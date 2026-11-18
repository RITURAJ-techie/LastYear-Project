"""Schema understanding: semantic type inference, column roles and data-quality scoring."""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

ID_NAME = re.compile(r"(^id$|_id$|^id_|uuid|guid|_key$|^key$|_code$|^code$|_no$|_number$|^sku$|^zip|postal|phone)", re.I)
MEAN_NAME = re.compile(r"(rate|ratio|percent|pct|price|score|rating|age|avg|mean|margin|days|duration|temp|latitude|longitude|lat$|lon$|lng$|discount|satisfaction|nps|tenure|salary|per_)", re.I)
CURRENCY_NAME = re.compile(r"(revenue|sales|amount|price|cost|profit|income|spend|budget|salary|value|fee|payment|total|gmv|usd|inr|eur)", re.I)
GEO_NAME = re.compile(r"(country|state|city|region|province|territory|continent|location|district|zone|area)", re.I)
TIME_NAME = re.compile(r"(date|time|month|day|period|timestamp|created|updated|_at$|_on$)", re.I)
YEAR_NAME = re.compile(r"(^year$|_year$|^yr$|fiscal_year|^fy$)", re.I)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PRIORITY_MEASURE = ["revenue", "sales", "profit", "amount", "total", "income", "spend", "cost", "quantity", "units", "orders", "price", "value", "count"]


def _is_text(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)


def infer_semantic(name: str, s: pd.Series) -> tuple[str, str]:
    """Return (semantic_type, role) for a cleaned column."""
    non_null = s.dropna()
    n = len(non_null)
    unique = non_null.nunique() if n else 0
    ratio = unique / n if n else 0.0

    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", "time"
    if pd.api.types.is_bool_dtype(s):
        return "boolean", "dimension"
    if pd.api.types.is_numeric_dtype(s):
        is_int = n > 0 and bool(np.all(np.mod(non_null.astype(float), 1) == 0))
        if YEAR_NAME.search(name) and is_int and n and non_null.between(1900, 2100).all():
            return "year", "time"
        if ID_NAME.search(name) and is_int and (ratio > 0.5 or unique > 50):
            return "identifier", "identifier"
        if is_int and unique <= 2 and set(non_null.unique()).issubset({0, 1}):
            return "boolean", "dimension"
        if re.search(r"(percent|pct|rate|ratio|margin)", name, re.I):
            return "percentage", "measure"
        if CURRENCY_NAME.search(name):
            return "currency", "measure"
        if is_int and re.search(r"(qty|quantity|count|units|num|visits|clicks|orders|items|leads|impressions)", name, re.I):
            return "count", "measure"
        return "numeric", "measure"
    if _is_text(s):
        strs = non_null.astype(str)
        avg_len = strs.str.len().mean() if n else 0
        if n and strs.head(200).str.match(EMAIL_RE).mean() > 0.9:
            return "email", "identifier"
        if ID_NAME.search(name) and (ratio > 0.5 or unique > 50):
            return "identifier", "identifier"
        if GEO_NAME.search(name) and ratio < 0.5:
            return "geo", "dimension"
        if unique <= max(30, int(0.05 * n)) and ratio < 0.5:
            return "categorical", "dimension"
        if ratio > 0.9 and avg_len < 40:
            return "identifier", "identifier"
        if avg_len >= 40:
            return "text", "text"
        return "categorical", "dimension"
    return "unknown", "dimension"


def default_aggregation(name: str, semantic: str) -> str:
    if semantic in {"percentage"} or MEAN_NAME.search(name):
        return "avg"
    return "sum"


def _num(v: Any) -> Any:
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return round(float(v), 6)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return v


def profile_column(name: str, s: pd.Series) -> dict[str, Any]:
    semantic, role = infer_semantic(name, s)
    n = len(s)
    missing = int(s.isna().sum())
    non_null = s.dropna()
    info: dict[str, Any] = {
        "name": name,
        "dtype": str(s.dtype),
        "semantic_type": semantic,
        "role": role,
        "missing": missing,
        "missing_pct": round(100 * missing / n, 2) if n else 0.0,
        "unique": int(non_null.nunique()),
        "unique_pct": round(100 * non_null.nunique() / max(len(non_null), 1), 2),
        "sample_values": [str(v) for v in non_null.drop_duplicates().head(5).tolist()],
    }
    if role == "measure" or (pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)):
        x = pd.to_numeric(non_null, errors="coerce").dropna().astype(float)
        if len(x):
            q1, q3 = np.percentile(x, [25, 75])
            iqr = q3 - q1
            outliers = int(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)).sum()) if iqr > 0 else 0
            info["stats"] = {
                "min": _num(x.min()), "max": _num(x.max()), "mean": _num(x.mean()), "median": _num(x.median()),
                "std": _num(x.std(ddof=1)) if len(x) > 1 else 0.0, "q1": _num(q1), "q3": _num(q3),
                "sum": _num(x.sum()), "skew": _num(x.skew()) if len(x) > 2 else 0.0, "outliers": outliers,
                "zeros": int((x == 0).sum()),
            }
        info["default_agg"] = default_aggregation(name, semantic)
    if role in {"dimension", "identifier"} and not pd.api.types.is_numeric_dtype(s):
        vc = non_null.astype(str).value_counts().head(10)
        info["top_values"] = [{"value": k, "count": int(v)} for k, v in vc.items()]
    if role == "time" and pd.api.types.is_datetime64_any_dtype(s) and len(non_null):
        info["stats"] = {"min": non_null.min().isoformat(), "max": non_null.max().isoformat(),
                         "span_days": int((non_null.max() - non_null.min()).days)}
    return info


