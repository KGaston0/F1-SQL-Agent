"""Command-line questions to the agent (to try it without the UI).

Usage (from the repo root):
    python scripts/ask.py "How many races did Senna win?"
    python scripts/ask.py --provider groq --list-models
    python scripts/ask.py --provider groq --choose-model
    python scripts/ask.py --provider gemini --model gemini-3.5-flash "How are points awarded?"
    python scripts/ask.py            # interactive mode (empty Enter to quit)
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.agent import Agent  # noqa: E402
from src.agent.llm import get_provider, list_available_models  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask the Formula 1 SQL + PDF agent.")
    parser.add_argument("question", nargs="*", help="Question to ask; omit for interactive mode.")
    parser.add_argument("--provider", choices=("groq", "gemini"), help="Override LLM_PROVIDER in .env.")
    parser.add_argument("--model", help="Model ID; use --list-models to see account options.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--list-models", action="store_true", help="List text-generation models available to your account.")
    selection.add_argument("--choose-model", action="store_true", help="Choose a listed model from an interactive menu.")
    return parser


def _choose_model(models: list[str]) -> str:
    if not models:
        raise RuntimeError("No text-generation models were returned for this account.")
    for index, model in enumerate(models, start=1):
        print(f"{index}. {model}")
    while True:
        choice = input("Model number: ").strip()
        try:
            selected = int(choice)
            if 1 <= selected <= len(models):
                return models[selected - 1]
        except ValueError:
            pass
        print(f"Enter a number from 1 to {len(models)}.")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = _parser().parse_args(argv)
    provider_name = args.provider
    try:
        if args.list_models or args.choose_model:
            models = list_available_models(provider_name)
            if args.list_models:
                print("\n".join(models) if models else "No text-generation models were returned for this account.")
                return 0
            args.model = _choose_model(models)
        provider = get_provider(name=provider_name, model=args.model)
        agent = Agent(provider=provider)
    except RuntimeError as e:  # e.g. missing API key: show the message, not a traceback
        print(f"Setup error: {e}", file=sys.stderr)
        return 1

    questions = [" ".join(args.question)] if args.question else None
    while True:
        q = questions.pop(0) if questions else (input("\n> ").strip() if questions is None else "")
        if not q:
            return 0
        res = agent.ask(q)
        print(f"\n{res.answer}\n[{res.status} | {res.elapsed_s}s | {len(res.steps)} tool calls | tokens {res.tokens}]")
        if questions is not None and not questions:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
