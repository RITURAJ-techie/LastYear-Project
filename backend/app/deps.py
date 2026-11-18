"""Shared helpers for routers: ownership checks, serialisation and a small analytics cache."""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import Dashboard, Dataset, ETLRun, User

_cache: OrderedDict[str, Any] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 256


def cached(ds: Dataset, name: str, params: dict[str, Any], fn: Callable[[], Any]) -> Any:
    """Memoise expensive analytics per dataset version (invalidated on every ETL refresh)."""
    key = json.dumps([ds.table_name, str(ds.last_refreshed), name, params], sort_keys=True, default=str)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    value = fn()
    with _cache_lock:
        _cache[key] = value
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return value


def owned_dataset(db: Session, dataset_id: int, user: User) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None or ds.owner_id != user.id:
        raise HTTPException(404, "Dataset not found")
    return ds


def ready_dataset(db: Session, dataset_id: int, user: User) -> Dataset:
    ds = owned_dataset(db, dataset_id, user)
    if ds.status not in {"ready"} or not ds.profile:
        raise HTTPException(409, f"Dataset is not ready (status: {ds.status})")
    return ds


def owned_dashboard(db: Session, dashboard_id: int, user: User) -> Dashboard:
    d = db.get(Dashboard, dashboard_id)
    if d is None or d.owner_id != user.id:
        raise HTTPException(404, "Dashboard not found")
    return d


def user_tables(db: Session, user: User) -> set[str]:
    tables = set()
    for ds in db.query(Dataset).filter(Dataset.owner_id == user.id).all():
        tables.add(ds.table_name)
        tables.add("stg_" + ds.table_name[3:])
        tables.add("mart_" + ds.table_name[3:])
    tables.add("dim_date")
    return tables


def _redact(cfg: dict[str, Any]) -> dict[str, Any]:
    out = dict(cfg or {})
    if "connection_url" in out:
        url = out["connection_url"]
        # hide password in URLs like postgresql://user:pass@host/db
        if "@" in url and "://" in url:
            scheme, rest = url.split("://", 1)
            creds, host = rest.rsplit("@", 1)
            user = creds.split(":", 1)[0]
            out["connection_url"] = f"{scheme}://{user}:***@{host}" if ":" in creds else url
    if "headers" in out and out["headers"]:
        out["headers"] = {k: "***" for k in out["headers"]}
    out.pop("path", None)
    return out


def dataset_out(ds: Dataset, detail: bool = False) -> dict[str, Any]:
    out = {
        "id": ds.id, "name": ds.name, "description": ds.description, "table_name": ds.table_name,
        "source_type": ds.source_type, "source_config": _redact(ds.source_config), "status": ds.status,
        "row_count": ds.row_count, "column_count": ds.column_count,
        "quality_score": (ds.quality or {}).get("score_after"), "quality_before": (ds.quality or {}).get("score_before"),
        "refresh_interval_minutes": ds.refresh_interval_minutes,
        "last_refreshed": ds.last_refreshed.isoformat() if ds.last_refreshed else None,
        "created_at": ds.created_at.isoformat() if ds.created_at else None,
        "primary_time": (ds.profile or {}).get("primary_time"),
        "primary_measure": (ds.profile or {}).get("primary_measure"),
        "etl_options": ds.etl_options or {},
    }
    if detail:
        out["profile"] = ds.profile
        out["quality"] = ds.quality
    return out


def run_out(r: ETLRun, steps: bool = True) -> dict[str, Any]:
    out = {
        "id": r.id, "dataset_id": r.dataset_id, "trigger": r.trigger, "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "duration_s": round((r.finished_at - r.started_at).total_seconds(), 3) if r.finished_at and r.started_at else None,
        "rows_extracted": r.rows_extracted, "rows_loaded": r.rows_loaded, "error": r.error,
    }
    if steps:
        out["steps"] = r.steps
    return out


def dashboard_out(d: Dashboard) -> dict[str, Any]:
    return {
        "id": d.id, "name": d.name, "description": d.description, "dataset_id": d.dataset_id,
        "dataset_name": d.dataset.name if d.dataset else None, "widgets": d.widgets or [], "filters": d.filters or [],
        "is_auto": bool(d.is_auto), "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }
