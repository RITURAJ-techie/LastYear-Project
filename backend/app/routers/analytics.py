from __future__ import annotations

import html
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..ai import llm
from ..analytics import insights as ins
from ..analytics import ml, stats, trends
from ..auth import get_current_user
from ..database import User, get_db
from ..deps import cached, ready_dataset

router = APIRouter(prefix="/api/datasets/{dataset_id}/analysis", tags=["analytics"])


def _guard(fn):
    try:
        return fn()
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/summary")
def summary(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return cached(ds, "summary", {}, lambda: stats.summary(ds.table_name, ds.profile))


@router.get("/distributions")
def distributions(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return cached(ds, "dist", {}, lambda: stats.distributions(ds.table_name, ds.profile))


@router.get("/correlations")
def correlations(dataset_id: int, method: str = Query("pearson", pattern="^(pearson|spearman)$"),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return cached(ds, "corr", {"m": method}, lambda: stats.correlations(ds.table_name, ds.profile, method))


@router.get("/scatter")
def scatter(dataset_id: int, x: str, y: str, color: str | None = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return _guard(lambda: stats.scatter(ds.table_name, ds.profile, x, y, color))


@router.get("/trends")
def trend(dataset_id: int, measure: str | None = None, time_column: str | None = None, grain: str | None = None,
          horizon: int | None = Query(None, ge=1, le=120), agg: str | None = Query(None, pattern="^(sum|avg|count|min|max)$"),
          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    params = {"m": measure, "t": time_column, "g": grain, "h": horizon, "a": agg}
    return _guard(lambda: cached(ds, "trend", params, lambda: trends.analyze(ds.table_name, ds.profile, measure, time_column, grain, horizon, agg)))


@router.get("/anomalies")
def anomalies(dataset_id: int, contamination: float = Query(0.02, gt=0, le=0.2),
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return cached(ds, "anom", {"c": contamination}, lambda: ml.anomalies(ds.table_name, ds.profile, contamination))


@router.get("/drivers")
def drivers(dataset_id: int, target: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return _guard(lambda: cached(ds, "drivers", {"t": target}, lambda: ml.key_drivers(ds.table_name, ds.profile, target)))


@router.get("/clusters")
def clusters(dataset_id: int, k: int | None = Query(None, ge=2, le=10), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    return cached(ds, "clusters", {"k": k}, lambda: ml.clusters(ds.table_name, ds.profile, k))


@router.get("/insights")
def insights(dataset_id: int, ai: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = ready_dataset(db, dataset_id, user)
    result = dict(cached(ds, "insights", {}, lambda: ins.generate(ds.table_name, ds.profile, ds.quality)))
    result["ai_available"] = llm.available()
    if ai:
        if not llm.available():
            raise HTTPException(400, "Generative AI is not configured. Set SARVAM_API_KEY to enable Sarvam AI narratives.")
        result["ai_narrative"] = cached(ds, "ai_narr", {}, lambda: ins.ai_narrative(ds.name, result))
    return result


@router.get("/report", response_class=HTMLResponse)
def report(dataset_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Self-contained, printable HTML analytics report."""
    ds = ready_dataset(db, dataset_id, user)
    res = cached(ds, "insights", {}, lambda: ins.generate(ds.table_name, ds.profile, ds.quality))
    q = ds.quality or {}
    e = html.escape
    colors = {"positive": "#15803d", "negative": "#b91c1c", "warning": "#b45309", "info": "#1d4ed8"}
    cards = "".join(
        f"<div class='card' style='border-left:4px solid {colors.get(i['severity'], '#555')}'><h3>{e(i['title'])}</h3>"
        f"<p>{e(i['description'])}</p><p class='rec'><b>Recommendation:</b> {e(i['recommendation'])}</p></div>"
        for i in res["insights"]
    )
    cols = "".join(
        f"<tr><td>{e(c['name'])}</td><td>{e(c['semantic_type'])}</td><td>{e(c['role'])}</td><td>{c['missing_pct']}%</td><td>{c['unique']:,}</td></tr>"
        for c in ds.profile["columns"]
    )
    page = f"""<!doctype html><html><head><meta charset='utf-8'><title>InsightFlow Report – {e(ds.name)}</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;max-width:960px;margin:40px auto;color:#1f2937;padding:0 16px}}
h1{{color:#4338ca;margin-bottom:4px}}.muted{{color:#6b7280}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}}
.kpi{{background:#f5f7ff;border-radius:10px;padding:14px}}.kpi b{{font-size:22px;display:block}}
.card{{background:#fafafa;border-radius:8px;padding:12px 16px;margin:12px 0}}.card h3{{margin:0 0 6px;font-size:16px}}.rec{{color:#374151}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border-bottom:1px solid #e5e7eb;padding:6px;text-align:left}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>{e(ds.name)}</h1><div class='muted'>InsightFlow AI analytics report · generated {datetime.now():%d %b %Y %H:%M}</div>
<div class='grid'><div class='kpi'>Rows<b>{ds.row_count:,}</b></div><div class='kpi'>Columns<b>{ds.column_count}</b></div>
<div class='kpi'>Quality (raw → clean)<b>{q.get('score_before')} → {q.get('score_after')}</b></div><div class='kpi'>Source<b>{e(ds.source_type.upper())}</b></div></div>
<h2>Executive summary</h2><p>{e(res['summary'])}</p><h2>Insights & recommendations</h2>{cards}
<h2>Data dictionary</h2><table><tr><th>Column</th><th>Semantic type</th><th>Role</th><th>Missing (clean)</th><th>Unique</th></tr>{cols}</table>
</body></html>"""
    return HTMLResponse(page)
