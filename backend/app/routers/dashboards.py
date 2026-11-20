from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..analytics import dashboard as dash
from ..auth import get_current_user
from ..database import Dashboard, User, get_db
from ..deps import dashboard_out, owned_dashboard, owned_dataset, ready_dataset
from ..services import create_combined_dashboard

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


class DashboardIn(BaseModel):
    dataset_id: int
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    auto: bool = True


class CombinedIn(BaseModel):
    dataset_ids: list[int] = Field(min_length=1, max_length=20)
    name: str | None = Field(None, max_length=200)


class DashboardPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    widgets: list[dict[str, Any]] | None = None
    filters: list[dict[str, Any]] | None = None


@router.get("")
def list_dashboards(dataset_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Dashboard).filter(Dashboard.owner_id == user.id)
    if dataset_id:
        q = q.filter(Dashboard.dataset_id == dataset_id)
    return [dashboard_out(d) for d in q.order_by(Dashboard.updated_at.desc()).all()]


@router.post("")
def create_dashboard(body: DashboardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, body.dataset_id, user)
    widgets = dash.generate(ds.table_name, ds.profile) if body.auto else []
    d = Dashboard(owner_id=user.id, dataset_id=ds.id, name=body.name, description=body.description,
                  widgets=widgets, filters=[], is_auto=int(body.auto))
    db.add(d)
    db.commit()
    return dashboard_out(d)


@router.post("/combined")
def create_combined(body: CombinedIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Build one dashboard over several datasets. An integrated (joined) dataset in the selection
    leads the dashboard; every other dataset gets its own labelled section."""
    datasets = [ready_dataset(db, i, user) for i in dict.fromkeys(body.dataset_ids)]
    joined = [d for d in datasets if d.source_type == "join"]
    integrated = max(joined, key=lambda d: d.row_count) if joined else None
    d = create_combined_dashboard(db, user, datasets, integrated, body.name)
    if d is None:
        raise HTTPException(400, "Could not build a dashboard for these datasets")
    return dashboard_out(d)


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return dashboard_out(owned_dashboard(db, dashboard_id, user))


@router.patch("/{dashboard_id}")
def update_dashboard(dashboard_id: int, body: DashboardPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = owned_dashboard(db, dashboard_id, user)
    if body.name is not None:
        d.name = body.name
    if body.description is not None:
        d.description = body.description
    if body.widgets is not None:
        for w in body.widgets:
            if not isinstance(w, dict) or "type" not in w or "id" not in w:
                raise HTTPException(400, "Each widget needs an id and a type")
            if w.get("dataset_id") is not None:
                owned_dataset(db, int(w["dataset_id"]), user)  # cannot point a widget at someone else's data
        d.widgets = body.widgets
    if body.filters is not None:
        d.filters = body.filters
    db.commit()
    return dashboard_out(d)


@router.post("/{dashboard_id}/regenerate")
def regenerate(dashboard_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = owned_dashboard(db, dashboard_id, user)
    ds = ready_dataset(db, d.dataset_id, user)
    ids = dashboard_out(d)["dataset_ids"]
    if len(ids) > 1:
        datasets = [ready_dataset(db, i, user) for i in ids]
        joined = [x for x in datasets if x.source_type == "join"]
        d.widgets = dash.generate_combined(datasets, max(joined, key=lambda x: x.row_count) if joined else None)
    else:
        d.widgets = dash.generate(ds.table_name, ds.profile)
    d.filters = []
    db.commit()
    return dashboard_out(d)


@router.delete("/{dashboard_id}")
def delete_dashboard(dashboard_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    d = owned_dashboard(db, dashboard_id, user)
    db.delete(d)
    db.commit()
    return {"ok": True}
