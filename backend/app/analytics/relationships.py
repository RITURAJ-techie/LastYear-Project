"""Automatic discovery of relationships (primary/foreign keys) between datasets."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .. import warehouse as wh

KEY_ROLES = {"identifier", "dimension"}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _values(table: str, col: str, limit: int = 50_000) -> set[str]:
    df = wh.query_df(f"SELECT DISTINCT CAST({wh.qi(col)} AS VARCHAR) AS v FROM {wh.safe_table(table)} WHERE {wh.qi(col)} IS NOT NULL LIMIT {limit}")
    return set(df["v"].astype(str))


def discover(datasets: list[Any]) -> list[dict[str, Any]]:
    """For every pair of key-like columns across datasets, measure value containment.

    A relationship A.x -> B.y (many-to-one) is proposed when B.y is unique in B
    and most distinct values of A.x are found in B.y."""
    candidates = []
    for ds in datasets:
        prof = ds.profile or {}
        for c in prof.get("columns", []):
            if c["role"] in KEY_ROLES and c["semantic_type"] not in {"boolean"} and c["unique"] >= 2:
                candidates.append((ds, c))
    cache: dict[tuple[str, str], set[str]] = {}

    def vals(ds, col):
        key = (ds.table_name, col)
        if key not in cache:
            cache[key] = _values(ds.table_name, col)
        return cache[key]

    found = []
    for i, (da, ca) in enumerate(candidates):
        for db_, cb in candidates:
            if db_.id == da.id:
                continue
            # skip lineage links (a joined dataset vs. the sources it was built from)
            if db_.id in (da.source_config or {}).get("sources", []) or da.id in (db_.source_config or {}).get("sources", []):
                continue
            # cb must look like a primary key of B (unique per row)
            if not (cb["unique"] >= 0.98 * max(db_.row_count, 1) and cb["missing"] == 0):
                continue
            name_sim = SequenceMatcher(None, _norm(ca["name"]), _norm(cb["name"])).ratio()
            if name_sim < 0.6 and not (ca["role"] == "identifier" and cb["role"] == "identifier"):
                continue
            va, vb = vals(da, ca["name"]), vals(db_, cb["name"])
            if not va or not vb:
                continue
            inter = len(va & vb)
            containment = inter / len(va)
            if containment < 0.5:
                continue
            confidence = round(0.7 * containment + 0.3 * name_sim, 4)
            a_unique = ca["unique"] >= 0.98 * max(da.row_count, 1)
            found.append({
                "from_dataset_id": da.id, "from_dataset": da.name, "from_table": da.table_name, "from_column": ca["name"],
                "to_dataset_id": db_.id, "to_dataset": db_.name, "to_table": db_.table_name, "to_column": cb["name"],
                "cardinality": "one-to-one" if a_unique else "many-to-one",
                "containment_pct": round(containment * 100, 2), "name_similarity": round(name_sim, 3),
                "matched_values": inter, "confidence": confidence,
                "orphan_values": len(va) - inter,
            })
    # keep one direction for one-to-one pairs, best confidence first
    found.sort(key=lambda r: -r["confidence"])
    seen, unique = set(), []
    for r in found:
        key = frozenset([(r["from_table"], r["from_column"]), (r["to_table"], r["to_column"])])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique
