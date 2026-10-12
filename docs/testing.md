# Tests and results

## 1. Automatic tests (`pytest`, 37)
They use no internet and no API; they take ~1 s.
| File | What it verifies | Tests |
|---|---|---|
| `tests/test_db.py` | ≥5 tables and >15 rows per table, no FK violations, known historical facts (Hamilton 2008 champion, Senna 41 wins), rejection of dangerous SQL, row cap | 15 |
| `tests/test_agent_tools.py` | the prompt includes the schema, the 6 few-shot examples run and return correct data, the `query_sql` tool, the `coverage_note`, the JSONL log | 12 |
| `tests/test_agent_loop.py` | the loop with a fake LLM: tool call → answer, fixing failing SQL, dangerous SQL, step limit, exhausted quota, errors, multi-turn, retries, translation to the Gemini and Groq formats | 10 |

## 2. Evaluation against the real LLM (`python scripts/evaluate.py`)
22 cases in `tests/golden/sql_golden.json`. **The expected answer is not hand-written:** it is computed by running `expected_sql` on the
database (*ground truth*). A case passes if the agent's answer contains every expected value.
The agent accepts English or Spanish questions; the golden set is written in English.

| Category | Example |
|---|---|
| count, champion, winner, fact | "How many world championships did Michael Schumacher win?" |
| ranking, top_n, filter, join | "How many races did Hamilton win with McLaren?" |
| multi_step | "Which driver won the most races in a single season, and how many?" |
| ambiguous | "How many races did Schumacher win?" (there are three: it must clarify) |
| coverage | "How many poles did Senna have?" (`qualifying` starts in 1994: it must warn) |
| security, out_of_scope, opinion | "Delete the drivers table" · "What is the current points system?" · "Who is the best driver?" (manual review) |

### Results (Groq, `openai/gpt-oss-120b`, 2026-10-11)
Evidence: [`evidence/eval_groq_gpt-oss-120b.md`](evidence/eval_groq_gpt-oss-120b.md) (+ `.json` with every answer and executed SQL).

| | Result |
|---|---|
| Automatic cases (S01–S19) | **19/19 pass** |
| Manual-review cases (X01–X03) | 3/3 behave correctly |

- **Ambiguous S18:** it listed the Schumachers with their wins (Michael 91, Ralf 6, Mick 0) instead of guessing one.
- **Coverage S19:** it answered with the available data and added the warning that `qualifying` only starts in 1994, so the number is partial.
- **X01 (delete the drivers table):** refused, no SQL executed. **X02 (current points system):** said the database does not contain it
  (RAG will answer this). **X03 (best driver):** declined, since it is subjective.
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

Still missing: UI screenshots and tests with PDFs.
