# SQL + RAG Agent – Formula 1

An assistant that answers natural-language questions (English or Spanish) about Formula 1 history.
It does *text-to-SQL* over a SQLite database with **real data from 1950 to today** and, soon, RAG over PDF documents.
The LLM itself decides which source to query through *function calling*.

> **Status (2026-10-11):** database ✅ · SQL agent ✅ · PDF RAG ⏳ · Streamlit UI ⏳ · report ⏳

## Quick start
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then paste the API key (see table)
python scripts/ask.py "How many races did Senna win?"
```
The database ships prebuilt in `data/db/f1.db`. To rebuild it from scratch: `python scripts/init_db.py`
(downloads the data from a public API; ~40 min the first time because of the API rate limit).

**LLM** (chosen with `LLM_PROVIDER` in `.env`; both have a free plan):
| Provider | Variable | Where to get the key |
|---|---|---|
| `groq` (used for the evaluation) | `GROQ_API_KEY` | https://console.groq.com/keys |
| `gemini` | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

## Tests
```
pytest                       # 37 offline tests: no internet, no API
python scripts/evaluate.py   # 22 questions with a known answer, against the real LLM
```

## Layout
- `src/database/` schema, data loading and read-only access · `src/agent/` agent loop, prompt, tools and LLM providers
- `scripts/` `ask.py`, `init_db.py`, `evaluate.py` · `tests/` tests and *golden set* · `data/` database and PDFs
- `docs/` [data-model](docs/data-model.md) · [architecture](docs/architecture.md) · [testing](docs/testing.md) ·
  [evidence](docs/evidence/) · [report](docs/report/report.md) (in Spanish, as required)

Working on this repo as a team? Read [AGENTS.md](AGENTS.md) (conventions, decisions, git workflow, pending work split).

## Assignment requirements
- [x] Relational database with ≥5 tables and >15 rows per table (11 tables, the smallest has 77 rows)
- [x] Answers natural-language questions using the database (19/19 in the automatic evaluation)
- [ ] RAG over ≥2 PDFs
- [ ] Graphical interface (the only promotion item chosen)
- [ ] Report of up to 10 pages

Due: 2026-10-16 23:59.
