"""Interchangeable LLM providers. Chosen with LLM_PROVIDER in .env ('gemini' | 'groq')."""
from src import config
from src.agent.llm.base import LLMProvider, LLMTurn, QuotaExhausted, ToolCall, ToolSpec


def get_provider(name: str | None = None, model: str | None = None) -> LLMProvider:
    name = (name or config.LLM_PROVIDER).lower()
    if name == "gemini":
        from src.agent.llm.gemini import GeminiProvider
        return GeminiProvider(model=model)
    if name == "groq":
        from src.agent.llm.groq_provider import GroqProvider
        return GroqProvider(model=model)
    raise ValueError(f"Unknown LLM provider: {name!r} (use 'gemini' or 'groq')")


__all__ = ["LLMProvider", "LLMTurn", "QuotaExhausted", "ToolCall", "ToolSpec", "get_provider"]
