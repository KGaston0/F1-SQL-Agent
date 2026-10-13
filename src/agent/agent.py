"""Agent loop (no framework) on top of an interchangeable LLM provider (Gemini or Groq).

Flow per question:
  user -> LLM (with tools) -> [tool_call -> we run it -> tool result -> LLM]* -> final text
Every question leaves one JSON line in LOG_PATH (see src/agent/logging_utils.py) and traces via `logging`.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from src import config
from src.agent import logging_utils
from src.agent.llm import LLMProvider, QuotaExhausted, ToolCall, get_provider
from src.agent.prompts import build_system_prompt
from src.agent.tools import REGISTRY, TOOLS

log = logging.getLogger("agent")

_INVISIBLE = re.compile("[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")      # zero-width characters
_CJK_OPEN_BRACKET = re.compile("\u3010\\s*\\[?")     # 【 or 【[  ->  [
_CJK_CLOSE_BRACKET = re.compile("\\]?\\s*\u3011")    # 】 or ]】  ->  ]
_ODD_SPACES = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")            # non-breaking / thin / wide spaces


def tidy_text(text: str) -> str:
    """Undo typographic artifacts some LLMs add (zero-width chars, narrow no-break spaces, non-breaking hyphens).

    They look identical on screen but break exact matching of file names in citations. Only whitespace, invisible
    characters, the non-breaking hyphen and CJK brackets are touched; accents and real punctuation are kept.
    """
    text = _ODD_SPACES.sub(" ", _INVISIBLE.sub("", text)).replace("\u2011", "-")
    # some models wrap citations in CJK brackets: 【[file.pdf, PDF p. 3]】 or 【file.pdf, PDF p. 3】 -> [file.pdf, PDF p. 3]
    text = _CJK_OPEN_BRACKET.sub("[", text)
    return _CJK_CLOSE_BRACKET.sub("]", text)


@dataclass
class AgentResult:
    question: str
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)  # tool calls, in order
    tokens: dict[str, int] = field(default_factory=dict)
    elapsed_s: float = 0.0
    status: str = "ok"  # ok | max_steps | quota | error
    history: list[dict] = field(default_factory=list)  # neutral messages, for multi-turn conversations


class Agent:
    def __init__(self, provider: LLMProvider | None = None, model: str | None = None):
        self.provider = provider or get_provider(model=model)
        self.system_prompt = build_system_prompt()

    @property
    def model(self) -> str:
        return f"{self.provider.name}:{self.provider.model}"

    def ask(self, question: str, history: list[dict] | None = None) -> AgentResult:
        started = time.perf_counter()
        messages = list(history or []) + [{"role": "user", "content": question}]
        result = AgentResult(question=question, answer="")
        tokens = {"prompt": 0, "output": 0, "thoughts": 0}
        log.info("QUESTION: %s", question)

        try:
            for step in range(1, config.AGENT_MAX_STEPS + 1):
                turn = self.provider.generate(self.system_prompt, messages, TOOLS)
                for k, v in turn.usage.items():
                    tokens[k] = tokens.get(k, 0) + (v or 0)

                if not turn.tool_calls:
                    result.answer = tidy_text(turn.text)
                    messages.append({"role": "assistant", "content": result.answer})
                    break

                messages.append({"role": "assistant", "content": turn.text, "tool_calls": turn.tool_calls,
                                 "raw": turn.raw})
                results = [{"call": call, "output": self._run_tool(call, step, result)} for call in turn.tool_calls]
                messages.append({"role": "tool", "results": results})
            else:
                result.status = "max_steps"
                result.answer = "I could not complete the query within the step limit. Try rephrasing the question."
        except QuotaExhausted as e:
            result.status = "quota"
            result.answer = str(e)
            log.error("%s", e)
        except Exception as e:  # the agent must never crash the UI: log it and report it
            result.status = "error"
            result.answer = f"An error occurred while calling the model: {e}"
            log.exception("Agent error")

        result.tokens = tokens
        result.elapsed_s = round(time.perf_counter() - started, 2)
        result.history = messages
        log.info("ANSWER (%s, %.1fs, %d tokens): %s", result.status, result.elapsed_s,
                 sum(tokens.values()), result.answer)
        logging_utils.write_run(result, self.model)
        return result

    # ------------------------------------------------------------------ tools
    def _run_tool(self, call: ToolCall, step: int, result: AgentResult) -> dict[str, Any]:
        fn = REGISTRY.get(call.name)
        out = fn(**call.args) if fn else {"ok": False, "error": f"Unknown tool: {call.name}"}
        detail = " ".join(str(call.args.get("sql") or call.args.get("query") or "").split())
        row_count = out.get("row_count", len(out.get("results", [])))
        result.steps.append({
            "step": step, "tool": call.name, "args": call.args, "ok": out.get("ok"),
            "row_count": row_count, "error": out.get("error"), "ms": out.get("ms"),
        })
        if out.get("ok"):
            log.info("  [%d] %s -> %s results (%s ms) | %s", step, call.name, row_count, out.get("ms"), detail)
        else:
            log.warning("  [%d] %s ERROR: %s | %s", step, call.name, out.get("error"), detail)
        return out
