"""Business operations shared by the API, the scheduler and the demo seeder."""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from . import warehouse as wh
from .analytics import dashboard as dash
from .database import Dashboard, Dataset, ETLRun, User
from .etl.pipeline import run_etl, unique_table_name

log = logging.getLogger("insightflow")


def create_dataset(db: Session, user: User, name: str, source_type: str, source_config: dict[str, Any],
                   description: str = "", etl_options: dict[str, Any] | None = None, refresh_interval_minutes: int = 0,
                   raw: pd.DataFrame | None = None, trigger: str = "upload", auto_dashboard: bool = True) -> tuple[Dataset, ETLRun]:
    ds = Dataset(owner_id=user.id, name=name.strip()[:200] or "Untitled dataset", description=description,
                 table_name=unique_table_name(db, name), source_type=source_type, source_config=source_config,
                 etl_options=etl_options or {}, refresh_interval_minutes=refresh_interval_minutes, status="pending")
    db.add(ds)
    db.commit()
    run = run_etl(db, ds, trigger=trigger, raw=raw)
    if run.status == "success" and auto_dashboard:
        create_auto_dashboard(db, user, ds)
    return ds, run


def create_auto_dashboard(db: Session, user: User, ds: Dataset) -> Dashboard | None:
    try:
        widgets = dash.generate(ds.table_name, ds.profile)
    except Exception as exc:  # noqa: BLE001 - dashboard generation should never block ingestion
        log.warning("Auto dashboard failed for %s: %s", ds.name, exc)
        return None
    d = Dashboard(owner_id=user.id, dataset_id=ds.id, name=f"{ds.name} – Overview", is_auto=1,
                  description="Automatically generated from the detected schema", widgets=widgets, filters=[])
    db.add(d)
    db.commit()
    return d


def delete_dataset(db: Session, ds: Dataset) -> None:
    wh.drop_objects(ds.table_name)
    db.delete(ds)
    db.commit()
