"""Interactive, read-only terminal shell for InsightFlow's two databases.

    python scripts/dbshell.py sqlite            # metadata: users, datasets, etl_runs, dashboards
    python scripts/dbshell.py duckdb            # warehouse: stg_*, dw_*, mart_*, dim_date
    python scripts/dbshell.py duckdb -c "SELECT * FROM dw_sales_orders LIMIT 5"

Inside the shell:  .tables   .schema <table>   .count   .help   .quit
End SQL statements with ';' (multi-line input is fine).

Both databases are opened READ-ONLY, so nothing can be changed by accident.
DuckDB note: while the app is running it holds a write lock on warehouse.duckdb, so stop the
app first (docker compose stop) or use the SQL console in the app (Data Warehouse -> SQL console).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import pandas as pd

DATA_DIR = Path(os.getenv("INSIGHTFLOW_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 60)
MAX_ROWS = 50


class Shell:
    def __init__(self, kind: str):
        self.kind = kind
        if kind == "sqlite":
            path = DATA_DIR / "metadata.db"
            if not path.exists():
                sys.exit(f"No metadata database at {path} – start the app once so it is created.")
            self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        else:
            import duckdb

            path = DATA_DIR / "warehouse.duckdb"
            if not path.exists():
                sys.exit(f"No warehouse at {path} – start the app once so it is created.")
            try:
                self.conn = duckdb.connect(str(path), read_only=True)
            except duckdb.IOException as exc:
                if "lock" in str(exc).lower():
                    sys.exit("The warehouse is in use by the running app (DuckDB allows one writer).\n"
                             "  • Stop the app first:   docker compose stop\n"
                             "  • or query it live in the app: Data Warehouse → SQL console")
                raise
        self.path = path

    def query(self, sql: str) -> pd.DataFrame:
        if self.kind == "sqlite":
            return pd.read_sql_query(sql, self.conn)
        return self.conn.execute(sql).df()

    def tables(self) -> pd.DataFrame:
        if self.kind == "sqlite":
            return self.query("SELECT name AS table_name, type FROM sqlite_master "
                              "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return self.query("""
            SELECT table_name, 'table' AS type, estimated_size AS rows, column_count AS columns FROM duckdb_tables()
            UNION ALL SELECT view_name, 'view', NULL, NULL FROM duckdb_views() WHERE NOT internal
            ORDER BY 1""")

    def schema(self, table: str) -> pd.DataFrame:
        if self.kind == "sqlite":
            return self.query(f"PRAGMA table_info('{table.replace(chr(39), '')}')")[["name", "type", "notnull", "pk"]]
        return self.query(f"SELECT column_name, data_type FROM duckdb_columns() WHERE table_name = '{table.replace(chr(39), '')}' "
                          "ORDER BY column_index")

    def counts(self) -> pd.DataFrame:
        rows = []
        for t, typ in self.tables()[["table_name", "type"]].itertuples(index=False):
            if typ == "table":
                n = self.query(f'SELECT count(*) AS n FROM "{t}"')["n"].iloc[0]
                rows.append({"table": t, "rows": int(n)})
        return pd.DataFrame(rows)

    def show(self, df: pd.DataFrame) -> None:
        if df.empty:
            print("(no rows)")
            return
        print(df.head(MAX_ROWS).to_string(index=False))
        if len(df) > MAX_ROWS:
            print(f"... {len(df) - MAX_ROWS} more rows (add LIMIT / WHERE to narrow)")
        print(f"({len(df)} row{'s' if len(df) != 1 else ''})")

    def run(self, text: str) -> None:
        cmd = text.strip()
        try:
            if cmd in {".tables", ".t"}:
                self.show(self.tables())
            elif cmd.startswith(".schema"):
                parts = cmd.split()
                if len(parts) < 2:
                    print("usage: .schema <table>")
                else:
                    self.show(self.schema(parts[1]))
            elif cmd == ".count":
                self.show(self.counts())
            elif cmd in {".help", ".h"}:
                print(__doc__)
            else:
                self.show(self.query(cmd.rstrip(";")))
        except Exception as exc:  # noqa: BLE001 - show any SQL error and keep the shell alive
            print(f"Error: {str(exc).splitlines()[0]}")

    def repl(self) -> None:
        print(f"InsightFlow {self.kind} shell (read-only) – {self.path}\nType .tables, .schema <table>, .count, .help or .quit\n")
        buf: list[str] = []
        while True:
            try:
                line = input(f"{self.kind}{'>' if not buf else '…'} ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            s = line.strip()
            if not buf and s in {".quit", ".exit", "exit", "quit"}:
                break
            if not buf and s.startswith("."):
                self.run(s)
                continue
            if s:
                buf.append(line)
            if s.endswith(";"):
                self.run("\n".join(buf))
                buf = []


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only shell for InsightFlow's SQLite metadata and DuckDB warehouse")
    ap.add_argument("db", choices=["sqlite", "duckdb"])
    ap.add_argument("-c", "--command", help="run one SQL statement or dot-command and exit")
    args = ap.parse_args()
    sh = Shell(args.db)
    if args.command:
        sh.run(args.command)
    else:
        sh.repl()


if __name__ == "__main__":
    main()
