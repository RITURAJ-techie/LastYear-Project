"""EXTRACT: read data from files (CSV/TSV/Excel/JSON/Parquet), SQL databases and REST APIs."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from sqlalchemy import create_engine, text

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json", ".parquet"}


class ExtractError(Exception):
    pass


def _read_text_table(raw: bytes, sep: str | None = None) -> pd.DataFrame:
    text_data = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text_data = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_data is None:
        raise ExtractError("Could not decode the file's text encoding")
    if sep is None:
        try:
            sep = csv.Sniffer().sniff(text_data[:20000], delimiters=",;\t|").delimiter
        except csv.Error:
            sep = ","
    return pd.read_csv(io.StringIO(text_data), sep=sep, dtype=str, keep_default_na=False, na_values=[""])


def _records_from_json(obj: Any, record_path: str | None = None) -> pd.DataFrame:
    if record_path:
        for part in record_path.split("."):
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                raise ExtractError(f"JSON path '{record_path}' not found")
    if isinstance(obj, dict):
        # pick the first list-of-objects value (common API envelope: {"data": [...]})
        lists = [v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        obj = lists[0] if lists else [obj]
    if not isinstance(obj, list):
        raise ExtractError("JSON does not contain a list of records")
    return pd.json_normalize(obj, sep="_")


def read_file(path: Path, original_name: str | None = None) -> dict[str, pd.DataFrame]:
    """Return {table_name: DataFrame}. Excel workbooks may yield one frame per sheet."""
    ext = Path(original_name or path.name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ExtractError(f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    raw = path.read_bytes()
    if not raw:
        raise ExtractError("File is empty")
    if ext in {".csv", ".txt"}:
        return {"data": _read_text_table(raw)}
    if ext == ".tsv":
        return {"data": _read_text_table(raw, sep="\t")}
    if ext in {".xlsx", ".xls"}:
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        sheets = {name: df for name, df in sheets.items() if not df.dropna(how="all").empty}
        if not sheets:
            raise ExtractError("Workbook has no non-empty sheets")
        return sheets
    if ext == ".json":
        try:
            return {"data": _records_from_json(json.loads(raw.decode("utf-8-sig")))}
        except json.JSONDecodeError:
            return {"data": pd.read_json(io.BytesIO(raw), lines=True)}
    if ext == ".parquet":
        return {"data": pd.read_parquet(io.BytesIO(raw))}
    raise ExtractError(f"Unsupported file type '{ext}'")


def read_sql(connection_url: str, query: str | None = None, table: str | None = None, limit: int = 1_000_000) -> pd.DataFrame:
    """Extract from any SQLAlchemy-supported database (PostgreSQL, MySQL, SQL Server, SQLite...)."""
    if not query and not table:
        raise ExtractError("Provide either a SQL query or a table name")
    if query:
        stripped = query.strip().rstrip(";")
        if not stripped.lower().startswith(("select", "with")):
            raise ExtractError("Only SELECT queries are allowed for extraction")
        sql = stripped
    else:
        if not all(ch.isalnum() or ch in "_." for ch in table):
            raise ExtractError("Invalid table name")
        sql = f"SELECT * FROM {table}"
    try:
        engine = create_engine(connection_url)
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn)
        engine.dispose()
    except Exception as exc:  # noqa: BLE001 - surface driver errors to the user
        raise ExtractError(f"Database extraction failed: {exc}") from exc
    return df.head(limit)


def list_sql_tables(connection_url: str) -> list[str]:
    from sqlalchemy import inspect

    try:
        engine = create_engine(connection_url)
        names = inspect(engine).get_table_names()
        engine.dispose()
        return names
    except Exception as exc:  # noqa: BLE001
        raise ExtractError(f"Could not connect: {exc}") from exc


def read_api(url: str, record_path: str | None = None, headers: dict[str, str] | None = None,
             params: dict[str, str] | None = None, timeout: int = 30) -> pd.DataFrame:
    """Extract JSON (or CSV) records from a REST endpoint."""
    if not url.lower().startswith(("http://", "https://")):
        raise ExtractError("API URL must start with http:// or https://")
    try:
        resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ExtractError(f"API request failed: {exc}") from exc
    ctype = resp.headers.get("content-type", "")
    if "csv" in ctype or url.lower().endswith(".csv"):
        return _read_text_table(resp.content)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ExtractError("API did not return JSON or CSV") from exc
    return _records_from_json(payload, record_path)
