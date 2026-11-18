"""TRANSFORM: automated, logged data-cleaning pipeline.

Every step appends an entry to ``log`` so the ETL run is fully auditable in the UI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

NULL_TOKENS = {"", "na", "n/a", "nan", "null", "none", "nil", "-", "--", "?", "missing", "undefined", "#n/a", "#value!"}
TRUE_TOKENS = {"true", "yes", "y", "t"}
FALSE_TOKENS = {"false", "no", "n", "f"}
DATE_HINT = re.compile(r"(?:\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4})|(?:[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{2,4})|(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})|(?:\d{4}-\d{2}$)")
NUM_CLEAN = re.compile(r"[\s$€£₹¥,]|(?<=\d)%$")

DEFAULT_OPTIONS: dict[str, Any] = {
    "standardize_names": True,
    "trim_whitespace": True,
    "fix_types": True,
    "remove_duplicates": True,
    "normalize_categories": True,
    "impute_missing": True,
    "drop_sparse_columns": True,
    "sparse_threshold": 0.95,
    "cap_outliers": False,
}


@dataclass
class TransformResult:
    df: pd.DataFrame
    log: list[dict[str, Any]] = field(default_factory=list)
    issues: dict[str, int] = field(default_factory=dict)


def _is_text(s: pd.Series) -> bool:
    return pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)


def standardize_name(name: Any, idx: int) -> str:
    s = str(name).strip()
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)  # camelCase -> camel_Case
    s = re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower()
    if not s or s.startswith("unnamed"):
        s = f"column_{idx + 1}"
    if s[0].isdigit():
        s = f"c_{s}"
    return s[:60]


def _parse_numeric(s: pd.Series) -> tuple[pd.Series, float]:
    txt = s.astype(str).str.strip()
    neg = txt.str.match(r"^\(.*\)$")
    cleaned = txt.str.replace(r"^\((.*)\)$", r"\1", regex=True).str.replace(NUM_CLEAN, "", regex=True)
    num = pd.to_numeric(cleaned, errors="coerce")
    num = num.where(~neg, -num)
    ratio = num.notna().sum() / max(len(s), 1)
    return num, ratio


def _parse_datetime(s: pd.Series) -> tuple[pd.Series, float]:
    sample = s.astype(str).head(500)
    if sample.str.contains(DATE_HINT).mean() < 0.8:
        return s, 0.0
    try:
        parsed = pd.to_datetime(s.astype(str), errors="coerce", format="mixed")
    except (ValueError, TypeError):
        return s, 0.0
    ratio = parsed.notna().sum() / max(len(s), 1)
    return parsed, ratio


def transform(raw: pd.DataFrame, options: dict[str, Any] | None = None) -> TransformResult:
    opts = {**DEFAULT_OPTIONS, **(options or {})}
    df = raw.copy().reset_index(drop=True)
    log: list[dict[str, Any]] = []
    issues = {"format_fixes": 0, "null_tokens": 0, "invalid_values": 0, "inconsistent_values": 0, "duplicates_removed": 0, "imputed_values": 0,
              "empty_rows_removed": 0, "columns_dropped": 0, "outliers_detected": 0}

    def add(step: str, description: str, affected: int = 0, details: Any = None) -> None:
        log.append({"step": step, "description": description, "affected": int(affected), "details": details})

    add("extract", f"Received {len(df):,} rows x {df.shape[1]} columns from source", len(df))

    # 1. Column names
    if opts["standardize_names"]:
        new_cols, seen, renamed = [], {}, {}
        for i, c in enumerate(df.columns):
            n = standardize_name(c, i)
            if n in seen:
                seen[n] += 1
                n = f"{n}_{seen[n]}"
            else:
                seen[n] = 0
            new_cols.append(n)
            if n != str(c):
                renamed[str(c)] = n
        df.columns = new_cols
        add("standardize_names", "Converted column names to clean snake_case identifiers", len(renamed), renamed or None)

    # 2. Whitespace + null tokens
    if opts["trim_whitespace"]:
        changed = 0
        nulled = 0
        for c in df.columns:
            if _is_text(df[c]):
                s = df[c]
                mask = s.notna()
                stripped = s.where(~mask, s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True))
                changed += int((stripped[mask] != s[mask].astype(str)).sum())
                is_null = stripped.astype(str).str.lower().isin(NULL_TOKENS) & mask
                nulled += int(is_null.sum())
                issues["null_tokens"] += int(is_null.sum())
                df[c] = stripped.mask(is_null)
        add("clean_text", "Trimmed whitespace and converted null placeholders (NA, N/A, '-', 'null'...) to missing",
            changed + nulled, {"trimmed": changed, "null_tokens": nulled})

    # 3. Remove empty rows/columns
    before_rows = len(df)
    df = df.dropna(how="all")
    empty_cols = [c for c in df.columns if df[c].isna().all()]
    df = df.drop(columns=empty_cols)
    issues["empty_rows_removed"] = before_rows - len(df)
    add("drop_empty", "Removed completely empty rows and columns", before_rows - len(df) + len(empty_cols),
        {"rows": before_rows - len(df), "columns": empty_cols})

    # 4. Type inference & coercion
    if opts["fix_types"]:
        conversions = {}
        for c in df.columns:
            s = df[c]
            if not _is_text(s):
                continue
            non_null = s.dropna()
            if non_null.empty:
                continue
            lower = non_null.astype(str).str.lower()
            uniq = set(lower.unique())
            if uniq and uniq <= (TRUE_TOKENS | FALSE_TOKENS) and len(uniq) <= 2:
                df[c] = s.map(lambda v: None if pd.isna(v) else str(v).lower() in TRUE_TOKENS).astype("boolean")
                conversions[c] = "boolean"
                continue
            num, ratio = _parse_numeric(non_null)
            if ratio >= 0.9:
                plain = pd.to_numeric(non_null.astype(str), errors="coerce")
                issues["format_fixes"] += int((plain.isna() & num.notna()).sum())
                bad = int(num.isna().sum())
                full = pd.Series(np.nan, index=s.index, dtype="float64")
                full.loc[num.index] = num.astype(float)
                if bad == 0 and np.all(np.mod(full.dropna(), 1) == 0) and full.abs().max() < 2**53:
                    full = full.astype("Int64")
                df[c] = full
                issues["invalid_values"] += bad
                conversions[c] = f"numeric ({bad} invalid -> missing)" if bad else "numeric"
                continue
            dt, ratio = _parse_datetime(non_null)
            if ratio >= 0.9:
                iso = non_null.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}")
                issues["format_fixes"] += int((~iso & dt.notna()).sum())
                bad = int(dt.isna().sum())
                full = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
                full.loc[dt.index] = dt.astype("datetime64[ns]")
                df[c] = full
                issues["invalid_values"] += bad
                conversions[c] = f"datetime ({bad} invalid -> missing)" if bad else "datetime"
        # pandas may have inferred types already (Excel/Parquet) – normalize timezone-aware dates
        for c in df.columns:
            if isinstance(df[c].dtype, pd.DatetimeTZDtype):
                df[c] = df[c].dt.tz_convert(None)
        add("fix_types", "Detected and converted data types (numbers, currency, percentages, dates, booleans)",
            len(conversions), conversions or None)

    # 5. Duplicates
    if opts["remove_duplicates"]:
        dups = int(df.duplicated().sum())
        df = df.drop_duplicates().reset_index(drop=True)
        issues["duplicates_removed"] = dups
        add("remove_duplicates", "Removed exact duplicate records", dups)

    # 6. Normalize inconsistent categorical spellings ("north", "North ", "NORTH" -> "North")
    if opts["normalize_categories"]:
        fixed: dict[str, int] = {}
        for c in df.columns:
            s = df[c]
            if not _is_text(s):
                continue
            nn = s.dropna().astype(str)
            if nn.empty or nn.nunique() > max(100, 0.2 * len(nn)):
                continue
            key = nn.str.lower().str.replace(r"[\s_\-]+", " ", regex=True).str.strip()
            if key.nunique() == nn.nunique():
                continue
            canonical = nn.groupby(key).agg(lambda x: x.value_counts().index[0])
            mapped = key.map(canonical)
            n_changed = int((mapped != nn).sum())
            if n_changed:
                df.loc[mapped.index, c] = mapped
                fixed[c] = n_changed
                issues["inconsistent_values"] += n_changed
        add("normalize_categories", "Unified inconsistent category spellings/casing", sum(fixed.values()), fixed or None)

    # 7. Sparse columns
    if opts["drop_sparse_columns"] and len(df):
        thr = float(opts["sparse_threshold"])
        sparse = [c for c in df.columns if df[c].isna().mean() > thr]
        df = df.drop(columns=sparse)
        issues["columns_dropped"] = len(sparse)
        add("drop_sparse", f"Dropped columns with more than {int(thr * 100)}% missing values", len(sparse), sparse or None)

    # 8. Outliers (IQR) – detect, optionally cap
    outlier_info = {}
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            x = s.dropna().astype(float)
            if len(x) < 10:
                continue
            q1, q3 = np.percentile(x, [25, 75])
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
            n_out = int(((x < lo) | (x > hi)).sum())
            if n_out:
                outlier_info[c] = n_out
                if opts["cap_outliers"]:
                    df[c] = s.astype(float).clip(lo, hi)
    issues["outliers_detected"] = sum(outlier_info.values())
    add("outliers", ("Capped" if opts["cap_outliers"] else "Flagged") + " extreme outliers (beyond 3xIQR from the quartiles)",
        issues["outliers_detected"], outlier_info or None)

    # 9. Missing value imputation
    if opts["impute_missing"]:
        imputed: dict[str, str] = {}
        for c in df.columns:
            s = df[c]
            miss = int(s.isna().sum())
            if not miss or miss == len(s):
                continue
            if pd.api.types.is_bool_dtype(s):
                df[c] = s.fillna(bool(s.mode().iloc[0]))
                imputed[c] = f"{miss} -> mode"
            elif pd.api.types.is_numeric_dtype(s):
                med = s.median()
                if pd.api.types.is_integer_dtype(s):
                    med = int(round(med))
                df[c] = s.fillna(med)
                imputed[c] = f"{miss} -> median ({med:,.2f})" if isinstance(med, float) else f"{miss} -> median ({med:,})"
            elif _is_text(s):
                df[c] = s.fillna("Unknown")
                imputed[c] = f"{miss} -> 'Unknown'"
            else:
                continue  # datetimes are left missing (imputing dates fabricates history)
            issues["imputed_values"] += miss
        add("impute_missing", "Filled missing values (numeric: median, categorical: 'Unknown', boolean: mode)",
            issues["imputed_values"], imputed or None)

    # Final: make string columns plain python-string friendly for DuckDB
    for c in df.columns:
        if _is_text(df[c]):
            df[c] = df[c].astype("string")

    add("load_ready", f"Clean dataset ready: {len(df):,} rows x {df.shape[1]} columns", len(df))
    return TransformResult(df=df, log=log, issues=issues)
