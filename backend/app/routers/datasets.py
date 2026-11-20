from __future__ import annotations

import io
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import warehouse as wh
from ..analytics import dashboard as dash
from ..analytics import relationships
from ..analytics import query as q
from ..auth import get_current_user
from ..config import MAX_UPLOAD_MB, UPLOAD_DIR
from ..database import Dataset, ETLRun, User, get_db
from ..deps import dataset_out, owned_dataset, ready_dataset, run_out
from ..etl import extract
from ..etl.pipeline import run_etl
from ..etl.transform import DEFAULT_OPTIONS
from ..services import create_combined_dashboard, create_dataset, delete_dataset

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
def list_datasets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Dataset).filter(Dataset.owner_id == user.id).order_by(Dataset.created_at.desc()).all()
    return [dataset_out(d) for d in rows]


@router.get("/etl-options")
def etl_options():
    return DEFAULT_OPTIONS


def _parse_options(options: str | None) -> dict[str, Any]:
    if not options:
        return {}
    try:
        val = json.loads(options)
        return {k: v for k, v in val.items() if k in DEFAULT_OPTIONS}
    except (json.JSONDecodeError, AttributeError):
        raise HTTPException(400, "Invalid ETL options JSON")


async def _save_upload(file: UploadFile) -> tuple[Path, str]:
    """Stream an upload to disk (size-limited). Raises HTTPException on bad type/size."""
    filename = Path(file.filename or "upload.csv").name
    ext = Path(filename).suffix.lower()
    if ext not in extract.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"{filename}: unsupported file type '{ext}'")
    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    size = 0
    with dest.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"{filename}: file exceeds {MAX_UPLOAD_MB} MB")
            fh.write(chunk)
    return dest, filename


