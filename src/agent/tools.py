"""Tools the LLM can call (provider-independent). For now: query_sql."""
from __future__ import annotations

import re
import time
from typing import Any

from src.agent.llm.base import ToolSpec
from src.database.connection import SQLNotAllowed, execute_select

MAX_ROWS_TO_LLM = 100  # cap on rows returned to the model (protects context size and quota)

QUERY_SQL = ToolSpec(
    name="query_sql",
    description=(
        "Runs a SQLite SELECT query on the historical Formula 1 database and returns the rows. "
        "Use it for any fact, count or statistic. Read-only: a single SELECT (or WITH ... SELECT)."
    ),
    parameters={
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "SQLite query (a single SELECT)."}},
        "required": ["sql"],
    },
)

TOOLS = [QUERY_SQL]

# Tables with partial coverage: if a query touches one, the tool adds the warning itself
# (it does not depend on the LLM remembering), so a "low" total is never presented as the full history.
COVERAGE_NOTES = {
    "qualifying": "The qualifying table only covers 1994 onwards: earlier poles and qualifying results are NOT "
                  "included, so totals for drivers who raced before 1994 are partial.",
    "sprint_results": "The sprint_results table only covers 2021 onwards (sprint races).",
    "constructor_standings": "The constructors' championship only exists from 1958.",
}


def coverage_notes(sql: str) -> list[str]:
    low = sql.lower()
    return [note for table, note in COVERAGE_NOTES.items() if re.search(rf"\b{table}\b", low)]


def query_sql(sql: str = "", **_ignored) -> dict[str, Any]:
    """Runs the SQL and returns a serializable dict for the model. Errors are returned (not raised)
    so the LLM can fix its query."""
    started = time.perf_counter()
    if not sql:
        return {"ok": False, "error": "Missing 'sql' argument.", "ms": _ms(started)}
    try:
        res = execute_select(sql)
    except (SQLNotAllowed, FileNotFoundError) as e:
        return {"ok": False, "error": str(e), "ms": _ms(started)}
    rows = [list(r) for r in res.rows[:MAX_ROWS_TO_LLM]]
    out = {
        "ok": True,
        "columns": res.columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": res.truncated or len(res.rows) > MAX_ROWS_TO_LLM,
        "ms": _ms(started),
    }
    if notes := coverage_notes(sql):
        out["coverage_note"] = " ".join(notes)
    return out


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


# name -> function registry (the agent dispatches by name)
REGISTRY = {"query_sql": query_sql}
