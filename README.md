# SQL + RAG Agent – Formula 1

An assistant that answers natural-language questions (English or Spanish) about Formula 1 history and regulations.
It combines *text-to-SQL* over a SQLite database with **real data from 1950 to today** and RAG over local PDF
regulations. The LLM decides which source to query through *function calling*.

> **Status (2026-10-12):** database ✅ · SQL agent ✅ · PDF RAG ✅ ·  report ⏳

## Quick start
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then paste the API key (see table)
python scripts/index_pdfs.py    # builds/refreshes the local index in data/vectorstore
python scripts/ask.py "How many races did Senna win?"
python scripts/ask.py --provider groq --list-models
python scripts/ask.py --provider groq --choose-model
python scripts/ask.py --provider groq --model openai/gpt-oss-120b "How are points awarded by finishing position?"
```
The first indexing run downloads the configured embedding model. Add regulation PDFs to `data/pdfs` and run the
indexing command again when documents change. The vector index is local and ignored by Git; each clone must build it.
The database ships prebuilt in `data/db/f1.db`. To rebuild it from scratch: `python scripts/init_db.py`
(downloads the data from a public API; ~40 min the first time because of the API rate limit).

**LLM** (chosen with `LLM_PROVIDER` in `.env`; both have a free plan):
| Provider | Variable | Where to get the key |
|---|---|---|
| `groq` (used for the evaluation) | `GROQ_API_KEY` | https://console.groq.com/keys |
| `gemini` | `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

Use `--provider groq` or `--provider gemini` to override `.env` for one run. See the models your account
can use with `python scripts/ask.py --provider groq --list-models` (or `gemini`), choose interactively with
`--choose-model`, or pass a model ID directly with `--model MODEL_ID`. The model list is fetched from the
provider and requires that provider's API key. Groq's free-tier tokens-per-minute limit still applies to each
model; changing models does not guarantee a higher quota.

## Tests
```
pytest                       # offline suite; no internet or LLM API calls
python scripts/evaluate.py --check-truth  # inspect expected answers without LLM calls
python scripts/evaluate.py R01 R02 M01    # three PDF and mixed SQL + PDF cases; uses LLM API quota
```
See [testing and manual examples](docs/testing.md) for model selection, smoke-test questions, and expected checks.

## Layout
- `src/database/` schema, data loading and read-only access · `src/agent/` agent loop, prompt, tools and LLM providers
- `scripts/` `ask.py`, `init_db.py`, `evaluate.py` · `tests/` tests and *golden set* · `data/` database and PDFs
- `docs/` [data-model](docs/data-model.md) · [architecture](docs/architecture.md) · [testing](docs/testing.md) ·
  [evidence](docs/evidence/) · [report](docs/report/report.md) (in Spanish, as required)

Working on this repo as a team? Read [AGENTS.md](AGENTS.md) (conventions, decisions, git workflow, pending work split).

## Assignment requirements
- [x] Relational database with ≥5 tables and >15 rows per table (11 tables, the smallest has 77 rows)
- [x] Answers natural-language questions using the database (19/19 in the automatic evaluation)
- [x] RAG over ≥2 PDFs (FIA 2026 Sections A/B/C and 2027 Section C)
- [ ] Graphical interface (the only promotion item chosen)
- [ ] Report of up to 10 pages

Due: 2026-10-16 23:59.
