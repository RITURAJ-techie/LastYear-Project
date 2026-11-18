"""Safe, declarative query engine used by charts, dashboards and the chart builder.

A chart is described by a JSON spec which is validated against the dataset
schema and compiled into parameterised DuckDB SQL (no string-built user values).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .. import warehouse as wh

AGGS = {
    "sum": "sum({c})", "avg": "avg({c})", "min": "min({c})", "max": "max({c})", "median": "median({c})",
    "count": "count({c})", "count_distinct": "count(DISTINCT {c})", "stddev": "stddev_samp({c})",
}
GRAINS = {"day", "week", "month", "quarter", "year"}
OPS = {"eq": "=", "neq": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


class QueryError(ValueError):
    pass


def _columns(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in profile.get("columns", [])}


def _check(col: str, cols: dict[str, Any]) -> str:
    if col not in cols:
        raise QueryError(f"Unknown column '{col}'")
    return wh.qi(col)


def build_where(filters: list[dict[str, Any]] | None, cols: dict[str, Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for f in filters or []:
        col = f.get("column")
        op = f.get("op", "eq")
        val = f.get("value")
        if col is None or val is None or val == "" or val == []:
            continue
        c = _check(col, cols)
        is_time = cols[col].get("semantic_type") == "datetime"
        if op in OPS:
            clauses.append(f"{c} {OPS[op]} ?")
            params.append(val)
        elif op == "in":
            vals = val if isinstance(val, list) else [val]
            clauses.append(f"CAST({c} AS VARCHAR) IN ({', '.join('?' for _ in vals)})")
            params.extend([str(v) for v in vals])
        elif op == "between":
            lo, hi = (val + [None, None])[:2] if isinstance(val, list) else (None, None)
            if lo not in (None, ""):
                clauses.append(f"{c} >= CAST(? AS TIMESTAMP)" if is_time else f"{c} >= ?")
                params.append(lo)
            if hi not in (None, ""):
                clauses.append(f"{c} < CAST(? AS DATE) + INTERVAL 1 DAY" if is_time else f"{c} <= ?")
                params.append(hi)
        elif op == "contains":
            clauses.append(f"CAST({c} AS VARCHAR) ILIKE ?")
            params.append(f"%{val}%")
        else:
            raise QueryError(f"Unsupported filter operator '{op}'")
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def run_chart_query(table: str, profile: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    cols = _columns(profile)
    table = wh.safe_table(table)
    x = spec.get("x")
    series = spec.get("series")
    grain = spec.get("time_grain")
    measures = spec.get("y") or [{"column": "*", "agg": "count"}]
    limit = max(1, min(int(spec.get("limit") or 50), 5000))

    select, group = [], []
    x_alias = None
    pos = 0
    if x:
        xc = _check(x, cols)
        if cols[x].get("semantic_type") == "datetime":
            grain = grain if grain in GRAINS else "month"
            select.append(f"date_trunc('{grain}', {xc}) AS {wh.qi(x)}")
        else:
            select.append(f"{xc} AS {wh.qi(x)}")
        pos += 1
        group.append(str(pos))  # positional: an alias shadowing a column name is ambiguous in GROUP BY
        x_alias = x
    if series:
        sc = _check(series, cols)
        select.append(f"CAST({sc} AS VARCHAR) AS __series")
        pos += 1
        group.append(str(pos))
    y_names = []
    for m in measures:
        col, agg = m.get("column", "*"), m.get("agg", "sum")
        if agg not in AGGS:
            raise QueryError(f"Unsupported aggregation '{agg}'")
        if col == "*" or col is None:
            expr, label = "count(*)", "count"
        else:
            expr = AGGS[agg].format(c=_check(col, cols))
            label = f"{agg}_{col}" if agg != "sum" else col
        label = m.get("label") or label
        y_names.append(label)
        select.append(f"{expr} AS {wh.qi(label)}")

    where, params = build_where(spec.get("filters"), cols)
    sql = f"SELECT {', '.join(select)} FROM {table}{where}"
    if x:
        sql += f" AND {wh.qi(x)} IS NOT NULL" if where else f" WHERE {wh.qi(x)} IS NOT NULL"
    if group:
        sql += " GROUP BY " + ", ".join(group)
    is_time = bool(x and cols[x].get("semantic_type") == "datetime")
    sort = spec.get("sort") or ("x" if is_time else "y_desc")
    if x and sort == "x":
        sql += " ORDER BY 1"
    elif y_names and sort in {"y_desc", "y_asc"}:
        sql += f" ORDER BY {pos + 1} {'DESC' if sort == 'y_desc' else 'ASC'} NULLS LAST"
    if is_time and not spec.get("limit"):
        limit = 5000
    if not series:
        sql += f" LIMIT {limit}"

    df = wh.query_df(sql, params)

    series_keys: list[str] = []
    if series and x:
        top = df.groupby("__series")[y_names[0]].sum().sort_values(ascending=False).head(8).index.tolist()
        df = df[df["__series"].isin(top)]
        wide = df.pivot_table(index=x, columns="__series", values=y_names[0], aggfunc="sum").reset_index()
        if is_time:
            wide = wide.sort_values(x)
        else:
            wide["__t"] = wide[top].sum(axis=1)
            wide = wide.sort_values("__t", ascending=False).drop(columns="__t").head(limit)
        df = wide
        series_keys = [str(s) for s in top]
        df.columns = [str(c) for c in df.columns]
    return {
        "x": x_alias,
        "y": series_keys or y_names,
        "series": series,
        "is_time": is_time,
        "rows": wh.to_records(df),
        "sql": sql,
    }


def run_table_query(table: str, profile: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    cols = _columns(profile)
    chosen = [c for c in (spec.get("columns") or list(cols)[:12]) if c in cols]
    where, params = build_where(spec.get("filters"), cols)
    order = spec.get("order_by")
    sql = f"SELECT {', '.join(wh.qi(c) for c in chosen)} FROM {wh.safe_table(table)}{where}"
    if order and order in cols:
        sql += f" ORDER BY {wh.qi(order)} {'ASC' if spec.get('ascending') else 'DESC'} NULLS LAST"
    sql += f" LIMIT {max(1, min(int(spec.get('limit') or 20), 1000))}"
    df = wh.query_df(sql, params)
    return {"columns": chosen, "rows": wh.to_records(df), "sql": sql}


def run_kpi_query(table: str, profile: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Single aggregated value + comparison with the previous equivalent period."""
    cols = _columns(profile)
    col, agg = spec.get("column", "*"), spec.get("agg", "count")
    expr = "count(*)" if col in ("*", None) else AGGS[agg].format(c=_check(col, cols))
    where, params = build_where(spec.get("filters"), cols)
    value = wh.query_df(f"SELECT {expr} AS v FROM {wh.safe_table(table)}{where}", params)["v"].iloc[0]
    from .insights import LOWER_IS_BETTER

    out: dict[str, Any] = {"value": None if pd.isna(value) else float(value),
                           "lower_is_better": bool(col not in ("*", None) and LOWER_IS_BETTER.search(col))}
    t = profile.get("primary_time")
    if t and spec.get("compare", True):
        tc = wh.qi(t)
        grain = spec.get("compare_grain", "month")
        q = (f"WITH b AS (SELECT date_trunc('{grain}', {tc}) AS p, {expr} AS v FROM {wh.safe_table(table)}{where}"
             f"{' AND' if where else ' WHERE'} {tc} IS NOT NULL GROUP BY 1) SELECT p, v FROM b ORDER BY p")
        ts = wh.query_df(q, params)
        if len(ts) >= 4:
            # if the latest period looks incomplete (far below the recent average of an additive
            # metric) compare the last two *complete* periods instead
            additive = col in ("*", None) or agg in {"sum", "count"}
            partial = additive and ts["v"].iloc[-1] < 0.6 * ts["v"].iloc[-4:-1].mean()
            end = len(ts) - 1 if partial else len(ts)
            cur, prev = ts["v"].iloc[end - 1], ts["v"].iloc[end - 2]
            out["period"] = str(pd.Timestamp(ts["p"].iloc[end - 1]).date())
            out["current"] = float(cur)
            out["previous"] = float(prev)
            out["change_pct"] = float((cur - prev) / abs(prev) * 100) if prev else None
            out["sparkline"] = [float(v) if pd.notna(v) else None for v in ts["v"].iloc[:end].tail(12)]
    return out
