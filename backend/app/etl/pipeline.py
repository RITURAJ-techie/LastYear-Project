"""ETL orchestration: Extract -> Transform -> Profile -> Load (staging, core, marts)."""
from __future__ import annotations

import logging
import re
import time
import traceback
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from .. import warehouse as wh
from ..database import Dataset, ETLRun, utcnow
from . import extract
from .profile import profile_dataframe, quality_report
from .transform import standardize_name, transform

log = logging.getLogger("insightflow.etl")


def slugify(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower() or "dataset"
    if s[0].isdigit():
        s = "d_" + s
    return s[:40]


def unique_table_name(db: Session, name: str) -> str:
    base = "dw_" + slugify(name)
    candidate, i = base, 1
    while db.query(Dataset).filter(Dataset.table_name == candidate).first():
        i += 1
        candidate = f"{base}_{i}"
    return candidate


def extract_for(dataset: Dataset) -> pd.DataFrame:
    cfg = dataset.source_config or {}
    st = dataset.source_type
    if st == "file":
        frames = extract.read_file(Path(cfg["path"]), cfg.get("original_name"))
        sheet = cfg.get("sheet")
        if sheet and sheet in frames:
            return frames[sheet]
        return next(iter(frames.values()))
    if st == "sql":
        return extract.read_sql(cfg["connection_url"], cfg.get("query"), cfg.get("table"))
    if st == "api":
        return extract.read_api(cfg["url"], cfg.get("record_path"), cfg.get("headers"), cfg.get("params"))
    if st in {"join", "derived"}:
        return wh.query_df(cfg["sql"])
    if st == "dataframe":  # in-memory frames (used by tests / internal callers)
        raise extract.ExtractError("In-memory dataset cannot be refreshed")
    raise extract.ExtractError(f"Unknown source type {st}")


def _staging_frame(raw: pd.DataFrame) -> pd.DataFrame:
    stg = raw.copy()
    seen: dict[str, int] = {}
    cols = []
    for i, c in enumerate(stg.columns):
        n = standardize_name(c, i)
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        cols.append(n)
    stg.columns = cols
    for c in stg.columns:
        stg[c] = stg[c].astype("string")
    stg["_loaded_at"] = pd.Timestamp.now('UTC').tz_localize(None)
    return stg


def build_marts(table: str, profile: dict[str, Any]) -> list[str]:
    """Create pre-aggregated mart views for fast dashboarding."""
    base = table[3:]
    created: list[str] = []
    measures = profile.get("measures", [])[:6]
    cols = {c["name"]: c for c in profile.get("columns", [])}
    aggs = []
    for m in measures:
        fn = "avg" if cols[m].get("default_agg") == "avg" else "sum"
        aggs.append(f"round({fn}({wh.qi(m)}), 4) AS {wh.qi(fn + '_' + m)}")
    agg_sql = ", ".join(["count(*) AS records"] + aggs)
    t = profile.get("primary_time")
    with wh.cursor() as con:
        if t:
            v = f"mart_{base}_monthly"
            con.execute(
                f"CREATE OR REPLACE VIEW {wh.qi(v)} AS SELECT date_trunc('month', {wh.qi(t)}) AS month, {agg_sql} "
                f"FROM {table} WHERE {wh.qi(t)} IS NOT NULL GROUP BY 1 ORDER BY 1"
            ).fetchall()
            created.append(v)
        for d in profile.get("dimensions", [])[:2]:
            v = f"mart_{base}_by_{d}"[:120]
            con.execute(
                f"CREATE OR REPLACE VIEW {wh.qi(v)} AS SELECT {wh.qi(d)}, {agg_sql} FROM {table} GROUP BY 1 ORDER BY 2 DESC"
            ).fetchall()
            created.append(v)
    return created


def run_etl(db: Session, dataset: Dataset, trigger: str = "manual", raw: pd.DataFrame | None = None) -> ETLRun:
    run = ETLRun(dataset_id=dataset.id, trigger=trigger, status="running", started_at=utcnow(), steps=[])
    db.add(run)
    dataset.status = "processing"
    db.commit()
    t0 = time.perf_counter()
    try:
        if raw is None:
            raw = extract_for(dataset)
        if raw.empty or raw.shape[1] == 0:
            raise extract.ExtractError("Source returned no rows")
        run.rows_extracted = int(len(raw))
        t1 = time.perf_counter()

        result = transform(raw, dataset.etl_options or {})
        clean = result.df
        if clean.empty:
            raise extract.ExtractError("No rows left after cleaning")
        t2 = time.perf_counter()

        profile = profile_dataframe(clean)
        quality = quality_report(raw, clean, result.issues)

        stg_table = "stg_" + dataset.table_name[3:]
        wh.load_dataframe(stg_table, _staging_frame(raw))
        wh.load_dataframe(dataset.table_name, clean)
        marts = build_marts(dataset.table_name, profile)
        for tcol in profile["time_columns"][:1]:
            s = clean[tcol].dropna()
            if len(s):
                wh.ensure_date_dimension(s.min(), s.max())
        t3 = time.perf_counter()

        steps = result.log + [{
            "step": "load", "affected": int(len(clean)),
            "description": f"Loaded staging table {stg_table}, core table {dataset.table_name}"
                           + (f" and {len(marts)} mart view(s)" if marts else ""),
            "details": {"staging": stg_table, "core": dataset.table_name, "marts": marts},
        }]
        run.steps = steps
        run.rows_loaded = int(len(clean))
        run.status = "success"
        run.finished_at = utcnow()
        dataset.profile = {**profile, "timings": {"extract_s": round(t1 - t0, 3), "transform_s": round(t2 - t1, 3),
                                                   "load_s": round(t3 - t2, 3)}}
        dataset.quality = quality
        dataset.row_count = int(len(clean))
        dataset.column_count = int(clean.shape[1])
        dataset.status = "ready"
        dataset.last_refreshed = utcnow()
    except Exception as exc:  # noqa: BLE001 - recorded on the run for the user
        log.warning("ETL failed for dataset %s: %s", dataset.id, exc)
        run.status = "failed"
        run.error = str(exc)
        run.finished_at = utcnow()
        run.steps = (run.steps or []) + [{"step": "error", "description": str(exc), "affected": 0,
                                           "details": traceback.format_exc(limit=3)}]
        dataset.status = "failed" if not dataset.row_count else "ready"
    db.commit()
    db.refresh(run)
    return run
