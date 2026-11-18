"""Natural-language questions -> query.

Two engines:
* ``rules``  – a built-in semantic parser that maps words to columns, aggregations,
  groupings, time grains, filters and top-N, then reuses the chart query engine.
* ``ai``     – Claude translates the question into DuckDB SQL (validated read-only).
"""
from __future__ import annotations

import json
import re
from difflib import get_close_matches
from typing import Any

import pandas as pd

from .. import warehouse as wh
from ..ai import llm
from . import query as q
from .sqlguard import SQLGuardError, validate_select

SYNONYMS = {
    "sales": ["revenue", "sales", "amount", "total"], "revenue": ["revenue", "sales", "amount"],
    "earnings": ["profit", "revenue", "income"], "income": ["income", "profit", "revenue"],
    "money": ["revenue", "amount", "sales"], "units": ["quantity", "units", "qty"], "volume": ["quantity", "units", "orders"],
    "spend": ["spend", "cost", "budget"], "expense": ["cost", "spend", "expense"], "margin": ["profit", "margin"],
    "customers": ["customer_id", "customer"], "orders": ["order_id", "orders"], "rating": ["rating", "score", "satisfaction"],
}
AGG_WORDS = [
    (r"\b(average|avg|mean|typical)\b", "avg"), (r"\b(median)\b", "median"),
    (r"\b(how many|number of|count|# of)\b", "count"), (r"\b(unique|distinct)\b", "count_distinct"),
    (r"\b(maximum|max|highest value|largest)\b", "max"), (r"\b(minimum|min|lowest value|smallest)\b", "min"),
    (r"\b(total|sum|overall|altogether)\b", "sum"),
]
GRAIN_WORDS = [(r"\b(daily|per day|by day|each day)\b", "day"), (r"\b(weekly|per week|by week|each week)\b", "week"),
               (r"\b(monthly|per month|by month|each month|month over month|over time|trend|trends|timeline)\b", "month"),
               (r"\b(quarterly|per quarter|by quarter|each quarter)\b", "quarter"),
               (r"\b(yearly|annually|per year|by year|each year|year over year|annual)\b", "year")]


def _words(name: str) -> str:
    return name.replace("_", " ").lower()


def _find_columns(text: str, names: list[str]) -> list[tuple[int, str]]:
    """Return [(position, column)] for columns mentioned in the question."""
    hits: list[tuple[int, str]] = []
    for n in sorted(names, key=len, reverse=True):
        for variant in {_words(n), n.lower(), _words(n).rstrip("s")}:
            m = re.search(r"\b" + re.escape(variant) + r"s?\b", text)
            if m and not any(abs(m.start() - p) < 2 for p, _ in hits):
                hits.append((m.start(), n))
                break
    tokens = re.findall(r"[a-z_]+", text)
    for word, targets in SYNONYMS.items():
        if word in tokens and not any(word in _words(h[1]) for h in hits):
            for tgt in targets:
                match = next((n for n in names if tgt in n.lower()), None)
                if match:
                    if match not in [h[1] for h in hits]:
                        hits.append((text.find(word), match))
                    break
    for tok in tokens:
        if len(tok) < 4:
            continue
        close = get_close_matches(tok, [n.lower() for n in names], n=1, cutoff=0.85)
        if close:
            col = next(n for n in names if n.lower() == close[0])
            if col not in [h[1] for h in hits]:
                hits.append((text.find(tok), col))
    return sorted(hits)


