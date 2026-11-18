"""Descriptive statistics, distributions and correlation analysis."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sps

from .. import warehouse as wh

MAX_ROWS = 200_000


def load(table: str, columns: list[str] | None = None, sample: int = MAX_ROWS) -> pd.DataFrame:
    cols = ", ".join(wh.qi(c) for c in columns) if columns else "*"
    n = wh.query_df(f"SELECT count(*) AS n FROM {wh.safe_table(table)}")["n"].iloc[0]
    if n > sample:
        return wh.query_df(f"SELECT {cols} FROM {wh.safe_table(table)} USING SAMPLE {int(sample)} ROWS (reservoir, 42)")
    return wh.query_df(f"SELECT {cols} FROM {wh.safe_table(table)}")


def compact(v: float) -> str:
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:.1f}B"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e4:
        return f"{v / 1e3:.0f}K"
    if a >= 100:
        return f"{v:,.0f}"
    return f"{v:.3g}"


def _f(v: Any) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) or np.isinf(v) else round(v, 6)


def distributions(table: str, profile: dict[str, Any], max_cols: int = 12) -> list[dict[str, Any]]:
    cols = {c["name"]: c for c in profile["columns"]}
    targets = profile["measures"][:max_cols] + profile["dimensions"][:max_cols]
    df = load(table, targets) if targets else pd.DataFrame()
    out = []
    for name in targets:
        col = cols[name]
        s = df[name].dropna()
        if col["role"] == "measure":
            x = s.astype(float)
            if x.empty:
                continue
            counts, edges = np.histogram(x, bins=min(24, max(5, int(np.sqrt(len(x))))))
            out.append({
                "column": name, "kind": "histogram", "semantic_type": col["semantic_type"],
                "bins": [{"start": _f(edges[i]), "end": _f(edges[i + 1]), "label": f"{compact(edges[i])}–{compact(edges[i + 1])}", "count": int(c)}
                         for i, c in enumerate(counts)],
                "skew": _f(x.skew()), "kurtosis": _f(x.kurt()),
                "shape": "right-skewed" if x.skew() > 1 else "left-skewed" if x.skew() < -1 else "approximately symmetric",
            })
        else:
            vc = s.astype(str).value_counts()
            top = vc.head(15)
            other = int(vc.iloc[15:].sum())
            bars = [{"label": k, "count": int(v)} for k, v in top.items()]
            if other:
                bars.append({"label": "Other", "count": other})
            out.append({"column": name, "kind": "categorical", "semantic_type": col["semantic_type"], "bins": bars,
                        "unique": int(vc.size), "dominant_share": _f(vc.iloc[0] / vc.sum() * 100) if len(vc) else None})
    return out


def correlations(table: str, profile: dict[str, Any], method: str = "pearson", max_cols: int = 15) -> dict[str, Any]:
    measures = profile["measures"][:max_cols]
    if len(measures) < 2:
        return {"columns": measures, "matrix": [], "pairs": []}
    df = load(table, measures).astype(float)
    df = df.loc[:, df.std() > 0]
    measures = list(df.columns)
    corr = df.corr(method=method)
    pairs = []
    for i, a in enumerate(measures):
        for b in measures[i + 1:]:
            r = corr.loc[a, b]
            if pd.isna(r):
                continue
            sub = df[[a, b]].dropna()
            p = sps.pearsonr(sub[a], sub[b]).pvalue if method == "pearson" and len(sub) > 2 else sps.spearmanr(sub[a], sub[b]).pvalue if len(sub) > 2 else 1.0
            strength = "very strong" if abs(r) >= 0.8 else "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.4 else "weak" if abs(r) >= 0.2 else "negligible"
            pairs.append({"a": a, "b": b, "r": _f(r), "p_value": _f(p), "strength": strength,
                          "direction": "positive" if r > 0 else "negative", "significant": bool(p < 0.05)})
    pairs.sort(key=lambda d: -abs(d["r"] or 0))
    return {
        "method": method,
        "columns": measures,
        "matrix": [[_f(corr.loc[a, b]) for b in measures] for a in measures],
        "pairs": pairs,
    }


def summary(table: str, profile: dict[str, Any]) -> dict[str, Any]:
    measures = profile["measures"]
    cols = {c["name"]: c for c in profile["columns"]}
    rows = []
    for m in measures:
        st = cols[m].get("stats") or {}
        mean, std = st.get("mean") or 0, st.get("std") or 0
        rows.append({"column": m, **st, "cv": _f(std / abs(mean)) if mean else None, "semantic_type": cols[m]["semantic_type"],
                     "default_agg": cols[m].get("default_agg")})
    return {"measures": rows, "dimensions": [cols[d] for d in profile["dimensions"]]}


def scatter(table: str, profile: dict[str, Any], x: str, y: str, color: str | None = None, n: int = 800) -> dict[str, Any]:
    cols = {c["name"] for c in profile["columns"]}
    for c in filter(None, [x, y, color]):
        if c not in cols:
            raise ValueError(f"Unknown column {c}")
    select = [x, y] + ([color] if color else [])
    df = load(table, select, sample=n).dropna(subset=[x, y])
    out = {"x": x, "y": y, "color": color, "points": wh.to_records(df)}
    if len(df) > 2:
        lr = sps.linregress(df[x].astype(float), df[y].astype(float))
        out["regression"] = {"slope": _f(lr.slope), "intercept": _f(lr.intercept), "r2": _f(lr.rvalue ** 2)}
    return out
