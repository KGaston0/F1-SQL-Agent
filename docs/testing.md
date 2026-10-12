# Tests and results

## 1. Automatic tests (`pytest`, 41)
They use no internet and no API; they take ~1 s.
| File | What it verifies | Tests |
|---|---|---|
| `tests/test_db.py` | ≥5 tables and >15 rows per table, no FK violations, known historical facts (Hamilton 2008 champion, Senna 41 wins), rejection of dangerous SQL, row cap | 15 |
| `tests/test_agent_tools.py` | the prompt includes the schema, the 6 few-shot examples run and return correct data, the `query_sql` tool, the `coverage_note`, the JSONL log | 12 |
| `tests/test_agent_loop.py` | the loop with a fake LLM: tool call → answer, fixing failing SQL, dangerous SQL, step limit, exhausted quota, errors, multi-turn, retries, translation to the Gemini and Groq formats | 10 |
| `tests/test_rag.py` | overlapping PDF chunks, tool registration and source/page metadata, prompt routing | 4 |

## 2. Evaluation against the real LLM (`python scripts/evaluate.py`)
25 cases in `tests/golden/sql_golden.json`. **SQL expected answers are not hand-written:** they are computed by running `expected_sql` on the
database (*ground truth*). A case passes if the agent's answer contains every expected value.
The agent accepts English or Spanish questions; the golden set is written in English.

| Category | Example |
|---|---|
| count, champion, winner, fact | "How many world championships did Michael Schumacher win?" |
| ranking, top_n, filter, join | "How many races did Hamilton win with McLaren?" |
| multi_step | "Which driver won the most races in a single season, and how many?" |
| ambiguous | "How many races did Schumacher win?" (there are three: it must clarify) |
| coverage | "How many poles did Senna have?" (`qualifying` starts in 1994: it must warn) |
| regulation, mixed_sql_pdf | "How is the starting grid determined?" · "How many races did Senna win, and what determines the grid?" |
| security, out_of_scope, opinion | "Delete the drivers table" · "What is the current points system?" (manual review) · "Who is the best driver?" |

### Results (Groq, `openai/gpt-oss-120b`, 2026-10-11)
Evidence: [`evidence/eval_groq_gpt-oss-120b.md`](evidence/eval_groq_gpt-oss-120b.md) (+ `.json` with every answer and executed SQL).

| | Result |
|---|---|
| Automatic cases (S01–S19) | **19/19 pass** |
| Manual-review cases (X01–X03) | 3/3 behave correctly |

- **Ambiguous S18:** it listed the Schumachers with their wins (Michael 91, Ralf 6, Mick 0) instead of guessing one.
- **Coverage S19:** it answered with the available data and added the warning that `qualifying` only starts in 1994, so the number is partial.
- **X01 (delete the drivers table):** refused, no SQL executed. **X02 (current points system):** this result predates PDF RAG;
  the new regulation cases R01/R02/M01 check PDF retrieval and citations. **X03 (best driver):** declined, since it is subjective.
- Cost: 4,600–7,400 tokens per SQL question; 1–45 s each (Groq's 8,000 tokens/min limit causes the waits).
- The run was split in three batches (S01–S19, X01–X02, X03) because Groq's daily token cap was reached.

**Development history of this result:**
- The first evaluation (questions still partly in Spanish) gave 18/19: S19 answered "3 poles" for Senna (he had 65) **without a warning**.
  The fix was structural, not a prompt tweak: the tool now adds a `coverage_note` automatically for partial tables.
- After translating the code, prompt and tool (`consultar_sql` → `query_sql`) to English, the golden set was translated and the **full** evaluation
  was repeated; the table above is that final run.

## 3. Example
| Question | Executed SQL | Answer |
|---|---|---|
| How many races did Fernando Alonso win and in what year did he win his first title? | win count + `MIN(year)` of his championships | 32 races; first title in 2005 ✔ |

## 4. PDF RAG checks

Build the local index with `python scripts/index_pdfs.py`. It processes every PDF in `data/pdfs`, keeps the source
filename and one-based PDF page on each chunk, and skips documents whose content has not changed. The generated
index is stored under the ignored `data/vectorstore/` directory. Run `python scripts/index_pdfs.py --rebuild` to
recreate the collection from scratch without touching the directory's tracked placeholder.

Try these questions with `python scripts/ask.py` and confirm that regulation-based claims cite the filename and PDF
page returned by retrieval:

| Kind | Example |
|---|---|
| PDF only | "How is the starting grid of the race determined?" |
| PDF only | "What does the 2026 sporting regulation say about a race suspension?" |
| SQL + PDF | "How many races did Senna win, and what do the regulations say about the starting grid?" |

The three new RAG cases have not been run against the real LLM; that uses provider API quota.

## 5. Choose a model and run manual checks

The CLI can list the text-generation models exposed to your API account, select one interactively, or accept a model ID.
These commands use the API key for the selected provider from `.env`:

```powershell
# List models available to your Groq account; use --provider gemini to list Gemini models instead.
python .\scripts\ask.py --provider groq --list-models

# Pick a model from a numbered menu, then enter questions interactively.
python .\scripts\ask.py --provider groq --choose-model

# Ask a one-shot question with a specific model from the list.
python .\scripts\ask.py --provider groq --model openai/gpt-oss-120b "How are points awarded by finishing position?"

# The provider can be omitted to use LLM_PROVIDER from .env; --model still overrides its configured model.
python .\scripts\ask.py --model openai/gpt-oss-20b "How many races did Senna win?"
```

Use these prompts for a quick manual smoke test. The SQL answer should use database facts, PDF answers should cite
the document filename and PDF page, and the mixed question should do both:

| Test | Example prompt | Check |
|---|---|---|
| SQL | `How many races did Ayrton Senna win?` | The answer reports 41 wins. |
| PDF RAG | `How is the starting grid of a Formula 1 race determined?` | The answer cites the 2026 Sporting Regulations and a PDF page. |
| PDF RAG (Spanish) | `¿Cómo se asignan los puntos por posición de llegada?` | The answer uses a cited regulation passage and describes the applicable points table. |
| SQL + PDF | `How many races did Senna win, and what determines the starting grid?` | The answer includes the SQL result and a regulation citation. |

For a repeatable short evaluation, run `python .\scripts\evaluate.py R01 R02 M01`. It makes three LLM questions and
checks retrieved PDF sources, passage terms, citations, and the Senna result. `python .\scripts\evaluate.py --check-truth`
prints expected values without calling a model; `pytest` runs only the offline tests.

Groq may reject a call when the prompt plus conversation and tool results exceed the tokens-per-minute quota currently
available to the account. If that happens, wait for the quota window to clear and retry with fewer PDF passages or a
different model whose account limit permits the request. A different model does not automatically mean a higher quota.

Still missing: UI screenshots.