def rules_parse(question: str, table: str, profile: dict[str, Any]) -> dict[str, Any]:
    text = question.lower().strip()
    cols = {c["name"]: c for c in profile["columns"]}
    measures, dims = profile["measures"], profile["dimensions"]
    t = profile.get("primary_time")

    agg = next((a for pat, a in AGG_WORDS if re.search(pat, text)), None)
    grain = next((g for pat, g in GRAIN_WORDS if re.search(pat, text)), None)
    limit = None
    order = None
    if m := re.search(r"\b(top|best|highest|most|largest|biggest)\s*(\d+)?", text):
        limit, order = (int(m.group(2)) if m.group(2) else 10), "y_desc"
    if m := re.search(r"\b(bottom|worst|lowest|least|smallest)\s*(\d+)?", text):
        limit, order = (int(m.group(2)) if m.group(2) else 10), "y_asc"

    mentioned = _find_columns(text, list(cols))
    m_cols = [c for _, c in mentioned if cols[c]["role"] == "measure"]
    d_cols = [c for _, c in mentioned if cols[c]["role"] in {"dimension", "identifier"}]

    group = None
    if g := re.search(r"\b(?:by|per|for each|across|split by|broken down by|grouped by|in each)\s+([a-z _]+)", text):
        after = g.group(1)
        cand = _find_columns(after, list(cols))
        if cand and cols[cand[0][1]]["role"] in {"dimension", "identifier", "time"}:
            group = cand[0][1]
    if not group and d_cols and (limit or re.search(r"\b(which|what|each|compare|breakdown|distribution|share)\b", text)):
        group = d_cols[0]
    if group and cols[group]["semantic_type"] == "datetime":
        grain = grain or "month"
        group = None

    # filters: category values literally present in the question
    filters: list[dict[str, Any]] = []
    matched: set[str] = set()
    for d in dims:
        if d == group or cols[d]["unique"] > 300:
            continue
        values = wh.query_df(f"SELECT DISTINCT CAST({wh.qi(d)} AS VARCHAR) AS v FROM {table} WHERE {wh.qi(d)} IS NOT NULL")["v"]
        for v in values:
            if len(str(v)) >= 2 and str(v).lower() not in matched and re.search(r"\b" + re.escape(str(v).lower()) + r"\b", text):
                filters.append({"column": d, "op": "eq", "value": v})
                matched.add(str(v).lower())
                break
    if t and (yr := re.search(r"\b(19|20)\d{2}\b", text)):
        y = yr.group(0)
        filters.append({"column": t, "op": "between", "value": [f"{y}-01-01", f"{y}-12-31"]})

    if agg == "count" and not m_cols:
        y = [{"column": "*", "agg": "count", "label": "count"}]
    elif agg == "count_distinct" and (d_cols or mentioned):
        target = next((c for c in d_cols if c != group), d_cols[0] if d_cols else mentioned[0][1])
        y = [{"column": target, "agg": "count_distinct", "label": f"unique_{target}"}]
    else:
        measure = m_cols[0] if m_cols else profile.get("primary_measure")
        if not measure:
            y = [{"column": "*", "agg": "count", "label": "count"}]
        else:
            a = agg if agg in q.AGGS and agg not in {"count_distinct"} else cols[measure].get("default_agg", "sum")
            y = [{"column": measure, "agg": a}]

    x = None
    if grain and t:
        x = t
        if group:
            spec = {"x": t, "series": group, "y": y, "time_grain": grain, "filters": filters}
            return {"spec": spec, "chart": "line"}
    elif group:
        x = group
    spec = {"x": x, "y": y, "time_grain": grain, "filters": filters}
    if limit or (x and x != t):
        spec["limit"] = limit or 25
    if order:
        spec["sort"] = order
    chart = "line" if (x and x == t) else ("bar" if x else "kpi")
    if x and x != t and cols[x]["unique"] <= 6 and re.search(r"\b(share|proportion|percentage|split|distribution)\b", text):
        chart = "pie"
    return {"spec": spec, "chart": chart}


