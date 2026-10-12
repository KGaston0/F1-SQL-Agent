"""Agent tests that do NOT call any LLM API (prompt, SQL tool and run logging)."""
import json

import pytest

from src import config
from src.agent import logging_utils
from src.agent.agent import AgentResult
from src.agent.prompts import FEW_SHOT_EXAMPLES, build_system_prompt
from src.agent.tools import query_sql
from src.database.connection import execute_select

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="Run scripts/init_db.py first")


def test_prompt_includes_schema_and_rules():
    p = build_system_prompt()
    assert "CREATE TABLE results" in p and "query_sql" in p and "v_results" in p


@pytest.mark.parametrize("question,sql", FEW_SHOT_EXAMPLES)
def test_few_shot_examples_are_valid_sql_and_return_rows(question, sql):
    res = execute_select(sql)
    assert res.rows, f"Example returns no rows: {question}"


def test_few_shot_examples_give_known_facts():
    assert execute_select(FEW_SHOT_EXAMPLES[0][1]).rows[0][0] == 41                  # Senna's wins
    assert execute_select(FEW_SHOT_EXAMPLES[1][1]).rows[0][0] == "Lewis Hamilton"    # 2008 champion


def test_tool_returns_ok_and_errors_as_dicts():
    ok = query_sql("SELECT COUNT(*) AS n FROM drivers")
    assert ok["ok"] and ok["columns"] == ["n"] and ok["rows"][0][0] > 15
    bad = query_sql("DROP TABLE drivers")
    assert not bad["ok"] and "error" in bad
    broken = query_sql("SELECT * FROM table_that_does_not_exist")
    assert not broken["ok"]


def test_tool_truncates_rows_sent_to_the_llm():
    out = query_sql("SELECT * FROM results")
    assert out["row_count"] == 100 and out["truncated"]


def test_jsonl_run_log(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "logs" / "agent.jsonl")
    logging_utils.write_run(AgentResult(question="hello?", answer="hi", steps=[{"tool": "query_sql"}]), "m")
    line = json.loads((tmp_path / "logs" / "agent.jsonl").read_text(encoding="utf-8"))
    assert line["question"] == "hello?" and line["model"] == "m" and line["steps"][0]["tool"] == "query_sql"


def test_automatic_coverage_note_on_partial_tables():
    out = query_sql("SELECT COUNT(*) FROM qualifying WHERE driver_id = 'senna' AND position = 1")
    assert out["ok"] and "1994" in out["coverage_note"]
    assert "coverage_note" not in query_sql("SELECT COUNT(*) FROM races")  # complete tables: no note
    assert "2021" in query_sql("SELECT COUNT(*) FROM sprint_results")["coverage_note"]
