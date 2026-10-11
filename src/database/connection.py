"""Acceso de SOLO LECTURA a la BD para la herramienta SQL del agente.

Defensa en profundidad (cada capa es independiente):
  1. Conexión abierta con mode=ro (SQLite rechaza cualquier escritura).
  2. Authorizer: solo permite SELECT/lectura/funciones; niega el resto (DDL, PRAGMA, ATTACH...).
  3. Una única sentencia que empiece con SELECT o WITH.
  4. Tope de filas devueltas y timeout por consulta.
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
    """La consulta no es un SELECT de lectura válido."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # True si había más filas que SQL_MAX_ROWS


def connect_readonly(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"No existe la BD {path}. Ejecutá: python scripts/init_db.py")
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.set_authorizer(lambda action, *_: sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY)
    return conn


def execute_select(sql: str, db_path: Path | None = None, max_rows: int | None = None,
                   timeout_s: float | None = None) -> QueryResult:
    """Ejecuta un SELECT validado. Lanza SQLNotAllowed ante cualquier otra cosa."""
    max_rows = max_rows or config.SQL_MAX_ROWS
    timeout_s = timeout_s or config.SQL_TIMEOUT_S
    sql = sql.strip().rstrip(";").strip()
    if not _STARTS_OK.match(sql):
        raise SQLNotAllowed("Solo se permiten consultas SELECT (o WITH ... SELECT).")

    conn = connect_readonly(db_path)
    try:
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cur = conn.execute(sql)
        except sqlite3.Warning as e:  # "You can only execute one statement at a time"
            raise SQLNotAllowed(str(e)) from e
        except sqlite3.DatabaseError as e:  # authorizer denied, ro violation, sintaxis, timeout
            raise SQLNotAllowed(f"Consulta rechazada o inválida: {e}") from e
        columns = [c[0] for c in cur.description or []]
        try:
            rows = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as e:
            raise SQLNotAllowed(f"Consulta interrumpida (timeout {timeout_s}s u otro error): {e}") from e
        return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)
    finally:
        conn.close()
