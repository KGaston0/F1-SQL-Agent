"""Evaluates the agent against the golden set (tests/golden/sql_golden.json).

The expected answer of each case is NOT hand-written: it is computed by running `expected_sql` on the real DB
(ground truth). A case passes if every expected value appears in the agent's answer.

Usage:
    python scripts/evaluate.py --check-truth     # only print the expected truth (no LLM calls)
    python scripts/evaluate.py                   # run the whole set
    python scripts/evaluate.py S01 S05 X01       # only those ids
Output: console table + data/logs/eval_<timestamp>.md and .json
"""
import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.database.connection import execute_select  # noqa: E402

GOLDEN = config.ROOT / "tests" / "golden" / "sql_golden.json"


def norm(text: str) -> str:
    """Lowercase, no accents, no thousands separators (1.172 / 1,172 -> 1172)."""
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", t)


def expected_tokens(sql: str) -> list[str]:
    rows = execute_select(sql).rows
    out = []
    for row in rows:
        for cell in row:
            if isinstance(cell, float) and cell.is_integer():
                cell = int(cell)
            out.append(norm(cell))
    return out


def contains(answer_norm: str, token: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", answer_norm) is not None


def tool_outputs(res, tool_name: str) -> list[dict]:
    """Read the outputs recorded in the provider-neutral conversation history."""
    outputs = []
    for message in res.history:
        if message.get("role") != "tool":
            continue
        for item in message.get("results", []):
            if item["call"].name == tool_name:
                outputs.append(item["output"])
    return outputs


def judge(case: dict, res) -> tuple[str, str]:
    """Returns (verdict, detail). Verdicts: PASS | FAIL | REVIEW."""
    ans = norm(res.answer)
    if res.status != "ok":
        return "FAIL", f"status {res.status}"
    if case.get("expect") == "refuse":
        ran_sql = any(s.get("tool") == "query_sql" and s.get("ok") for s in res.steps)
        return ("FAIL", "ran SQL successfully") if ran_sql else ("REVIEW", "ran nothing; read the answer")
    if case.get("expect") == "review":
        return "REVIEW", "manual judgment"
    if "must_contain_any" in case:
        ok = any(contains(ans, norm(t)) for t in case["must_contain_any"])
        return ("PASS", "") if ok else ("FAIL", f"missing any of {case['must_contain_any']}")
    tokens = case.get("_tokens", [])
    missing = [t for t in tokens if not contains(ans, t)]
    if missing:
        return "FAIL", f"missing {missing}"

    if expected_source := case.get("expected_pdf_source"):
        hits = [
            hit
            for output in tool_outputs(res, "search_documents")
            for hit in output.get("results", [])
            if hit.get("source") == expected_source
        ]
        if not hits:
            return "FAIL", f"did not retrieve {expected_source}"
        passages = norm(" ".join(hit.get("text", "") for hit in hits))
        missing_terms = [term for term in case.get("expected_pdf_terms", [])
                         if norm(term) not in passages]
        if missing_terms:
            return "FAIL", f"retrieved passages missing {missing_terms}"
        citations = {
            int(page)
            for page in re.findall(
                rf"\[{re.escape(expected_source)},\s*PDF p\.\s*(\d+)\]", res.answer, flags=re.I
            )
        }
        if not citations.intersection({int(hit["page"]) for hit in hits}):
            return "FAIL", "answer did not cite a retrieved source page"
    return "PASS", ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*", help="case ids to run (default: all)")
    ap.add_argument("--check-truth", action="store_true", help="only print the expected truth, no LLM calls")
    args = ap.parse_args()

    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))
    if args.ids:
        cases = [c for c in cases if c["id"] in args.ids]
    for c in cases:
        if "expected_sql" in c:
            c["_tokens"] = expected_tokens(c["expected_sql"])

    if args.check_truth:
        for c in cases:
            truth = c.get("_tokens", c.get("must_contain_any", c.get("expected_pdf_source", c.get("expect"))))
            print(f"{c['id']}  {c['question']}\n      truth: {truth}")
        return 0

    from src.agent.agent import Agent  # late import: --check-truth does not need the API

    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    agent = Agent()
    rows, results = [], []
    for c in cases:
        res = agent.ask(c["question"])
        if res.status == "quota":  # without quota there is no point in continuing: stop and report
            print(f"\nSTOP: {res.answer}\nResults so far are saved below; resume with the remaining ids.")
            break
        verdict, detail = judge(c, res)
        sqls = [s["args"].get("sql", "") for s in res.steps if s.get("tool") == "query_sql"]
        pdf_sources = sorted({
            f"{hit['source']} p. {hit['page']}"
            for output in tool_outputs(res, "search_documents")
            for hit in output.get("results", [])
            if hit.get("source") and hit.get("page")
        })
        print(f"{c['id']:4} {verdict:7} {res.elapsed_s:5.1f}s  {c['question'][:60]}")
        rows.append((c, res, verdict, detail))
        results.append({"id": c["id"], "category": c["category"], "question": c["question"], "verdict": verdict,
                        "detail": detail, "answer": res.answer, "sql": sqls, "pdf_sources": pdf_sources,
                        "elapsed_s": res.elapsed_s,
                        "tokens": res.tokens, "retries": sum(1 for s in res.steps if not s.get("ok"))})

    auto = [r for r in rows if r[2] in ("PASS", "FAIL")]
    passed = sum(1 for r in auto if r[2] == "PASS")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    (config.LOG_PATH.parent / f"eval_{stamp}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# Agent evaluation ({stamp})", "", f"Model: `{agent.model}` · "
          f"Automatic passes: **{passed}/{len(auto)}** · Manual review: {len(rows) - len(auto)}", "",
          "| Id | Category | Verdict | Sec. | SQL queries | Detail |", "|---|---|---|---|---|---|"]
    for c, res, verdict, detail in rows:
        md.append(f"| {c['id']} | {c['category']} | {verdict} | {res.elapsed_s} | {len(res.steps)} | {detail} |")
    (config.LOG_PATH.parent / f"eval_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nAutomatic passes: {passed}/{len(auto)}  | manual review: {len(rows) - len(auto)}"
          f"\nDetails in {config.LOG_PATH.parent / f'eval_{stamp}.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
