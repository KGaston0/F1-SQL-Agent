# AGENTS.md – guide for contributors and coding assistants

Read this before changing anything. For the user-facing overview see `README.md`.

## What this project is
University assignment: an agent that answers natural-language questions about Formula 1 by combining
**text-to-SQL** over a SQLite database (real data, 1950–today) and, still pending, **RAG** over PDFs.
Only promotion item chosen: a basic UI (Streamlit). Due **2026-10-16 23:59**.

## Setup (Windows)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # set LLM_PROVIDER and ONE api key (your own, never shared)
pytest                      # must be green before every push
python scripts/ask.py "How many races did Senna win?"
```
The database ships prebuilt (`data/db/f1.db`); you do not need `scripts/init_db.py` unless the schema changes.

## Repository map
| Path | Purpose |
|---|---|
| `src/database/schema.sql` | **Single source of truth** for the schema; also injected into the LLM prompt |
| `src/database/` | `jolpica.py` (API client + cache), `builder.py` (load), `connection.py` (read-only SQL access) |
| `src/agent/agent.py` | Agent loop: LLM ↔ tools, step limit, logging |
| `src/agent/prompts.py` | System prompt: rules, domain hints, few-shot examples, compacted schema |
| `src/agent/tools.py` | Tools exposed to the LLM (`query_sql` today) + coverage warnings |
| `src/agent/llm/` | Provider layer (`gemini.py`, `groq_provider.py`) behind one neutral interface |
| `src/rag/`, `src/ui/` | Pending (PDF RAG, Streamlit UI) |
| `tests/` | Offline tests (`test_*.py`) and the golden set (`golden/sql_golden.json`) |
| `scripts/` | `ask.py` (CLI), `evaluate.py` (golden-set run), `init_db.py` (rebuild DB) |
| `docs/` | `data-model`, `architecture`, `testing`, `evidence/`, `report/` (Spanish) |
| `private/` | Personal notes, **gitignored** – never commit |

## Conventions
- **Language:** everything is in English – code, identifiers, comments, docstrings, commit messages, docs, prompts, tests.
  The only exception is the final report (`docs/report/`), which must be delivered in Spanish.
- Python 3.12, type hints where they help, short docstrings explaining *why*. No frameworks for the agent loop (deliberate).
- Keep the code explainable: every teammate must be able to defend each piece in the oral exam. Prefer simple over clever.
- Never commit secrets: `.env` is gitignored; only `.env.example` is tracked. Each person uses their own API key.
- Do not commit `data/raw/` (API cache), `data/logs/`, `data/vectorstore/`, `.venv/`, `private/` (all gitignored).

## Architecture decisions (do not reverse without discussing)
1. **Real data, not synthetic**, so answers can be verified against history.
2. **SQLite**, one file, no server – the grader must be able to run it easily.
3. **Own agent loop with native function calling**, no LangChain/LangGraph.
4. **The LLM never gets write access.** SQL goes through `execute_select`: read-only connection, SQLite authorizer,
   single `SELECT`/`WITH` statement, row cap and timeout. Do not add a code path that bypasses it.
5. **Partial tables must warn.** If a query touches `qualifying` (1994+), `sprint_results` (2021+) or
   `constructor_standings` (1958+), the tool adds `coverage_note` and the prompt forces the LLM to include it
   (`COVERAGE_NOTES` in `tools.py`). Add new partial tables there.
6. **Provider-agnostic agent:** `agent.py` knows nothing about Gemini/Groq SDKs. New provider = new file in `src/agent/llm/`
   implementing `LLMProvider.generate` + registration in `llm/__init__.py`.
7. **Evaluation by golden set:** expected answers are computed with `expected_sql` on the real DB, never hand-typed.
8. **Schema changes** go in `schema.sql` first, then `builder.py`, then `docs/data-model.md`; rebuild with
   `python scripts/init_db.py --offline` (needs the local cache) and commit the new `data/db/f1.db`.

## How to…
- **Add a tool:** define a `ToolSpec` and a function in `src/agent/tools.py`, add it to `TOOLS` and `REGISTRY`, mention when to use it in
  the prompt rules (`prompts.py`), add tests in `tests/test_agent_tools.py`.
- **Add an evaluation case:** append to `tests/golden/sql_golden.json` (`id`, `category`, `lang`, `question`, `expected_sql`).
  Check with `python scripts/evaluate.py --check-truth` before spending API quota.
- **Change the prompt:** re-run at least the hard cases (`python scripts/evaluate.py S05 S16 S18 S19 X01`) and note the result in `docs/testing.md`.

## LLM quotas (important with 3 people)
Free plans are tight: Gemini ≈ 20 requests/day per model; Groq 1,000 requests/day but **8,000 tokens/minute** per model.
A full `evaluate.py` run takes ~30–40 min and uses a large part of Groq's daily tokens – coordinate before running it and
prefer subsets by id. Offline tests (`pytest`) never touch the API.

## Git workflow
- `main` stays working. Work on a branch (`feat/<topic>`, `fix/<topic>`), open a PR, one teammate reviews, then merge.
- Small commits with imperative messages in English ("Add PDF ingestion script").
- Run `pytest` before pushing. If you touch the agent, prompt or tools, also run a relevant subset of `evaluate.py`.
- Avoid editing the same file from two branches at once; the suggested split below keeps areas separate.

## Pending work and suggested split
| Area | Files | Notes |
|---|---|---|
| RAG | `src/rag/`, new `search_documents` tool, `data/pdfs/` (≥2 PDFs) | Chunk → embed locally → ChromaDB → top-k with file+page; add mixed SQL+PDF cases to the golden set |
| UI | `src/ui/app.py` | Streamlit chat; show the executed SQL and PDF sources per answer; reuse `Agent.ask(..., history=...)` |
| Report & polish | `docs/report/`, `requirements.txt` (pin versions), screenshots | Report ≤ 10 pages, Spanish; use `docs/evidence/` and `private/` notes as raw material |