def measure_priority(col: dict[str, Any]) -> tuple[int, float]:
    name = col["name"].lower()
    for i, kw in enumerate(PRIORITY_MEASURE):
        if kw in name:
            return (i, 0.0)
    stats = col.get("stats") or {}
    mean = abs(stats.get("mean") or 0) or 1
    cv = (stats.get("std") or 0) / mean
    return (len(PRIORITY_MEASURE), -cv)


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    columns = [profile_column(c, df[c]) for c in df.columns]
    measures = sorted([c for c in columns if c["role"] == "measure"], key=measure_priority)
    dims = [c for c in columns if c["role"] == "dimension"]
    # prefer dimensions with a "chartable" number of categories
    dims.sort(key=lambda c: (not (2 <= c["unique"] <= 25), abs(c["unique"] - 8)))
    times = [c for c in columns if c["semantic_type"] == "datetime"]
    # the main event/transaction date is usually the densest date column
    times.sort(key=lambda c: (c["missing_pct"] > 20, -c["unique"], c["missing_pct"]))
    return {
        "columns": columns,
        "measures": [c["name"] for c in measures],
        "dimensions": [c["name"] for c in dims],
        "time_columns": [c["name"] for c in times],
        "identifiers": [c["name"] for c in columns if c["role"] == "identifier"],
        "primary_time": times[0]["name"] if times else None,
        "primary_measure": measures[0]["name"] if measures else None,
    }


def quality_report(raw: pd.DataFrame, clean: pd.DataFrame, issues: dict[str, int]) -> dict[str, Any]:
    """Score data quality on 4 dimensions (0-100) before/after cleaning."""
    raw_cells = max(raw.size, 1)
    from .transform import NULL_TOKENS  # local import avoids a cycle

    raw_missing = int(raw.isna().sum().sum())
    for c in raw.columns:
        if pd.api.types.is_string_dtype(raw[c]) or pd.api.types.is_object_dtype(raw[c]):
            raw_missing += int(raw[c].dropna().astype(str).str.strip().str.lower().isin(NULL_TOKENS - {""}).sum())
    raw_dups = int(raw.duplicated().sum()) if len(raw) else 0
    clean_cells = max(clean.size, 1)
    clean_missing = int(clean.isna().sum().sum())

    completeness_before = 1 - raw_missing / raw_cells
    uniqueness_before = 1 - raw_dups / max(len(raw), 1)
    validity_before = 1 - issues.get("invalid_values", 0) / raw_cells
    consistency_before = 1 - (issues.get("inconsistent_values", 0) + issues.get("format_fixes", 0)) / raw_cells

    def score(c, u, v, k):
        return round(100 * (0.35 * c + 0.25 * u + 0.25 * v + 0.15 * k), 1)

    completeness_after = 1 - clean_missing / clean_cells
    before = score(completeness_before, uniqueness_before, validity_before, consistency_before)
    after = score(completeness_after, 1.0, 1.0, 1.0)
    per_column = [
        {"column": c, "missing": int(clean[c].isna().sum()), "missing_pct": round(100 * clean[c].isna().mean(), 2)}
        for c in clean.columns
    ]
    return {
        "score_before": before,
        "score_after": after,
        "dimensions_before": {
            "completeness": round(100 * completeness_before, 1),
            "uniqueness": round(100 * uniqueness_before, 1),
            "validity": round(100 * validity_before, 1),
            "consistency": round(100 * consistency_before, 1),
        },
        "dimensions_after": {
            "completeness": round(100 * completeness_after, 1),
            "uniqueness": 100.0,
            "validity": 100.0,
            "consistency": 100.0,
        },
        "raw_rows": int(len(raw)),
        "clean_rows": int(len(clean)),
        "raw_missing_cells": raw_missing,
        "clean_missing_cells": clean_missing,
        "duplicate_rows": raw_dups,
        "issues": issues,
        "per_column": per_column,
        "grade": "A" if after >= 90 else "B" if after >= 80 else "C" if after >= 70 else "D",
    }
