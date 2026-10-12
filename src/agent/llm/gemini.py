"""Gemini provider (google-genai SDK) using native function calling."""
from __future__ import annotations

from typing import Any

from google import genai
from google.genai import errors, types

from src import config
from src.agent.llm.base import LLMProvider, LLMTurn, ToolCall, ToolSpec, call_with_retries

RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _retry_after_s(e: errors.APIError) -> float:
    """Seconds Gemini asks us to wait (RetryInfo.retryDelay, e.g. '5527s'); 0 if not reported."""
    try:
        for d in (e.details or {}).get("error", {}).get("details", []):
            if str(d.get("@type", "")).endswith("RetryInfo"):
                return float(str(d["retryDelay"]).rstrip("s"))
    except (AttributeError, KeyError, ValueError, TypeError):
        pass
    return 0.0


def _classify(e: Exception) -> tuple[bool, float]:
    if isinstance(e, errors.APIError):
        return e.code in RETRYABLE_HTTP, _retry_after_s(e) if e.code == 429 else 0.0
    return False, 0.0


def _schema(js: dict[str, Any]) -> types.Schema:
    """JSON Schema (subset: object/string/integer/number/boolean/array) -> Gemini types.Schema."""
    t = js.get("type", "string").upper()
    kwargs: dict[str, Any] = {"type": getattr(types.Type, t), "description": js.get("description")}
    if "properties" in js:
        kwargs["properties"] = {k: _schema(v) for k, v in js["properties"].items()}
    if "required" in js:
        kwargs["required"] = js["required"]
    if "items" in js:
        kwargs["items"] = _schema(js["items"])
    return types.Schema(**kwargs)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str | None = None, client: genai.Client | None = None):
        if client is None and not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing in .env (see .env.example).")
        self.client = client or genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = model or config.GEMINI_MODEL

    # ---- neutral format -> Gemini
    @staticmethod
    def _to_contents(messages: list[dict]) -> list[types.Content]:
        out: list[types.Content] = []
        for m in messages:
            if m["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part(text=m["content"])]))
            elif m["role"] == "assistant":
                if m.get("raw") is not None:
                    out.append(m["raw"])  # sent back unchanged (includes thought signatures)
                else:
                    parts = [types.Part(text=m["content"])] if m.get("content") else []
                    parts += [types.Part.from_function_call(name=c.name, args=c.args) for c in m.get("tool_calls", [])]
                    out.append(types.Content(role="model", parts=parts))
            else:  # tool
                parts = [types.Part.from_function_response(name=r["call"].name, response=r["output"])
                         for r in m["results"]]
                out.append(types.Content(role="user", parts=parts))
        return out

    def generate(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        decls = [types.FunctionDeclaration(name=t.name, description=t.description, parameters=_schema(t.parameters))
                 for t in tools]
        cfg = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=decls)],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # manual loop: we log it
            temperature=0.0,  # deterministic SQL
            thinking_config=(types.ThinkingConfig(thinking_level=config.GEMINI_THINKING_LEVEL)
                             if config.GEMINI_THINKING_LEVEL else None),
        )
        contents = self._to_contents(messages)
        resp = call_with_retries(
            lambda: self.client.models.generate_content(model=self.model, contents=contents, config=cfg),
            _classify, config.LLM_MAX_RETRIES, f"Gemini ({self.model})")
        u = resp.usage_metadata
        usage = {"prompt": u.prompt_token_count or 0, "output": u.candidates_token_count or 0,
                 "thoughts": u.thoughts_token_count or 0} if u else {}
        calls = [ToolCall(id=c.id or c.name, name=c.name, args=dict(c.args or {})) for c in (resp.function_calls or [])]
        return LLMTurn(text=(resp.text or "").strip() if not calls else "", tool_calls=calls,
                       raw=resp.candidates[0].content if calls else None, usage=usage)
