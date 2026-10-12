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


def list_available_models(name: str | None = None) -> list[str]:
    """List models visible to the configured account that can handle text generation."""
    name = (name or config.LLM_PROVIDER).lower()
    if name == "groq":
        from src.agent.llm.groq_provider import GroqProvider

        provider = GroqProvider()
        excluded = ("whisper", "guard", "embed", "speech", "orpheus")
        models = provider.client.models.list()
        return sorted(
            model.id for model in models.data
            if getattr(model, "active", True)
            and (getattr(model, "context_window", 0) or 0) >= 8192
            and not any(term in model.id.lower() for term in excluded)
        )
    if name == "gemini":
        from src.agent.llm.gemini import GeminiProvider

        provider = GeminiProvider()
        models = provider.client.models.list()
        names = []
        for model in models:
            actions = getattr(model, "supported_actions", None) or []
            if "generateContent" in actions:
                names.append(getattr(model, "base_model_id", None) or model.name.removeprefix("models/"))
        return sorted(set(names))
    raise ValueError(f"Unknown LLM provider: {name!r} (use 'gemini' or 'groq')")


__all__ = ["LLMProvider", "LLMTurn", "QuotaExhausted", "ToolCall", "ToolSpec", "get_provider",
           "list_available_models"]
