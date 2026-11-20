"""Automatic dashboard generation: choose KPIs and chart types from the inferred schema."""
from __future__ import annotations

import uuid
from typing import Any

from . import query as q
from . import stats


def _wid() -> str:
    return uuid.uuid4().hex[:10]


def _fmt(col: dict[str, Any]) -> str:
    return {"currency": "currency", "percentage": "percent"}.get(col["semantic_type"], "number")


def _title(name: str) -> str:
    return name.replace("_", " ").title()


def generate(table: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    cols = {c["name"]: c for c in profile["columns"]}
    measures = profile["measures"]
    dims = [d for d in profile["dimensions"] if 2 <= cols[d]["unique"] <= 60]
    t = profile.get("primary_time")
    widgets: list[dict[str, Any]] = []
    additive = next((m for m in measures if cols[m].get("default_agg") == "sum"), None)
    share_y = [{"column": additive, "agg": "sum"}] if additive else [{"column": "*", "agg": "count"}]
    share_label = _title(additive) if additive else "Records"

    # --- KPI row -------------------------------------------------------------
    widgets.append({"id": _wid(), "type": "kpi", "title": "Total Records", "w": 1,
                    "spec": {"column": "*", "agg": "count", "format": "number"}})
    for m in measures[:3]:
        agg = cols[m].get("default_agg", "sum")
        widgets.append({"id": _wid(), "type": "kpi", "w": 1,
                        "title": f"{'Average' if agg == 'avg' else 'Total'} {_title(m)}",
                        "spec": {"column": m, "agg": agg, "format": _fmt(cols[m])}})

    # --- Trends --------------------------------------------------------------
    if t and measures:
        m0 = measures[0]
        widgets.append({"id": _wid(), "type": "area", "w": 3, "title": f"{_title(m0)} Over Time",
                        "spec": {"x": t, "y": [{"column": m0, "agg": cols[m0].get("default_agg", "sum")}], "time_grain": "month"}})
        if dims:
            widgets.append({"id": _wid(), "type": "donut", "w": 1, "title": f"{share_label} Share by {_title(dims[0])}",
                            "spec": {"x": dims[0], "y": share_y, "limit": 8}})
        if len(measures) > 1:
            m1 = measures[1]
            widgets.append({"id": _wid(), "type": "line", "w": 2, "title": f"{_title(m1)} Trend",
                            "spec": {"x": t, "y": [{"column": m1, "agg": cols[m1].get("default_agg", "sum")}], "time_grain": "month"}})
        if dims:
            d = dims[1] if len(dims) > 1 else dims[0]
            widgets.append({"id": _wid(), "type": "stacked_bar", "w": 2, "title": f"{share_label} by {_title(d)} Over Time",
                            "spec": {"x": t, "series": d, "y": share_y, "time_grain": "quarter"}})
    elif t:
        widgets.append({"id": _wid(), "type": "area", "w": 4, "title": "Records Over Time",
                        "spec": {"x": t, "y": [{"column": "*", "agg": "count"}], "time_grain": "month"}})

    # --- Category comparisons ----------------------------------------------
    m0 = measures[0] if measures else None
    for d in dims[:3]:
        y = [{"column": m0, "agg": cols[m0].get("default_agg", "sum")}] if m0 else [{"column": "*", "agg": "count"}]
        widgets.append({"id": _wid(), "type": "hbar" if cols[d]["unique"] > 6 else "bar", "w": 2,
                        "title": f"{_title(m0) if m0 else 'Records'} by {_title(d)}",
                        "spec": {"x": d, "y": y, "limit": 12}})
    if not t and dims:
        widgets.append({"id": _wid(), "type": "pie", "w": 2, "title": f"Distribution of {_title(dims[0])}",
                        "spec": {"x": dims[0], "y": [{"column": "*", "agg": "count"}], "limit": 8}})

    # --- Distribution, relationships --------------------------------------
    if measures:
        widgets.append({"id": _wid(), "type": "histogram", "w": 2, "title": f"Distribution of {_title(measures[0])}",
                        "spec": {"column": measures[0]}})
    if len(measures) >= 2:
        corr = stats.correlations(table, profile)
        # the most informative pair: strong but not a near-identity (e.g. unit vs list price)
        pair = next((p for p in corr["pairs"] if 0.3 <= abs(p["r"] or 0) < 0.95), None) or \
            next((p for p in corr["pairs"] if abs(p["r"] or 0) < 0.999), None)
        if pair:
            widgets.append({"id": _wid(), "type": "scatter", "w": 2, "title": f"{_title(pair['a'])} vs {_title(pair['b'])} (r = {pair['r']:.2f})",
                            "spec": {"x": pair["a"], "y": pair["b"], "color": dims[0] if dims and cols[dims[0]]["unique"] <= 8 else None}})
        if len(measures) >= 3:
            widgets.append({"id": _wid(), "type": "heatmap", "w": 2, "title": "Correlation Matrix", "spec": {}})

    # --- Detail table --------------------------------------------------------
    show = (profile["identifiers"][:1] + ([t] if t else []) + dims[:3] + measures[:4])
    widgets.append({"id": _wid(), "type": "table", "w": 4, "title": f"Top Records by {_title(m0)}" if m0 else "Sample Records",
                    "spec": {"columns": list(dict.fromkeys(show)) or None, "order_by": m0, "limit": 10}})
    return widgets


TIME_ALIAS = "__time__"  # dashboard filter meaning "this dataset's primary date column"


def applicable_filters(profile: dict[str, Any], filters: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Map dashboard-level filters onto one dataset.

    On a combined (multi-dataset) dashboard a filter may name a column that only some datasets
    have; those widgets simply ignore it. ``__time__`` resolves to each dataset's primary date."""
    names = {c["name"] for c in profile.get("columns", [])}
    keep, ignored = [], []
    for f in filters or []:
        col = f.get("column")
        if col == TIME_ALIAS:
            t = profile.get("primary_time")
            if t:
                keep.append({**f, "column": t})
            else:
                ignored.append("date range")
        elif col in names:
            keep.append(f)
        else:
            ignored.append(str(col))
    return keep, ignored


def compact(table: str, profile: dict[str, Any], dataset_id: int) -> list[dict[str, Any]]:
    """A short per-dataset block for combined dashboards: 2 KPIs, the main trend and the main breakdown."""
    full = generate(table, profile)
    picked: list[dict[str, Any]] = []
    # row 1: KPI cards spread across the full width (widths always sum to 4)
    kpis = [w for w in full if w["type"] == "kpi"][:4]
    widths = {1: [4], 2: [2, 2], 3: [1, 1, 2], 4: [1, 1, 1, 1]}.get(len(kpis), [])
    picked += [{**w, "w": wd} for w, wd in zip(kpis, widths)]
    # row 2: main trend + main breakdown side by side (or one full-width chart)
    trend = next((w for w in full if w["type"] in {"area", "line"}), None)
    breakdown = next((w for w in full if w["type"] in {"bar", "hbar", "donut", "pie"}), None)
    charts = [c for c in (trend, breakdown) if c] or [w for w in full if w["type"] in {"histogram", "table"}][:1]
    picked += [{**c, "w": 2 if len(charts) == 2 else 4} for c in charts]
    for w in picked:
        w["dataset_id"] = dataset_id
    return picked


def section(title: str, subtitle: str, dataset_id: int | None) -> dict[str, Any]:
    return {"id": _wid(), "type": "section", "title": title, "w": 4, "spec": {"subtitle": subtitle}, "dataset_id": dataset_id}


def generate_combined(datasets: list[Any], integrated: Any | None = None) -> list[dict[str, Any]]:
    """Widgets for a multi-dataset dashboard. Every widget carries the ``dataset_id`` it reads from."""
    widgets: list[dict[str, Any]] = []
    if integrated is not None:
        widgets.append(section(f"{integrated.name}", f"Cross-file view · {integrated.row_count:,} rows joined from the linked files", integrated.id))
        for w in generate(integrated.table_name, integrated.profile):
            if w["type"] == "table":
                continue
            w["dataset_id"] = integrated.id
            widgets.append(w)
    for d in datasets:
        if integrated is not None and d.id == integrated.id:
            continue
        widgets.append(section(d.name, f"{d.row_count:,} rows · {d.column_count} columns", d.id))
        widgets.extend(compact(d.table_name, d.profile, d.id))
    return widgets


def widget_data(table: str, profile: dict[str, Any], widget: dict[str, Any], filters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Resolve any widget type to its data, applying dashboard-level filters."""
    out = _widget_data(table, profile, widget, filters)
    _, ignored = applicable_filters(profile, filters)
    if ignored and isinstance(out, dict):
        out["filters_ignored"] = ignored
    return out


def _widget_data(table: str, profile: dict[str, Any], widget: dict[str, Any], filters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    wtype = widget.get("type")
    if wtype == "section":
        return {}
    spec = dict(widget.get("spec") or {})
    spec["filters"] = list(spec.get("filters") or []) + applicable_filters(profile, filters)[0]
    if wtype == "kpi":
        return q.run_kpi_query(table, profile, spec)
    if wtype == "table":
        return q.run_table_query(table, profile, spec)
    if wtype == "histogram":
        import numpy as np

        from .. import warehouse as wh
        cols = {c["name"]: c for c in profile["columns"]}
        col = spec["column"]
        if col not in cols:
            raise q.QueryError(f"Unknown column {col}")
        where, params = q.build_where(spec["filters"], cols)
        x = wh.query_df(f"SELECT {wh.qi(col)} AS v FROM {wh.safe_table(table)}{where}", params)["v"].dropna().astype(float)
        if x.empty:
            return {"rows": []}
        counts, edges = np.histogram(x, bins=min(24, max(5, int(np.sqrt(len(x))))))
        return {"rows": [{"bin": f"{stats.compact(edges[i])}–{stats.compact(edges[i + 1])}", "count": int(c)} for i, c in enumerate(counts)],
                "x": "bin", "y": ["count"]}
    if wtype == "scatter":
        from .. import warehouse as wh
        cols = {c["name"]: c for c in profile["columns"]}
        sel = [spec["x"], spec["y"]] + ([spec["color"]] if spec.get("color") else [])
        for c in sel:
            if c not in cols:
                raise q.QueryError(f"Unknown column {c}")
        where, params = q.build_where(spec["filters"], cols)
        df = wh.query_df(f"SELECT * FROM (SELECT {', '.join(wh.qi(c) for c in sel)} FROM {wh.safe_table(table)}{where}) "
                         "USING SAMPLE 600 ROWS (reservoir, 7)", params)
        return {"rows": wh.to_records(df.dropna()), "x": spec["x"], "y": [spec["y"]], "color": spec.get("color")}
    if wtype == "heatmap":
        return stats.correlations(table, profile)
    return q.run_chart_query(table, profile, spec)
