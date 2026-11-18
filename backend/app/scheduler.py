"""Lightweight background scheduler for automated ETL refreshes."""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from .database import Dataset, SessionLocal, utcnow
from .etl.pipeline import run_etl

log = logging.getLogger("insightflow.scheduler")
_stop = threading.Event()


def due_datasets(db) -> list[Dataset]:
    now = utcnow()
    out = []
    for ds in db.query(Dataset).filter(Dataset.refresh_interval_minutes > 0).all():
        if ds.source_type not in {"file", "sql", "api", "join"} or ds.status == "processing":
            continue
        if ds.last_refreshed is None or now - ds.last_refreshed >= timedelta(minutes=ds.refresh_interval_minutes):
            out.append(ds)
    return out


def tick() -> int:
    db = SessionLocal()
    try:
        due = due_datasets(db)
        for ds in due:
            run = run_etl(db, ds, trigger="schedule")
            log.info("Scheduled refresh of %s -> %s", ds.name, run.status)
        return len(due)
    finally:
        db.close()


def _loop(interval: int) -> None:
    while not _stop.wait(interval):
        try:
            tick()
        except Exception:  # noqa: BLE001 - keep the scheduler alive
            log.exception("Scheduler tick failed")


def start(interval_seconds: int = 60) -> None:
    _stop.clear()
    threading.Thread(target=_loop, args=(interval_seconds,), daemon=True, name="etl-scheduler").start()


def stop() -> None:
    _stop.set()
