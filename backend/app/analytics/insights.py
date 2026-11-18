"""Insight & recommendation engine.

Combines the outputs of the statistical and ML modules into ranked,
plain-language findings, each with a concrete recommended action.
"""
from __future__ import annotations

import json
import re
from typing import Any

import numpy as np
import pandas as pd

from .. import warehouse as wh
from ..ai import llm
from . import ml, stats, trends


LOWER_IS_BETTER = re.compile(r"(cost|expense|spend|discount|delay|days|duration|churn|return|refund|defect|complaint|error|loss|bounce|wait|latency|debt|absence|attrition)", re.I)


def _t(name: str) -> str:
    return name.replace("_", " ")


def _fmt(v: float | None, semantic: str = "numeric") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    a = abs(v)
    s = f"{v / 1e9:,.2f}B" if a >= 1e9 else f"{v / 1e6:,.2f}M" if a >= 1e6 else f"{v / 1e3:,.1f}K" if a >= 1e4 else f"{v:,.2f}"
    return ("$" + s) if semantic == "currency" else (s + "%") if semantic == "percentage" else s


def _insight(kind: str, severity: str, title: str, description: str, recommendation: str, score: float,
             metric: str | None = None, value: Any = None) -> dict[str, Any]:
    return {"type": kind, "severity": severity, "title": title, "description": description,
            "recommendation": recommendation, "score": round(float(score), 3), "metric": metric, "value": value}


def segment_movers(table: str, profile: dict[str, Any], measure: str, dim: str) -> dict[str, Any] | None:
    """Compare the latest 3 complete months vs the 3 before, per category."""
    t = profile.get("primary_time")
    if not t:
        return None
    m, d, tc = wh.qi(measure), wh.qi(dim), wh.qi(t)
    df = wh.query_df(f"SELECT date_trunc('month', {tc}) AS p, CAST({d} AS VARCHAR) AS k, sum({m}) AS v FROM {table} "
                     f"WHERE {tc} IS NOT NULL GROUP BY 1, 2")
    if df.empty:
        return None
    months = sorted(df["p"].unique())
    if len(months) < 7:
        return None
    recent, prior = months[-4:-1], months[-7:-4]  # skip possibly-partial last month
    cur = df[df["p"].isin(recent)].groupby("k")["v"].sum()
    prev = df[df["p"].isin(prior)].groupby("k")["v"].sum()
    joined = pd.concat([cur.rename("cur"), prev.rename("prev")], axis=1).fillna(0)
    joined = joined[joined["prev"] > 0.01 * joined["prev"].sum()]  # ignore tiny segments
    if joined.empty:
        return None
    joined["chg"] = (joined["cur"] - joined["prev"]) / joined["prev"] * 100
    joined["abs"] = joined["cur"] - joined["prev"]
    return {
        "period": f"{pd.Timestamp(recent[0]):%b %Y}–{pd.Timestamp(recent[-1]):%b %Y}",
        "prior": f"{pd.Timestamp(prior[0]):%b %Y}–{pd.Timestamp(prior[-1]):%b %Y}",
        "best": (joined["chg"].idxmax(), float(joined["chg"].max())),
        "worst": (joined["chg"].idxmin(), float(joined["chg"].min())),
        "table": joined.sort_values("chg").reset_index().rename(columns={"index": "k"}),
    }


