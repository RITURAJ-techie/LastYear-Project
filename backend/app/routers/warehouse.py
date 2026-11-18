from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import warehouse as wh
from ..analytics import relationships
from ..analytics.sqlguard import SQLGuardError, validate_select
from ..auth import get_current_user
from ..database import Dashboard, Dataset, ETLRun, User, get_db
from ..deps import dataset_out, owned_dataset, run_out, user_tables
from ..services import create_dataset

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    datasets = db.query(Dataset).filter(Dataset.owner_id == user.id).all()
    ids = [d.id for d in datasets]
    runs = db.query(ETLRun).filter(ETLRun.dataset_id.in_(ids)).order_by(ETLRun.started_at.desc()).all() if ids else []
    dashboards = db.query(Dashboard).filter(Dashboard.owner_id == user.id).count()
    q_scores = [d.quality.get("score_after") for d in datasets if d.quality]
    q_before = [d.quality.get("score_before") for d in datasets if d.quality]
    by_source = Counter(d.source_type for d in datasets)
    names = {d.id: d.name for d in datasets}
    recent = [{**run_out(r, steps=False), "dataset_name": names.get(r.dataset_id)} for r in runs[:8]]
    return {
        "datasets": len(datasets), "dashboards": dashboards,
        "total_rows": sum(d.row_count for d in datasets),
        "total_columns": sum(d.column_count for d in datasets),
        "avg_quality": round(sum(q_scores) / len(q_scores), 1) if q_scores else None,
        "avg_quality_before": round(sum(q_before) / len(q_before), 1) if q_before else None,
        "etl_runs": len(runs), "etl_success_rate": round(100 * sum(r.status == "success" for r in runs) / len(runs), 1) if runs else None,
        "issues_fixed": sum(sum(v for k, v in (d.quality or {}).get("issues", {}).items() if k not in {"outliers_detected", "columns_dropped"}) for d in datasets),
        "by_source": dict(by_source), "recent_runs": recent,
        "scheduled": sum(1 for d in datasets if d.refresh_interval_minutes),
    }


@router.get("/objects")
def objects(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = user_tables(db, user)
    owners = {}
    for d in db.query(Dataset).filter(Dataset.owner_id == user.id).all():
        owners[d.table_name] = owners["stg_" + d.table_name[3:]] = d.name
    out = []
    for o in wh.list_objects():
        n = o["name"]
        if n in allowed or any(n.startswith(t + "_") for t in allowed if t.startswith("mart_")):
            o["dataset"] = owners.get(n) or next((v for k, v in owners.items() if k.startswith("dw_") and n.startswith("mart_" + k[3:])), None)
            o["columns_detail"] = wh.table_columns(n) if o["kind"] == "table" else []
            out.append(o)
    return out


@router.get("/relationships")
def get_relationships(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.owner_id == user.id, Dataset.status == "ready").all()
    return relationships.discover(ds)


class JoinSpec(BaseModel):
    dataset_id: int
    left_column: str
    right_column: str
    how: str = Field("left", pattern="^(left|inner)$")


class JoinIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    base_dataset_id: int
    joins: list[JoinSpec] = Field(min_length=1, max_length=6)
    description: str = ""


@router.post("/join")
def join(body: JoinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Integrate several datasets into one modelled (denormalised) dataset inside the warehouse."""
    base = owned_dataset(db, body.base_dataset_id, user)
    base_cols = [c["name"] for c in base.profile.get("columns", [])]
    used = set(base_cols)
    select = [f"t0.{wh.qi(c)}" for c in base_cols]
    joins_sql = []
    available = {c: "t0" for c in base_cols}
    for i, j in enumerate(body.joins, start=1):
        other = owned_dataset(db, j.dataset_id, user)
        o_cols = [c["name"] for c in other.profile.get("columns", [])]
        if j.left_column not in available:
            raise HTTPException(400, f"Column '{j.left_column}' not available for join")
        if j.right_column not in o_cols:
            raise HTTPException(400, f"Column '{j.right_column}' not in {other.name}")
        alias = f"t{i}"
        joins_sql.append(f"{'LEFT' if j.how == 'left' else 'INNER'} JOIN {other.table_name} {alias} "
                         f"ON CAST({available[j.left_column]}.{wh.qi(j.left_column)} AS VARCHAR) = CAST({alias}.{wh.qi(j.right_column)} AS VARCHAR)")
        prefix = other.table_name[3:]
        for c in o_cols:
            if c == j.right_column:
                continue
            name = c if c not in used else f"{prefix}_{c}"
            used.add(name)
            available[name] = alias
            select.append(f"{alias}.{wh.qi(c)} AS {wh.qi(name)}")
    sql = f"SELECT {', '.join(select)} FROM {base.table_name} t0 " + " ".join(joins_sql)
    try:
        raw = wh.query_df(sql)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Join failed: {exc}")
    opts = {"remove_duplicates": False, "normalize_categories": False}
    ds, run = create_dataset(db, user, body.name, "join", {"sql": sql, "sources": [base.id] + [j.dataset_id for j in body.joins]},
                             body.description or "Integrated dataset built in the warehouse", opts, raw=raw)
    return {"dataset": dataset_out(ds), "run": run_out(run), "sql": sql}


class SQLIn(BaseModel):
    sql: str = Field(min_length=1, max_length=20000)
    limit: int = Field(500, ge=1, le=5000)


@router.post("/sql")
def run_sql(body: SQLIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        sql = validate_select(body.sql, user_tables(db, user))
        df = wh.query_df(f"SELECT * FROM ({sql}) AS q LIMIT {body.limit}")
    except SQLGuardError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface SQL errors
        raise HTTPException(400, f"SQL error: {str(exc).splitlines()[0]}")
    return {"columns": list(df.columns), "rows": wh.to_records(df), "row_count": len(df), "sql": sql}


@router.get("/runs")
def all_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    datasets = {d.id: d.name for d in db.query(Dataset).filter(Dataset.owner_id == user.id).all()}
    if not datasets:
        return []
    rows = db.query(ETLRun).filter(ETLRun.dataset_id.in_(list(datasets))).order_by(ETLRun.started_at.desc()).limit(200).all()
    return [{**run_out(r), "dataset_name": datasets.get(r.dataset_id)} for r in rows]
