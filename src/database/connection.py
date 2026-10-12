"""READ-ONLY access to the DB for the agent's SQL tool.

Defense in depth (each layer is independent):
  1. Connection opened with mode=ro (SQLite rejects any write).
  2. Authorizer: only allows SELECT/read/functions; denies the rest (DDL, PRAGMA, ATTACH...).
  3. A single statement that starts with SELECT or WITH.
  4. Cap on returned rows and a per-query timeout.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from src import config

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_STARTS_OK = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


class SQLNotAllowed(ValueError):
    """The query is not a valid read-only SELECT."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # True if there were more rows than SQL_MAX_ROWS


def connect_readonly(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"DB not found: {path}. Run: python scripts/init_db.py")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
    return conn


def execute_select(sql: str, db_path: Path | None = None, max_rows: int | None = None,
                   timeout_s: float | None = None) -> QueryResult:
    """Runs a validated SELECT. Raises SQLNotAllowed for anything else."""
    max_rows = max_rows or config.SQL_MAX_ROWS
    timeout_s = timeout_s or config.SQL_TIMEOUT_S
    sql = sql.strip().rstrip(";").strip()
    if not _STARTS_OK.match(sql):
        raise SQLNotAllowed("Only SELECT queries (or WITH ... SELECT) are allowed.")

    conn = connect_readonly(db_path)
    try:
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cur = conn.execute(sql)
        except sqlite3.Warning as e:  # "You can only execute one statement at a time"
            raise SQLNotAllowed(str(e)) from e
        except sqlite3.DatabaseError as e:  # authorizer denied, read-only violation, syntax error, timeout
            raise SQLNotAllowed(f"Query rejected or invalid: {e}") from e
        columns = [c[0] for c in cur.description or []]
        try:
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as e:
            raise SQLNotAllowed(f"Query interrupted (timeout {timeout_s}s or other error): {e}") from e
        return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)
    finally:
        conn.close()
