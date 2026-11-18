"""Validation for user-written and AI-generated SQL (read-only, owner's tables only)."""
from __future__ import annotations

import re

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|install|load|pragma|set|reset|call|"
    r"checkpoint|vacuum|grant|revoke|truncate|replace|merge|use|begin|commit|rollback|execute|prepare)\b",
    re.I,
)
SYSTEM_OBJECTS = re.compile(r"\b(duckdb_\w+|information_schema|pg_catalog|pg_\w+|sqlite_\w+|read_\w+|glob|getenv|current_setting|query_table|query)\s*\(?", re.I)
TABLE_REF = re.compile(r"\b((?:dw|stg|mart)_[A-Za-z0-9_]+)\b")


class SQLGuardError(ValueError):
    pass


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", sql)


def validate_select(sql: str, allowed_tables: set[str]) -> str:
    s = strip_comments(sql).strip().rstrip(";").strip()
    if not s:
        raise SQLGuardError("Empty query")
    if ";" in s:
        raise SQLGuardError("Only a single statement is allowed")
    if not re.match(r"^(select|with|from)\b", s, re.I):
        raise SQLGuardError("Only SELECT queries are allowed")
    # ignore string literals when scanning for keywords
    scan = re.sub(r"'(?:[^']|'')*'", "''", s)
    if m := FORBIDDEN.search(scan):
        raise SQLGuardError(f"Keyword '{m.group(1).upper()}' is not allowed in read-only queries")
    if m := SYSTEM_OBJECTS.search(scan):
        raise SQLGuardError(f"Access to '{m.group(1)}' is not allowed")
    for t in TABLE_REF.findall(scan):
        if t not in allowed_tables and not any(t.startswith(a) for a in allowed_tables if a.startswith("mart_")):
            raise SQLGuardError(f"Table '{t}' is not available to you")
    return s
