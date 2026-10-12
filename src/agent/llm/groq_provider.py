"""Groq provider (OpenAI-compatible API: chat.completions + tools). Open models, free plan."""
from __future__ import annotations

import json

import groq

from src import config
from src.agent.llm.base import LLMProvider, LLMTurn, ToolCall, ToolSpec, call_with_retries

RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _classify(e: Exception) -> tuple[bool, float]:
    if isinstance(e, groq.APIConnectionError):  # includes timeouts
        return True, 0.0
    if isinstance(e, groq.APIStatusError):
        hint = 0.0
        if e.status_code == 429:
            try:
                hint = float(e.response.headers.get("retry-after", 0))
            except (TypeError, ValueError):
                hint = 0.0
        # Open models sometimes emit a malformed tool call: retrying usually fixes it.
        malformed_tool_call = e.status_code == 400 and "tool_use_failed" in str(e)
        return (e.status_code in RETRYABLE_HTTP or malformed_tool_call), hint
    return False, 0.0


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, model: str | None = None, client: groq.Groq | None = None):
        if client is None and not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing in .env (free key at https://console.groq.com/keys).")
        # max_retries=0: retries are handled by call_with_retries (to tell per-minute limits from daily quota)
        self.client = client or groq.Groq(api_key=config.GROQ_API_KEY, max_retries=0)
        self.model = model or config.GROQ_MODEL

    @staticmethod
    def _to_messages(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg: dict = {"role": "assistant", "content": m.get("content") or ""}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [{"id": c.id, "type": "function",
                                          "function": {"name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)}}
                                         for c in m["tool_calls"]]
                out.append(msg)
            else:  # tool: one message per result
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r["call"].id, "name": r["call"].name,
                                "content": json.dumps(r["output"], ensure_ascii=False, default=str)})
        return out

    def generate(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        api_tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                       "parameters": t.parameters}} for t in tools]
        payload = self._to_messages(system, messages)
        resp = call_with_retries(
            lambda: self.client.chat.completions.create(
                model=self.model, messages=payload, tools=api_tools, tool_choice="auto", temperature=0.0),
            _classify, config.LLM_MAX_RETRIES, f"Groq ({self.model})")
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_parse_error": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
        u = resp.usage
        usage = {"prompt": u.prompt_tokens, "output": u.completion_tokens, "thoughts": 0} if u else {}
        return LLMTurn(text=(msg.content or "").strip(), tool_calls=calls, usage=usage)