def generate(table: str, profile: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    cols = {c["name"]: c for c in profile["columns"]}
    measures = profile["measures"]
    dims = [d for d in profile["dimensions"] if 2 <= cols[d]["unique"] <= 60]
    out: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}

    # 1. Trends, seasonality, forecast for the top measures
    for i, m in enumerate(measures[:3] if profile.get("primary_time") else []):
        sem = cols[m]["semantic_type"]
        tr = trends.analyze(table, profile, measure=m)
        if not tr.get("available"):
            continue
        facts.setdefault("trends", []).append({k: tr[k] for k in ("measure", "agg", "grain", "trend", "growth", "seasonality", "forecast")})
        weight = 1.0 - 0.2 * i
        g, trd = tr["growth"], tr["trend"]
        inverse = bool(LOWER_IS_BETTER.search(m))
        agg_word = "average" if tr["agg"] == "avg" else "total"
        if trd["direction"].startswith("upward") and inverse:
            out.append(_insight("trend", "warning", f"{_t(m).title()} is rising",
                                f"{agg_word.title()} {_t(m)} shows a statistically significant upward trend "
                                f"(+{trd['slope_pct_of_mean']:.2f}% of the mean per {tr['grain']}). "
                                f"It moved from {_fmt(g['first'], sem)} to {_fmt(g['last'], sem)} ({g['total_change_pct']:+.1f}%).",
                                f"Check whether rising {_t(m)} is justified by higher volume; set a target ratio and review the biggest contributors.",
                                7 * weight, m, trd["slope_pct_of_mean"]))
        elif trd["direction"].startswith("downward") and inverse:
            out.append(_insight("trend", "positive", f"{_t(m).title()} is falling",
                                f"{agg_word.title()} {_t(m)} shows a statistically significant downward trend "
                                f"({trd['slope_pct_of_mean']:.2f}% of the mean per {tr['grain']}), from {_fmt(g['first'], sem)} to {_fmt(g['last'], sem)}.",
                                f"Document what reduced {_t(m)} so the improvement can be sustained.",
                                6 * weight, m, trd["slope_pct_of_mean"]))
        elif trd["direction"].startswith("upward"):
            out.append(_insight("trend", "positive", f"{_t(m).title()} is growing",
                                f"{agg_word.title()} {_t(m)} shows a statistically significant upward trend "
                                f"(+{trd['slope_pct_of_mean']:.2f}% of the mean per {tr['grain']}, R² = {trd['r2']:.2f}). "
                                f"It moved from {_fmt(g['first'], sem)} to {_fmt(g['last'], sem)} over the period "
                                f"({g['total_change_pct']:+.1f}%).",
                                f"Sustain the momentum: identify which segments drive the growth in {_t(m)} and allocate more resources to them.",
                                8 * weight, m, trd["slope_pct_of_mean"]))
        elif trd["direction"].startswith("downward"):
            out.append(_insight("trend", "negative", f"{_t(m).title()} is declining",
                                f"{agg_word.title()} {_t(m)} shows a statistically significant downward trend "
                                f"({trd['slope_pct_of_mean']:.2f}% of the mean per {tr['grain']}). "
                                f"It moved from {_fmt(g['first'], sem)} to {_fmt(g['last'], sem)} ({g['total_change_pct']:+.1f}%).",
                                f"Investigate root causes of the decline in {_t(m)} – review the key-driver analysis and the worst-performing segments.",
                                9 * weight, m, trd["slope_pct_of_mean"]))
        if g.get("last_change_pct") is not None and abs(g["last_change_pct"]) >= 15:
            up = g["last_change_pct"] > 0
            out.append(_insight("change", "positive" if up != inverse else "warning",
                                f"{_t(m).title()} {'jumped' if up else 'dropped'} {abs(g['last_change_pct']):.1f}% in the latest {tr['grain']}",
                                f"The most recent complete {tr['grain']} recorded {_fmt(g['last'], sem)} for {_t(m)}, "
                                f"a {g['last_change_pct']:+.1f}% change versus the previous {tr['grain']}.",
                                "Check whether this is a one-off event (promotion, outage, data issue) or the start of a new pattern before acting." if not up
                                else "Find out what drove this jump (campaign, pricing, seasonality) and whether it can be repeated.",
                                6 * weight, m, g["last_change_pct"]))
        s = tr.get("seasonality")
        if s and s["detected"] and i == 0:
            out.append(_insight("seasonality", "info", f"Seasonal pattern in {_t(m)}: peaks in {s['peak']}",
                                f"{_t(m).title()} follows a recurring {('weekly' if tr['grain'] == 'day' else 'annual')} cycle "
                                f"(seasonal strength {s['strength'] * 100:.0f}%), highest in {s['peak']} and lowest in {s['trough']}.",
                                f"Plan inventory, staffing and marketing budgets ahead of the {s['peak']} peak; use the {s['trough']} trough for maintenance or promotions.",
                                7 * weight, m, s["strength"]))
        fc = tr["forecast"]
        if i == 0 and fc.get("total_forecast") is not None:
            acc = f" (backtest MAPE {fc['mape']:.1f}%)" if fc.get("mape") is not None else ""
            fut = [p for p in tr["points"] if "forecast" in p]
            out.append(_insight("forecast", "info", f"Forecast: {_t(m)} over the next {fc['horizon']} {tr['grain']}s",
                                f"Using {fc['method']}{acc}, {_t(m)} is projected at about {_fmt(fut[0]['forecast'], sem)} next {tr['grain']} "
                                f"and {_fmt(fut[-1]['forecast'], sem)} by {fut[-1]['period']}"
                                + (f", totalling {_fmt(fc['total_forecast'], sem)}." if tr["agg"] == "sum" else "."),
                                "Use the forecast range (not just the point estimate) for budgeting and capacity planning; re-run after each data refresh.",
                                5, m, fc["total_forecast"]))
        if tr["anomalies"] and i == 0:
            a = max(tr["anomalies"], key=lambda r: abs(r["score"]))
            out.append(_insight("anomaly", "warning", f"Unusual {a['type']} in {_t(m)} on {a['period']}",
                                f"{_t(m).title()} was {_fmt(a['value'], sem)} versus an expected ~{_fmt(a['expected'], sem)} "
                                f"({len(tr['anomalies'])} unusual period(s) detected in total).",
                                "Verify the records behind this period; if genuine, document the cause so it can be replicated or prevented.",
                                6.5, m, a["value"]))

    # 2. Segment concentration & movers
    additive = [m for m in measures if cols[m].get("default_agg") == "sum"]
    if additive and dims:
        m = additive[0]
        sem = cols[m]["semantic_type"]
        for j, d in enumerate(dims[:3]):
            g = wh.query_df(f"SELECT CAST({wh.qi(d)} AS VARCHAR) AS k, sum({wh.qi(m)}) AS v FROM {table} GROUP BY 1 ORDER BY 2 DESC")
            g = g[g["v"] > 0]
            if len(g) < 2:
                continue
            total = g["v"].sum()
            top_share = g["v"].iloc[0] / total * 100
            n20 = max(1, int(np.ceil(len(g) * 0.2)))
            pareto = g["v"].head(n20).sum() / total * 100
            facts.setdefault("segments", []).append({"dimension": d, "measure": m, "top": g["k"].iloc[0], "top_share_pct": round(top_share, 2),
                                                     "bottom": g["k"].iloc[-1], "categories": len(g), "top20pct_share": round(pareto, 2)})
            if top_share >= 40 and len(g) >= 3:
                out.append(_insight("concentration", "warning", f"{top_share:.0f}% of {_t(m)} comes from one {_t(d)}",
                                    f"'{g['k'].iloc[0]}' contributes {_fmt(g['v'].iloc[0], sem)} ({top_share:.1f}%) of total {_t(m)} across {len(g)} {_t(d)} values.",
                                    f"Reduce dependency risk: grow the next-largest {_t(d)} values ('{g['k'].iloc[1]}') while protecting '{g['k'].iloc[0]}'.",
                                    6 - j, m, top_share))
            elif j == 0:
                out.append(_insight("segment", "info", f"Top {_t(d)}: {g['k'].iloc[0]}",
                                    f"'{g['k'].iloc[0]}' leads {_t(m)} with {_fmt(g['v'].iloc[0], sem)} ({top_share:.1f}% share); "
                                    f"'{g['k'].iloc[-1]}' is lowest with {_fmt(g['v'].iloc[-1], sem)}. The top 20% of {_t(d)} values generate {pareto:.0f}% of the total.",
                                    f"Study what makes '{g['k'].iloc[0]}' successful and apply those practices to lower-performing {_t(d)} values.",
                                    5.5, m, top_share))
            mv = segment_movers(table, profile, m, d) if j < 2 else None
            if mv:
                (bk, bv), (wk, wv) = mv["best"], mv["worst"]
                if wv <= -10:
                    out.append(_insight("segment_decline", "negative", f"{_t(d).title()} '{wk}' fell {abs(wv):.0f}%",
                                        f"{_t(m).title()} for '{wk}' dropped {abs(wv):.1f}% in {mv['period']} compared with {mv['prior']}"
                                        + (f", while '{bk}' grew {bv:+.1f}%." if bv > 0 else "."),
                                        f"Prioritise a targeted review of '{wk}' (pricing, availability, competition, customer feedback).",
                                        7.5 - j, m, wv))
                if bv >= 10:
                    out.append(_insight("segment_growth", "positive", f"{_t(d).title()} '{bk}' grew {bv:.0f}%",
                                        f"{_t(m).title()} for '{bk}' rose {bv:.1f}% in {mv['period']} versus {mv['prior']}.",
                                        f"Double down on '{bk}': increase stock/marketing investment and replicate its playbook elsewhere.",
                                        6.5 - j, m, bv))

    # 3. Correlations
    if len(measures) >= 2:
        corr = stats.correlations(table, profile)
        facts["correlations"] = corr["pairs"][:8]
        shown = 0
        for p in corr["pairs"]:
            if shown >= 3 or abs(p["r"]) < 0.5 or abs(p["r"]) > 0.995 or not p["significant"]:
                continue
            shown += 1
            out.append(_insight("correlation", "info", f"{_t(p['a']).title()} and {_t(p['b'])} are {p['strength']}ly {'linked' if p['r'] > 0 else 'inversely linked'}",
                                f"Pearson r = {p['r']:.2f} (p < 0.05): when {_t(p['a'])} increases, {_t(p['b'])} tends to {'increase' if p['r'] > 0 else 'decrease'}.",
                                (f"Use {_t(p['a'])} as a leading indicator when planning {_t(p['b'])}; confirm cause and effect with a controlled test before changing policy."
                                 if p["r"] > 0 else f"Watch the trade-off: higher {_t(p['a'])} coincides with lower {_t(p['b'])} – review policies that push {_t(p['a'])} up."),
                                4.5 + abs(p["r"]), p["a"], p["r"]))

    # 4. Key drivers
    if measures and len(profile["columns"]) > 2:
        try:
            kd = ml.key_drivers(table, profile)
        except Exception:  # noqa: BLE001 - driver analysis is best-effort
            kd = {"available": False}
        if kd.get("available") and kd["drivers"]:
            facts["key_drivers"] = {"target": kd["target"], "drivers": kd["drivers"][:5]}
            top = kd["drivers"][0]
            out.append(_insight("driver", "info", f"Biggest driver of {_t(kd['target'])}: {_t(top['feature'])}",
                                f"A machine-learning model attributes {top['importance']:.0f}% of explained variation in {_t(kd['target'])} to {_t(top['feature'])}. {top['effect']}.",
                                f"Focus improvement initiatives on {_t(top['feature'])} first – it has the largest measured influence on {_t(kd['target'])}.",
                                6, kd["target"], top["importance"]))

    # 5. Anomalies (record level)
    if measures:
        an = ml.anomalies(table, profile)
        if an.get("available") and an["anomaly_count"]:
            facts["anomalies"] = {"count": an["anomaly_count"], "rate_pct": an["anomaly_rate_pct"],
                                  "examples": [a["reasons"] for a in an["top"][:3]]}
            out.append(_insight("anomaly", "warning", f"{an['anomaly_count']:,} unusual records detected",
                                f"Isolation-Forest analysis flagged {an['anomaly_rate_pct']:.1f}% of records as outliers. Example: {an['top'][0]['reasons'][0]}.",
                                "Review the flagged records in the Anomalies tab – they may indicate fraud, data-entry errors or exceptional events worth investigating.",
                                5, None, an["anomaly_count"]))

    # 6. Data quality
    if quality:
        facts["quality"] = {k: quality.get(k) for k in ("score_before", "score_after", "issues", "grade")}
        iss = quality.get("issues", {})
        fixed = iss.get("duplicates_removed", 0) + iss.get("inconsistent_values", 0) + iss.get("imputed_values", 0) + iss.get("invalid_values", 0)
        sev = "positive" if quality.get("score_before", 100) >= 90 else "warning"
        out.append(_insight("quality", sev, f"Data quality score {quality.get('score_before')} → {quality.get('score_after')} after ETL",
                            f"The pipeline fixed {fixed:,} issues: {iss.get('duplicates_removed', 0)} duplicates, {iss.get('inconsistent_values', 0)} inconsistent labels, "
                            f"{iss.get('invalid_values', 0)} invalid values and {iss.get('imputed_values', 0)} missing values.",
                            "Fix these problems at the source system (validation rules, dropdowns instead of free text) to make reporting more reliable."
                            if sev == "warning" else "Source data is in good shape – keep the automated quality checks running on every refresh.",
                            3 if sev == "positive" else 5.5, None, quality.get("score_before")))

    out.sort(key=lambda i: -i["score"])
    summary = executive_summary(out, profile)
    return {"insights": out, "summary": summary, "facts": facts,
            "recommendations": [{"title": i["title"], "action": i["recommendation"], "severity": i["severity"]} for i in out[:8]]}


