"""Agent loop tests using a fake LLM provider (no network, no quota)."""
import json

import pytest

from src import config
from src.agent.agent import Agent
from src.agent.llm.base import LLMProvider, LLMTurn, QuotaExhausted, ToolCall, call_with_retries

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="Run scripts/init_db.py first")


class ScriptedProvider(LLMProvider):
    """Returns predefined turns and records what it received, to verify the loop."""
    name, model = "fake", "scripted"

    def __init__(self, turns):
        self.turns, self.seen = list(turns), []

    def generate(self, system, messages, tools):
        self.seen.append((system, [dict(m) for m in messages], [t.name for t in tools]))
        t = self.turns.pop(0)
        if isinstance(t, Exception):
            raise t
        return t


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_PATH", tmp_path / "agent.jsonl")


def _call(sql, id_="c1"):
    return ToolCall(id=id_, name="query_sql", args={"sql": sql})


def test_tool_call_then_answer():
    p = ScriptedProvider([
        LLMTurn(text="", tool_calls=[_call("SELECT COUNT(*) AS n FROM drivers")], usage={"prompt": 10, "output": 2}),
        LLMTurn(text="There are many drivers.", usage={"prompt": 12, "output": 5}),
    ])
    res = Agent(provider=p).ask("How many drivers are there?")
    assert res.status == "ok" and res.answer == "There are many drivers."
    assert len(res.steps) == 1 and res.steps[0]["ok"] and res.steps[0]["row_count"] == 1
    assert res.tokens["prompt"] == 22
    # the 2nd turn received the tool result
    tool_msg = p.seen[1][1][-1]
    assert tool_msg["role"] == "tool" and tool_msg["results"][0]["output"]["ok"]
    assert p.seen[0][2] == ["query_sql"]


def test_invalid_sql_is_returned_to_the_model_so_it_can_fix_it():
    p = ScriptedProvider([
        LLMTurn(text="", tool_calls=[_call("SELECT * FROM nonexistent_table")]),
        LLMTurn(text="", tool_calls=[_call("SELECT COUNT(*) FROM races", "c2")]),
        LLMTurn(text="Done."),
    ])
    res = Agent(provider=p).ask("races")
    assert [s["ok"] for s in res.steps] == [False, True] and res.answer == "Done."


def test_dangerous_sql_is_not_executed():
    p = ScriptedProvider([LLMTurn(text="", tool_calls=[_call("DROP TABLE drivers")]), LLMTurn(text="I can't.")])
    res = Agent(provider=p).ask("delete everything")
    assert res.steps[0]["ok"] is False
    from src.database.connection import execute_select
    assert execute_select("SELECT COUNT(*) FROM drivers").rows[0][0] > 15


def test_step_limit(monkeypatch):
    monkeypatch.setattr(config, "AGENT_MAX_STEPS", 2)
    p = ScriptedProvider([LLMTurn(text="", tool_calls=[_call("SELECT 1")])] * 5)
    res = Agent(provider=p).ask("infinite loop")
    assert res.status == "max_steps"


def test_quota_exhausted_is_its_own_status():
    res = Agent(provider=ScriptedProvider([QuotaExhausted("no quota")])).ask("hello")
    assert res.status == "quota" and "no quota" in res.answer


def test_generic_error_does_not_crash_the_agent():
    res = Agent(provider=ScriptedProvider([RuntimeError("boom")])).ask("hello")
    assert res.status == "error" and "boom" in res.answer


def test_every_question_is_logged_to_jsonl(tmp_path):
    Agent(provider=ScriptedProvider([LLMTurn(text="ok")])).ask("hello?")
    rec = json.loads((tmp_path / "agent.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["question"] == "hello?" and rec["model"] == "fake:scripted" and rec["status"] == "ok"


def test_history_allows_multi_turn_conversations():
    p = ScriptedProvider([LLMTurn(text="One."), LLMTurn(text="Two.")])
    a = Agent(provider=p)
    r1 = a.ask("first")
    a.ask("second", history=r1.history)
    assert [m["role"] for m in p.seen[1][1]] == ["user", "assistant", "user"]


def test_retries_and_daily_quota(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("503")
        return "ok"

    assert call_with_retries(flaky, lambda e: (True, 0.0), 5, "test") == "ok" and len(attempts) == 3
    with pytest.raises(QuotaExhausted):  # suggested wait of hours => no retry
        call_with_retries(lambda: (_ for _ in ()).throw(RuntimeError("429")), lambda e: (True, 5000.0), 5, "test")


def test_translation_to_groq_and_gemini_formats():
    from src.agent.llm.gemini import GeminiProvider
    from src.agent.llm.groq_provider import GroqProvider

    call = ToolCall(id="abc", name="query_sql", args={"sql": "SELECT 1"})
    msgs = [{"role": "user", "content": "hello"},
            {"role": "assistant", "content": "", "tool_calls": [call], "raw": None},
            {"role": "tool", "results": [{"call": call, "output": {"ok": True, "rows": [[1]]}}]}]

    g = GroqProvider._to_messages("SYSTEM", msgs)
    assert [m["role"] for m in g] == ["system", "user", "assistant", "tool"]
    assert g[2]["tool_calls"][0]["id"] == "abc" and json.loads(g[2]["tool_calls"][0]["function"]["arguments"]) == call.args
    assert g[3]["tool_call_id"] == "abc" and json.loads(g[3]["content"])["rows"] == [[1]]

    c = GeminiProvider._to_contents(msgs)
    assert [x.role for x in c] == ["user", "model", "user"]
    assert c[1].parts[0].function_call.name == "query_sql"
    assert c[2].parts[0].function_response.response["ok"] is True
