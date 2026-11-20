"""Combined insights across several datasets (e.g. everything uploaded in one batch)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..ai import llm
from ..analytics import insights as ins
from ..analytics import relationships
from ..auth import get_current_user
from ..database import Dataset, User, get_db
from ..deps import cached

router = APIRouter(prefix="/api/insights", tags=["insights"])

MAX_DATASETS = 20
SEVERITY_RANK = {"negative": 0, "warning": 1, "positive": 2, "info": 3}


def _parse_ids(ids: str | None) -> list[int]:
    if not ids:
        return []
    try:
        return list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))
    except ValueError:
        raise HTTPException(400, "ids must be a comma-separated list of dataset ids")


def _dataset_insights(snap: SimpleNamespace) -> dict[str, Any]:
    try:
        res = cached(snap, "insights", {}, lambda: ins.generate(snap.table_name, snap.profile, snap.quality))
        return {"ok": True, **res}
    except Exception as exc:  # noqa: BLE001 - one bad dataset must not break the combined view
        return {"ok": False, "error": str(exc), "insights": [], "summary": "", "facts": {}}


@router.get("/combined")
def combined(ids: str | None = Query(None, description="Comma-separated dataset ids; all ready datasets when omitted"),
             ai: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wanted = _parse_ids(ids)
    q = db.query(Dataset).filter(Dataset.owner_id == user.id, Dataset.status == "ready")
    if wanted:
        q = q.filter(Dataset.id.in_(wanted))
    datasets = q.order_by(Dataset.created_at.desc()).limit(MAX_DATASETS).all()
    if not datasets:
        raise HTTPException(404, "No ready datasets selected")

    # plain snapshots: safe to hand to worker threads (no ORM session access)
    snaps = [SimpleNamespace(id=d.id, name=d.name, table_name=d.table_name, profile=d.profile, quality=d.quality,
                             last_refreshed=d.last_refreshed) for d in datasets]
    with ThreadPoolExecutor(max_workers=min(4, len(snaps))) as pool:
        results = list(pool.map(_dataset_insights, snaps))

    per_dataset, merged = [], []
    for d, res in zip(datasets, results):
        q_ = d.quality or {}
        issues = q_.get("issues", {})
        fixed = sum(v for k, v in issues.items() if k not in {"outliers_detected", "columns_dropped"})
        sev: dict[str, int] = {}
        for i in res["insights"]:
            sev[i["severity"]] = sev.get(i["severity"], 0) + 1
            merged.append({**i, "dataset_id": d.id, "dataset_name": d.name})
        per_dataset.append({
            "id": d.id, "name": d.name, "source_type": d.source_type, "row_count": d.row_count,
            "column_count": d.column_count, "quality_before": q_.get("score_before"), "quality_after": q_.get("score_after"),
            "issues_fixed": fixed, "primary_measure": (d.profile or {}).get("primary_measure"),
            "primary_time": (d.profile or {}).get("primary_time"), "summary": res.get("summary", ""),
            "insight_count": len(res["insights"]), "severity_counts": sev, "top_insights": res["insights"][:5],
            "error": None if res["ok"] else res["error"],
        })
    # rank: highest-priority findings first; a dataset contributes at most 4 to the headline list.
    # An integrated dataset repeats findings of the sources it was built from: identical findings
    # are merged into one entry that lists every dataset it appears in.
    merged.sort(key=lambda i: (-i["score"], SEVERITY_RANK.get(i["severity"], 9)))
    headline, taken, seen = [], {}, {}
    for i in merged:
        key = (i["title"], i["description"])
        if key in seen:
            seen[key].setdefault("also_in", []).append(i["dataset_name"])
            continue
        if taken.get(i["dataset_id"], 0) < 4 and len(headline) < 15:
            headline.append(i)
            seen[key] = i
            taken[i["dataset_id"]] = taken.get(i["dataset_id"], 0) + 1
    rels = relationships.discover(datasets) if len(datasets) > 1 else []
    sev_all: dict[str, int] = {}
    for i in merged:
        sev_all[i["severity"]] = sev_all.get(i["severity"], 0) + 1
    out = {
        "totals": {"datasets": len(datasets), "rows": sum(d.row_count for d in datasets),
                   "issues_fixed": sum(p["issues_fixed"] for p in per_dataset), "insights": len(merged),
                   "risks": sev_all.get("negative", 0), "warnings": sev_all.get("warning", 0),
                   "opportunities": sev_all.get("positive", 0), "info": sev_all.get("info", 0)},
        "datasets": per_dataset,
        "top_insights": headline,
        "action_plan": [{"title": i["title"], "action": i["recommendation"], "severity": i["severity"],
                         "dataset_name": i["dataset_name"]} for i in headline if i["severity"] in {"negative", "warning", "positive"} and i["type"] != "quality"][:10],
        "relationships": rels,
        "ai_available": llm.available(),
    }
    if ai:
        if not llm.available():
            raise HTTPException(400, "Generative AI is not configured. Set SARVAM_API_KEY to enable Sarvam AI narratives.")
        out["ai_narrative"] = ins.ai_combined_narrative(out)
    return out
