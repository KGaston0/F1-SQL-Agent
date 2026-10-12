"""Command-line questions to the agent (to try it without the UI).

Usage (from the repo root):
    python scripts/ask.py "How many races did Senna win?"
    python scripts/ask.py            # interactive mode (empty Enter to quit)
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.agent import Agent  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        agent = Agent()
    except RuntimeError as e:  # e.g. missing API key: show the message, not a traceback
        print(f"Setup error: {e}", file=sys.stderr)
        return 1

    questions = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else None
    while True:
        q = questions.pop(0) if questions else (input("\n> ").strip() if questions is None else "")
        if not q:
            return 0
        res = agent.ask(q)
        print(f"\n{res.answer}\n[{res.status} | {res.elapsed_s}s | {len(res.steps)} SQL queries | tokens {res.tokens}]")
        if questions is not None and not questions:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