def _ingest_file(db: Session, user: User, dest: Path, filename: str, name: str | None, description: str,
                 options: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a saved file (every Excel sheet becomes a dataset) and run ETL on each frame."""
    try:
        frames = extract.read_file(dest, filename)
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"{filename}: could not read file: {exc}")
    base = (name or Path(filename).stem.replace("_", " ").replace("-", " ")).strip()
    created = []
    for sheet, df in frames.items():
        ds_name = base if len(frames) == 1 else f"{base} – {sheet}"
        cfg = {"path": str(dest), "original_name": filename, "sheet": sheet if len(frames) > 1 else None}
        ds, run = create_dataset(db, user, ds_name, "file", cfg, description, options, raw=df)
        created.append({"dataset": dataset_out(ds), "run": run_out(run), "file": filename})
    return created


@router.post("/upload")
async def upload(file: UploadFile = File(...), name: str | None = Form(None), description: str = Form(""),
                 options: str | None = Form(None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dest, filename = await _save_upload(file)
    return _ingest_file(db, user, dest, filename, name, description, _parse_options(options))


MAX_BATCH_FILES = 20


@router.post("/upload-batch")
async def upload_batch(files: list[UploadFile] = File(...), options: str | None = Form(None),
                       auto_integrate: bool = Form(True), integrated_name: str | None = Form(None),
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload several files at once: ETL each one, discover how they relate, optionally build an
    integrated (joined) dataset, and return everything needed for combined insights.

    A file that fails is reported in `failed` and never aborts the rest of the batch."""
    if not files:
        raise HTTPException(400, "No files uploaded")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(400, f"At most {MAX_BATCH_FILES} files per batch")
    opts = _parse_options(options)
    created: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for f in files:
        try:
            dest, filename = await _save_upload(f)
            created.extend(_ingest_file(db, user, dest, filename, None, "Uploaded in a batch", opts))
        except HTTPException as exc:
            failed.append({"file": Path(f.filename or "?").name, "error": str(exc.detail)})
    for c in created:
        if c["run"]["status"] != "success":
            failed.append({"file": c["file"], "error": c["run"]["error"] or "ETL failed"})
    ready_ids = [c["dataset"]["id"] for c in created if c["run"]["status"] == "success"]
    ready = db.query(Dataset).filter(Dataset.id.in_(ready_ids)).all() if ready_ids else []

    rels = relationships.discover(ready) if len(ready) > 1 else []
    integrated = None
    if auto_integrate and rels:
        try:
            integrated = build_integrated(db, user, ready, rels, integrated_name)
        except HTTPException as exc:
            failed.append({"file": "(integrated dataset)", "error": str(exc.detail)})
    combined_dashboard = None
    if len(ready) > 1:
        integ_ds = db.get(Dataset, integrated["dataset"]["id"]) if integrated and integrated["run"]["status"] == "success" else None
        dsets = ready + ([integ_ds] if integ_ds else [])
        d = create_combined_dashboard(db, user, dsets, integ_ds)
        combined_dashboard = d.id if d else None
    return {
        "combined_dashboard_id": combined_dashboard,
        "datasets": [c for c in created if c["run"]["status"] == "success"],
        "failed": failed,
        "relationships": rels,
        "integrated": integrated,
        "insight_dataset_ids": ready_ids + ([integrated["dataset"]["id"]] if integrated else []),
    }


def build_integrated(db: Session, user: User, datasets: list[Dataset], rels: list[dict[str, Any]],
                     name: str | None = None) -> dict[str, Any] | None:
    """Join the 'fact' dataset (most outgoing many-to-one links) with every dataset it references."""
    from .warehouse import JoinIn, JoinSpec, join

    m2o = [r for r in rels if r["cardinality"] == "many-to-one"]
    if not m2o:
        return None
    by_id = {d.id: d for d in datasets}
    outgoing: dict[int, set[int]] = {}
    for r in m2o:
        outgoing.setdefault(r["from_dataset_id"], set()).add(r["to_dataset_id"])
    base_id = max(outgoing, key=lambda i: (len(outgoing[i]), by_id[i].row_count))
    joins, used = [], set()
    for r in sorted((r for r in m2o if r["from_dataset_id"] == base_id), key=lambda r: -r["confidence"]):
        if r["to_dataset_id"] in used:
            continue
        used.add(r["to_dataset_id"])
        joins.append(JoinSpec(dataset_id=r["to_dataset_id"], left_column=r["from_column"], right_column=r["to_column"], how="left"))
    title = name or ("Integrated: " + " + ".join([by_id[base_id].name] + [by_id[j.dataset_id].name for j in joins]))[:190]
    return join(JoinIn(name=title, base_dataset_id=base_id, joins=joins,
                       description="Automatically integrated from a batch upload using discovered relationships"), user=user, db=db)


class SQLTestIn(BaseModel):
    connection_url: str


class SQLSourceIn(BaseModel):
    name: str = Field(min_length=1)
    connection_url: str
    table: str | None = None
    query: str | None = None
    description: str = ""
    refresh_interval_minutes: int = Field(0, ge=0, le=10080)
    etl_options: dict[str, Any] = {}


class APISourceIn(BaseModel):
    name: str = Field(min_length=1)
    url: str
    record_path: str | None = None
    headers: dict[str, str] = {}
    description: str = ""
    refresh_interval_minutes: int = Field(0, ge=0, le=10080)
    etl_options: dict[str, Any] = {}


def _resolve_sqlite(url: str) -> str:
    # allow the bundled demo database to be referenced by a short alias
    if url.strip() == "demo":
        from ..config import SAMPLE_DIR
        return f"sqlite:///{SAMPLE_DIR / 'erp.db'}"
    return url


@router.post("/sql/test")
def sql_test(body: SQLTestIn, user: User = Depends(get_current_user)):
    try:
        return {"ok": True, "tables": extract.list_sql_tables(_resolve_sqlite(body.connection_url))}
    except extract.ExtractError as exc:
        raise HTTPException(400, str(exc))


@router.post("/sql")
def add_sql_source(body: SQLSourceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.table and not body.query:
        raise HTTPException(400, "Provide a table or a query")
    cfg = {"connection_url": _resolve_sqlite(body.connection_url), "table": body.table, "query": body.query}
    try:
        raw = extract.read_sql(cfg["connection_url"], body.query, body.table)
    except extract.ExtractError as exc:
        raise HTTPException(400, str(exc))
    ds, run = create_dataset(db, user, body.name, "sql", cfg, body.description,
                             {k: v for k, v in body.etl_options.items() if k in DEFAULT_OPTIONS},
                             body.refresh_interval_minutes, raw=raw)
    return {"dataset": dataset_out(ds), "run": run_out(run)}


@router.post("/api")
def add_api_source(body: APISourceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cfg = {"url": body.url, "record_path": body.record_path, "headers": body.headers}
    try:
        raw = extract.read_api(body.url, body.record_path, body.headers)
    except extract.ExtractError as exc:
        raise HTTPException(400, str(exc))
    ds, run = create_dataset(db, user, body.name, "api", cfg, body.description,
                             {k: v for k, v in body.etl_options.items() if k in DEFAULT_OPTIONS},
                             body.refresh_interval_minutes, raw=raw)
    return {"dataset": dataset_out(ds), "run": run_out(run)}


@router.get("/{dataset_id}")
def get_dataset(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return dataset_out(owned_dataset(db, dataset_id, user), detail=True)


class DatasetPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    refresh_interval_minutes: int | None = Field(None, ge=0, le=10080)
    etl_options: dict[str, Any] | None = None


@router.patch("/{dataset_id}")
def update_dataset(dataset_id: int, body: DatasetPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = owned_dataset(db, dataset_id, user)
    if body.name is not None:
        ds.name = body.name.strip() or ds.name
    if body.description is not None:
        ds.description = body.description
    if body.refresh_interval_minutes is not None:
        ds.refresh_interval_minutes = body.refresh_interval_minutes
    if body.etl_options is not None:
        ds.etl_options = {k: v for k, v in body.etl_options.items() if k in DEFAULT_OPTIONS}
    db.commit()
    return dataset_out(ds, detail=True)


@router.delete("/{dataset_id}")
def remove_dataset(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = owned_dataset(db, dataset_id, user)
    path = (ds.source_config or {}).get("path")
    delete_dataset(db, ds)
    if path and not any((d.source_config or {}).get("path") == path for d in db.query(Dataset).all()):
        Path(path).unlink(missing_ok=True)
    return {"ok": True}


@router.post("/{dataset_id}/refresh")
def refresh(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = owned_dataset(db, dataset_id, user)
    run = run_etl(db, ds, trigger="manual")
    if run.status != "success":
        raise HTTPException(400, f"ETL failed: {run.error}")
    return {"dataset": dataset_out(ds), "run": run_out(run)}


@router.get("/{dataset_id}/runs")
def runs(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_dataset(db, dataset_id, user)
    rows = db.query(ETLRun).filter(ETLRun.dataset_id == dataset_id).order_by(ETLRun.started_at.desc()).limit(50).all()
    return [run_out(r) for r in rows]


@router.get("/{dataset_id}/preview")
def preview(dataset_id: int, limit: int = Query(50, ge=1, le=1000), offset: int = Query(0, ge=0),
            search: str | None = None, sort: str | None = None, desc: bool = False, layer: str = "core",
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = owned_dataset(db, dataset_id, user)
    table = ds.table_name if layer == "core" else "stg_" + ds.table_name[3:]
    cols = [c["name"] for c in wh.table_columns(table)]
    if not cols:
        raise HTTPException(404, "Table not loaded")
    where, params = "", []
    if search:
        where = " WHERE " + " OR ".join(f"CAST({wh.qi(c)} AS VARCHAR) ILIKE ?" for c in cols)
        params = [f"%{search}%"] * len(cols)
    order = f" ORDER BY {wh.qi(sort)} {'DESC' if desc else 'ASC'} NULLS LAST" if sort in cols else ""
    total = int(wh.query_df(f"SELECT count(*) AS n FROM {table}{where}", params)["n"].iloc[0])
    df = wh.query_df(f"SELECT * FROM {table}{where}{order} LIMIT {limit} OFFSET {offset}", params)
    return {"columns": cols, "rows": wh.to_records(df), "total": total, "table": table}


@router.get("/{dataset_id}/export")
def export(dataset_id: int, format: str = "csv", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    df = wh.read_table(ds.table_name)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in ds.name)
    if format == "xlsx":
        buf = io.BytesIO()
        with pd.ExcelWriter(buf) as xw:
            df.to_excel(xw, index=False, sheet_name="data")
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                 headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'})
    if format == "json":
        data = json.dumps(wh.to_records(df), default=str)
        return StreamingResponse(io.BytesIO(data.encode()), media_type="application/json",
                                 headers={"Content-Disposition": f'attachment; filename="{safe}.json"'})
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return StreamingResponse(io.BytesIO(buf.getvalue().encode()), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{safe}_clean.csv"'})


@router.get("/{dataset_id}/values/{column}")
def distinct_values(dataset_id: int, column: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    if column not in {c["name"] for c in ds.profile["columns"]}:
        raise HTTPException(404, "Unknown column")
    df = wh.query_df(f"SELECT CAST({wh.qi(column)} AS VARCHAR) AS v, count(*) AS n FROM {ds.table_name} "
                     f"WHERE {wh.qi(column)} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 200")
    return [{"value": r.v, "count": int(r.n)} for r in df.itertuples()]


@router.post("/{dataset_id}/query")
def chart_query(dataset_id: int, spec: dict[str, Any], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    try:
        return q.run_chart_query(ds.table_name, ds.profile, spec)
    except q.QueryError as exc:
        raise HTTPException(400, str(exc))


class WidgetDataIn(BaseModel):
    widget: dict[str, Any]
    filters: list[dict[str, Any]] = []


@router.post("/{dataset_id}/widget-data")
def widget_data(dataset_id: int, body: WidgetDataIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    try:
        return dash.widget_data(ds.table_name, ds.profile, body.widget, body.filters)
    except (q.QueryError, KeyError, ValueError) as exc:
        raise HTTPException(400, f"Widget error: {exc}")