def _num(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def describe_answer(question: str, result: dict[str, Any], chart: str, additive: bool = True) -> str:
    rows = result["rows"]
    if not rows:
        return "No data matched your question."
    y = result["y"][0]
    if chart == "kpi":
        v = rows[0].get(y)
        return f"The answer is **{_num(v)}**." if isinstance(v, (int, float)) else f"The answer is **{v}**."
    x = result["x"]
    if result.get("is_time"):
        first, last = rows[0], rows[-1]
        if len(result["y"]) == 1 and isinstance(first.get(y), (int, float)) and isinstance(last.get(y), (int, float)) and first[y]:
            chg = (last[y] - first[y]) / abs(first[y]) * 100
            peak = max(rows, key=lambda r: r.get(y) or float("-inf"))
            return (f"{y.replace('_', ' ').title()} went from {_num(first[y])} ({first[x]}) to {_num(last[y])} ({last[x]}), "
                    f"a {chg:+.1f}% change across {len(rows)} periods. The peak was {_num(peak[y])} in {peak[x]}.")
        return f"Showing {len(rows)} periods for {len(result['y'])} series."
    top = rows[0]
    val = top.get(y)
    total = sum(r.get(y) or 0 for r in rows if isinstance(r.get(y), (int, float)))
    share = f" ({val / total * 100:.1f}% of the shown total)" if additive and isinstance(val, (int, float)) and total else ""
    if not isinstance(val, (int, float)):
        return f"{len(rows)} rows returned."
    last = rows[-1]
    tail = f" and **{last.get(x)}** is last with {_num(last.get(y))}" if len(rows) > 1 and isinstance(last.get(y), (int, float)) else ""
    return f"**{top.get(x)}** ranks first with {_num(val)}{share}{tail}; {len(rows)} groups shown."


NLQ_SYSTEM = (
    "You translate business questions into a single DuckDB SQL SELECT statement. "
    "Rules: read-only SELECT only; use only the provided table and columns; quote identifiers with double quotes; "
    "use date_trunc for time grouping; alias aggregates with readable snake_case names; add ORDER BY and LIMIT 200 when appropriate. "
    'Respond with JSON only: {"sql": "...", "chart": "bar|line|pie|kpi|table|scatter", "x": "<column alias for x axis or null>", '
    '"y": ["<numeric column aliases>"], "explanation": "<one sentence on how the question was interpreted>"}'
)


def ai_answer(question: str, table: str, profile: dict[str, Any], allowed: set[str]) -> dict[str, Any] | None:
    schema = [{"name": c["name"], "type": c["semantic_type"], "role": c["role"],
               "examples": c.get("sample_values", [])[:3]} for c in profile["columns"]]
    prompt = f"Table: {table}\nColumns: {json.dumps(schema)}\nQuestion: {question}"
    raw = llm.complete(NLQ_SYSTEM, prompt, max_tokens=4000, effort="low")
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        plan = json.loads(m.group(0))
        sql = validate_select(plan["sql"], allowed)
        df = wh.query_df(f"SELECT * FROM ({sql}) AS q LIMIT 1000")
    except (json.JSONDecodeError, KeyError, SQLGuardError, Exception):  # noqa: BLE001 - fall back to rules engine
        return None
    rows = wh.to_records(df)
    cols = list(df.columns)
    num = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
    x = plan.get("x") if plan.get("x") in cols else next((c for c in cols if c not in num), None)
    y = [c for c in (plan.get("y") or num) if c in cols] or num
    chart = plan.get("chart", "table")
    if chart == "kpi" and len(rows) != 1:
        chart = "table"
    is_time = bool(x and pd.api.types.is_datetime64_any_dtype(df[x]))
    result = {"x": x, "y": y, "rows": rows, "is_time": is_time, "sql": sql, "columns": cols}
    narrative = llm.complete(
        "You are a data analyst. Answer the user's question in 1-3 sentences using only the query result provided. Use Markdown bold for key numbers.",
        f"Question: {question}\nSQL: {sql}\nResult (first rows): {json.dumps(rows[:40], default=str)}",
        max_tokens=1500, effort="low",
    )
    return {"mode": "ai", "chart": chart, "result": result, "explanation": plan.get("explanation", ""),
            "answer": narrative or describe_answer(question, result, chart)}


def answer(question: str, table: str, profile: dict[str, Any], allowed: set[str], use_ai: bool = True) -> dict[str, Any]:
    if use_ai and llm.available():
        res = ai_answer(question, table, profile, allowed)
        if res:
            return res
    parsed = rules_parse(question, table, profile)
    spec, chart = parsed["spec"], parsed["chart"]
    result = q.run_chart_query(table, profile, spec)
    result["columns"] = ([result["x"]] if result["x"] else []) + result["y"]
    parts = [f"{y['agg']} of {y['column']}" if y["column"] != "*" else "count of records" for y in spec["y"]]
    expl = "Interpreted as " + ", ".join(parts)
    if spec.get("x"):
        expl += f" grouped by {spec['x']}" + (f" ({spec['time_grain']})" if spec.get("time_grain") and spec["x"] == profile.get("primary_time") else "")
    if spec.get("series"):
        expl += f" and split by {spec['series']}"
    if spec.get("filters"):
        expl += " where " + " and ".join(f"{f['column']} {'= ' + str(f['value']) if f['op'] == 'eq' else 'in ' + ' to '.join(f['value'])}" for f in spec["filters"])
    return {"mode": "rules", "chart": chart, "result": result, "spec": spec, "explanation": expl + ".",
            "answer": describe_answer(question, result, chart, additive=spec["y"][0]["agg"] in {"sum", "count"})}