def executive_summary(items: list[dict[str, Any]], profile: dict[str, Any]) -> str:
    if not items:
        return "Not enough structure was detected to produce insights. Add a date column or numeric measures for richer analysis."
    pos = [i for i in items if i["severity"] == "positive"]
    neg = [i for i in items if i["severity"] in {"negative", "warning"}]
    parts = [f"Analysis of {len(profile['columns'])} columns produced {len(items)} findings."]
    if pos:
        parts.append("Strengths: " + "; ".join(i["title"] for i in pos[:2]) + ".")
    if neg:
        parts.append("Areas needing attention: " + "; ".join(i["title"] for i in neg[:3]) + ".")
    top = items[0]
    parts.append(f"Top priority: {top['recommendation']}")
    return " ".join(parts)


AI_SYSTEM = (
    "You are a senior business analyst writing for executives who are not data experts. "
    "You receive statistical findings that were computed from a dataset. Use only these findings; "
    "never invent numbers. Be specific, quantitative and concise."
)


def ai_narrative(dataset_name: str, result: dict[str, Any]) -> str | None:
    """Ask Claude for an executive briefing based on computed findings (no raw data is sent)."""
    payload = {"dataset": dataset_name, "findings": result["insights"][:15], "facts": result["facts"]}
    prompt = (
        "Write an executive briefing in Markdown with these sections:\n"
        "## Executive summary (3-4 sentences)\n## Key findings (bullets, most important first)\n"
        "## Recommended actions (numbered, each tied to a finding, with expected impact)\n## Risks & watch-list\n\n"
        f"Findings JSON:\n{json.dumps(payload, default=str)[:60000]}"
    )
    return llm.complete(AI_SYSTEM, prompt, max_tokens=6000, effort="medium")
