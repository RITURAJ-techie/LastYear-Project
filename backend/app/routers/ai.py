from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai import llm
from ..analytics import nlq
from ..analytics.query import QueryError
from ..auth import get_current_user
from ..config import AI_MODEL
from ..database import User, get_db
from ..deps import ready_dataset, user_tables

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status")
def status():
    return {"generative_ai": llm.available(), "model": AI_MODEL if llm.available() else None, "provider": llm.PROVIDER,
            "engines": ["statistics", "machine-learning", "rule-based NLP"] + ([llm.PROVIDER] if llm.available() else [])}


class AskIn(BaseModel):
    dataset_id: int
    question: str = Field(min_length=2, max_length=500)
    use_ai: bool = True


@router.post("/ask")
def ask(body: AskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, body.dataset_id, user)
    try:
        return nlq.answer(body.question, ds.table_name, ds.profile, user_tables(db, user), body.use_ai)
    except QueryError as exc:
        raise HTTPException(400, f"Could not answer: {exc}")


@router.get("/suggestions/{dataset_id}")
def suggestions(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    p = ds.profile
    m = p.get("primary_measure")
    ucount = {c["name"]: c["unique"] for c in p["columns"]}
    dims = [d for d in p.get("dimensions", []) if 2 <= ucount.get(d, 0) <= 30]
    t = p.get("primary_time")
    out = []
    w = lambda s: s.replace("_", " ")  # noqa: E731
    if m and t:
        out.append(f"Show monthly total {w(m)}")
    if m and dims:
        out.append(f"Top 5 {w(dims[0])} by {w(m)}")
        out.append(f"Average {w(m)} by {w(dims[-1] if len(dims) > 1 else dims[0])}")
    if m and t and dims:
        out.append(f"{w(m).title()} by {w(dims[0])} per quarter")
    if len(p.get("measures", [])) > 1:
        out.append(f"What is the total {w(p['measures'][1])}?")
    out.append("How many records are there?")
    return out[:6]
