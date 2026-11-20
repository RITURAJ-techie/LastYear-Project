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


def create_combined_dashboard(db: Session, user: User, datasets: list[Dataset], integrated: Dataset | None = None,
                              name: str | None = None) -> Dashboard | None:
    """One dashboard over several datasets (widgets carry their own dataset_id)."""
    if not datasets:
        return None
    try:
        widgets = dash.generate_combined(datasets, integrated)
    except Exception as exc:  # noqa: BLE001 - never block an upload because of the dashboard
        log.warning("Combined dashboard failed: %s", exc)
        return None
    primary = integrated or datasets[0]
    names = [d.name for d in datasets if not integrated or d.id != integrated.id]
    d = Dashboard(owner_id=user.id, dataset_id=primary.id, is_auto=1, widgets=widgets, filters=[],
                  name=(name or f"Combined – {', '.join(names)}")[:200],
                  description=f"Combined dashboard across {len(datasets)} datasets")
    db.add(d)
    db.commit()
    return d


def delete_dataset(db: Session, ds: Dataset) -> None:
    # remove this dataset's widgets from combined dashboards owned by other primary datasets
    for d in db.query(Dashboard).filter(Dashboard.owner_id == ds.owner_id, Dashboard.dataset_id != ds.id).all():
        kept = [w for w in (d.widgets or []) if w.get("dataset_id") != ds.id]
        if len(kept) != len(d.widgets or []):
            d.widgets = kept
    wh.drop_objects(ds.table_name)
    db.delete(ds)
    db.commit()
