"""DuckDB-backed analytical data warehouse.

Layers
------
* ``stg_<name>``   – staging: raw extracted data, as-is (all columns as loaded)
* ``dw_<name>``    – core: cleaned, typed, conformed data (what analytics read)
* ``mart_<name>_*`` – marts: pre-aggregated views (e.g. monthly KPIs)
* ``dim_date``     – shared conformed date dimension

A single process-wide connection is used and guarded by a lock: DuckDB is an
in-process columnar OLAP engine, so this gives fast analytical SQL without a
separate server. File-system access from SQL is disabled after start-up so
user-supplied (or AI-generated) SELECT statements cannot read local files.
"""
from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import duckdb
import numpy as np
import pandas as pd

from .config import WAREHOUSE_PATH

_lock = threading.RLock()
_conn: duckdb.DuckDBPyConnection | None = None

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _connect(path: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(path)
    conn.execute("SET enable_external_access = false").fetchall()
    conn.execute("SET lock_configuration = true").fetchall()
    return conn


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = _connect(str(WAREHOUSE_PATH))
    return _conn


def reset_connection(path: str | None = None) -> None:
    """Re-open the warehouse (used by tests to point at a temp database)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = _connect(path or str(WAREHOUSE_PATH))


@contextmanager
def cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """A short-lived cursor (its own connection to the shared database instance).

    DuckDB handles concurrent readers/writers via MVCC, so each operation gets an
    independent cursor; this also guarantees no half-consumed result leaks
    between operations."""
    with _lock:
        base = get_conn()
    cur = base.cursor()
    try:
        yield cur
    finally:
        cur.close()


def qi(name: str) -> str:
    """Quote an identifier for DuckDB."""
    return '"' + str(name).replace('"', '""') + '"'


def safe_table(name: str) -> str:
    if not IDENT_RE.match(name):
        raise ValueError(f"Invalid table name: {name}")
    return name


def load_dataframe(table: str, df: pd.DataFrame, replace: bool = True) -> None:
    table = safe_table(table)
    with cursor() as con:
        con.register("__incoming", df)
        try:
            if replace:
                con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM __incoming").fetchall()
            else:
                con.execute(f"INSERT INTO {table} SELECT * FROM __incoming").fetchall()
        finally:
            con.unregister("__incoming")


def drop_objects(prefix_table: str) -> None:
    """Drop the staging/core tables and mart views belonging to a dataset."""
    base = safe_table(prefix_table)
    with cursor() as con:
        views = con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal AND view_name LIKE ?",
            [f"mart_{base[3:]}%"],
        ).fetchall()
        for (v,) in views:
            con.execute(f"DROP VIEW IF EXISTS {qi(v)}").fetchall()
        con.execute(f"DROP TABLE IF EXISTS {base}").fetchall()
        con.execute(f"DROP TABLE IF EXISTS stg_{base[3:]}").fetchall()


def read_table(table: str, limit: int | None = None) -> pd.DataFrame:
    table = safe_table(table)
    sql = f"SELECT * FROM {table}" + (f" LIMIT {int(limit)}" if limit else "")
    with cursor() as con:
        return con.execute(sql).df()


def query_df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with cursor() as con:
        return con.execute(sql, params or []).df()


def list_objects() -> list[dict[str, Any]]:
    with cursor() as con:
        tables = con.execute(
            "SELECT table_name, estimated_size, column_count FROM duckdb_tables() WHERE NOT internal ORDER BY table_name"
        ).fetchall()
        views = con.execute(
            "SELECT view_name, sql FROM duckdb_views() WHERE NOT internal ORDER BY view_name"
        ).fetchall()
    out: list[dict[str, Any]] = []
    for name, rows, cols in tables:
        layer = "staging" if name.startswith("stg_") else "core" if name.startswith("dw_") else "dimension" if name.startswith("dim_") else "other"
        out.append({"name": name, "kind": "table", "layer": layer, "rows": int(rows or 0), "columns": int(cols or 0)})
    for name, sql in views:
        out.append({"name": name, "kind": "view", "layer": "mart", "rows": None, "columns": None, "sql": sql})
    return out


def table_columns(table: str) -> list[dict[str, str]]:
    with cursor() as con:
        rows = con.execute(
            "SELECT column_name, data_type FROM duckdb_columns() WHERE table_name = ? ORDER BY column_index",
            [table],
        ).fetchall()
    return [{"name": r[0], "type": r[1]} for r in rows]


def ensure_date_dimension(start: pd.Timestamp, end: pd.Timestamp) -> None:
    """Create/extend the conformed ``dim_date`` table to cover [start, end]."""
    if pd.isna(start) or pd.isna(end):
        return
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    with cursor() as con:
        exists = con.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE table_name = 'dim_date'"
        ).fetchone()[0]
        if exists:
            lo, hi = con.execute("SELECT min(date_key), max(date_key) FROM dim_date").fetchone()
            if lo is not None:
                start = min(start, pd.Timestamp(lo))
                end = max(end, pd.Timestamp(hi))
    if (end - start).days > 365 * 60:  # guard against absurd ranges
        return
    dates = pd.date_range(start, end, freq="D")
    dim = pd.DataFrame(
        {
            "date_key": dates,
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.strftime("%B"),
            "week": dates.isocalendar().week.astype(int).values,
            "day_of_week": dates.day_of_week + 1,
            "day_name": dates.strftime("%A"),
            "is_weekend": dates.day_of_week >= 5,
            "year_month": dates.strftime("%Y-%m"),
        }
    )
    load_dataframe("dim_date", dim)


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """JSON-safe records (NaN -> None, timestamps -> ISO strings)."""
    out = df.copy()
    for c in out.columns:
        s = out[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            out[c] = s.dt.strftime("%Y-%m-%d %H:%M:%S").str.replace(" 00:00:00", "", regex=False)
        elif pd.api.types.is_float_dtype(s):
            out[c] = s.round(6)
    out = out.astype(object).where(pd.notna(out), None)
    recs = out.to_dict(orient="records")
    for r in recs:
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                r[k] = int(v)
            elif isinstance(v, (np.floating,)):
                r[k] = None if np.isnan(v) else float(v)
            elif isinstance(v, (np.bool_,)):
                r[k] = bool(v)
            elif isinstance(v, (pd.Timestamp,)):
                r[k] = v.isoformat()
    return recs
