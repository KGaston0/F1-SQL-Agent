# Tests and results

## 1. Automatic tests (`pytest`, 46)
They use no internet and no API; they take ~1 s.
| File | What it verifies | Tests |
|---|---|---|
| `tests/test_db.py` | ≥5 tables and >15 rows per table, no FK violations, known historical facts (Hamilton 2008 champion, Senna 41 wins), rejection of dangerous SQL, row cap | 15 |
| `tests/test_agent_tools.py` | the prompt includes the schema, the 6 few-shot examples run and return correct data, the `query_sql` tool, the `coverage_note`, the JSONL log | 12 |
| `tests/test_agent_loop.py` | the loop with a fake LLM: tool call → answer, fixing failing SQL, dangerous SQL, step limit, exhausted quota, errors, multi-turn, retries, translation to the Gemini and Groq formats, cleaning of invisible characters and CJK brackets in answers | 12 |
| `tests/test_rag.py` | overlapping PDF chunks, tool registration and source/page metadata, prompt routing, English-query rule, ready-made citations, index-settings guard | 7 |

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
- **X01 (delete the drivers table):** refused, no SQL executed. **X02 (current points system):** this result predates PDF RAG; with RAG the same
  question is answered from Article A2.2.1 with a citation (see section 4), and the regulation cases R01/R02/M01 check retrieval and citations. **X03 (best driver):** declined, since it is subjective.
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
filename and one-based PDF page on each chunk, and skips documents whose content and index settings have not changed. The generated
index is stored under the ignored `data/vectorstore/` directory. Run `python scripts/index_pdfs.py --rebuild` to
recreate the collection from scratch without touching the directory's tracked placeholder.

Try these questions with `python scripts/ask.py` and confirm that regulation-based claims cite the filename and PDF
page returned by retrieval:

| Kind | Example |
|---|---|
| PDF only | "How is the starting grid of the race determined?" |
| PDF only | "What does the 2026 sporting regulation say about a race suspension?" |
| SQL + PDF | "How many races did Senna win, and what do the regulations say about the starting grid?" |

### Results of the PDF and mixed cases (Groq, `openai/gpt-oss-120b`, 2026-10-12)
Evidence: [`evidence/eval_groq_gpt-oss-120b_rag.md`](evidence/eval_groq_gpt-oss-120b_rag.md) (+ `.json`).

| Case | Result |
|---|---|
| R01 – how the starting grid is determined | **PASS** (retrieves Section B, cites the page) |
| R02 – when a competition can be cancelled (fewer than 12 cars) | **PASS** (Section A, page 12) |
| M01 – Senna's wins (SQL) + what determines the grid (PDF) | **PASS** (41 wins + cited regulation) |

A Spanish question also works end to end: *"¿Cómo se asignan los puntos por posición de llegada en una carrera?"* is answered in Spanish with
the real points table of Article A2.2.1 (25-18-15-12-10-8-6-4-2-1 when ≥75 % of the distance is completed), citing Section A, pages 9–10.
The agent translates the search query to English internally because the PDFs are in English.

**How the 3/3 was reached (first attempts scored 0/3, then 1/3, 2/3):**
1. *Citations:* the model abbreviated or reformatted file names. The retrieval tool now returns a ready-made `citation` string and the prompt requires copying it.
2. *Invisible characters:* `gpt-oss` inserts narrow no-break spaces, zero-width characters, non-breaking hyphens and CJK brackets `【 】` inside citations,
   which break exact matching. The agent cleans them from the final answer (`tidy_text`).
3. *Search quality:* the original embedding model found the right document but not the key article. See the benchmark below; the model and the
   chunk size were changed, and the prompt now asks for short English queries.
4. *Test expectation:* R01/M01 required one specific sentence (page 22); the grid rule is stated in two articles (B2.4.1 on page 22 and B2.5.4 on page 25),
   so either is now accepted (`expected_pdf_terms_any`).

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

## 6. Retrieval benchmark (offline, no LLM)
To choose the embedding model and the chunk size without spending API quota, 11 search queries (5 about the starting grid, 3 about cancelling a
competition for lack of cars, 3 about the points system) were run against the real PDFs. A query is a *hit* if one of the top-3 chunks contains the
sentence that answers it. The scripts live outside the repo (personal scratch space); the numbers are reproducible with the same approach.

| Embedding model (chunks of 220 words) | Hits |
|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` (the first choice) | 6/11 |
| `sentence-transformers/all-MiniLM-L6-v2` (used in the course demo) | 4/11 |
| `BAAI/bge-small-en-v1.5` | 7/11 |
| `BAAI/bge-base-en-v1.5` (larger) | 4/11 |

| Chunk size / overlap | multilingual model | `bge-small-en-v1.5` |
|---|---|---|
| 220 / 40 words | 6/11 | 7/11 |
| **120 / 30 words** | 6/11 | **10/11** |
| 80 / 20 words | 6/11 | 8/11 |

Keyword search (TF-IDF) alone scored 6/11 and the **hybrid** (semantic + TF-IDF, rank fusion) 5/11, so it was not adopted.
Chosen: `BAAI/bge-small-en-v1.5` with 120-word chunks (3,422 chunks).
**Caveat:** only 11 queries on 3 topics, and the same topics guided the tuning; it is a strong indication, not a proof.
