"""Persistent record of every agent question: one JSON line per run (JSONL).

Used to review later what the agent did, to show evidence in the report and to feed the evaluation.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src import config

log = logging.getLogger("agent")


def write_run(result, model: str) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "status": result.status,
        "question": result.question,
        "answer": result.answer,
        "steps": result.steps,
        "tokens": result.tokens,
        "elapsed_s": result.elapsed_s,
    }
    try:
        config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with config.LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:  # logging must never bring the agent down
        log.warning("Could not write the log: %s", e)
