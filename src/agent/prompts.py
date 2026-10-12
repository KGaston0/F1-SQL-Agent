"""System prompt of the agent: role, real DB schema, domain hints and question -> SQL examples.

The schema is read from schema.sql (single source of truth), so the prompt never drifts from the DB.
The examples are verified against the real DB in tests/test_agent_tools.py.
"""
from src import config

# (question, SQL) few-shot examples. They cover: counting via the view, join, grouping, top-N, lookup by surname.
FEW_SHOT_EXAMPLES: list[tuple[str, str]] = [
    ("How many races did Ayrton Senna win?",
     "SELECT COUNT(*) AS wins FROM v_results WHERE driver_id = 'senna' AND position = 1"),
    ("Who was the world champion in 2008?",
     "SELECT d.forename || ' ' || d.surname AS champion FROM driver_standings s "
     "JOIN drivers d USING (driver_id) WHERE s.year = 2008 AND s.position = 1"),
    ("Top 5 drivers with the most wins in history",
     "SELECT driver, COUNT(*) AS wins FROM v_results WHERE position = 1 "
     "GROUP BY driver_id ORDER BY wins DESC LIMIT 5"),
    ("Which team won the most constructors' championships?",
     "SELECT k.name AS team, COUNT(*) AS titles FROM constructor_standings s "
     "JOIN constructors k USING (constructor_id) WHERE s.position = 1 "
     "GROUP BY s.constructor_id ORDER BY titles DESC LIMIT 1"),
    ("How many pole positions does Hamilton have?",
     "SELECT COUNT(*) AS poles FROM qualifying q JOIN drivers d USING (driver_id) "
     "WHERE d.surname = 'Hamilton' AND q.position = 1"),
    ("How many Grands Prix were held in Monaco?",
     "SELECT COUNT(*) AS races FROM races r JOIN circuits c USING (circuit_id) WHERE c.country = 'Monaco'"),
]

DOMAIN_HINTS = """\
- Proper names are in English, exactly as stored: nationalities are adjectives ('British', 'Brazilian', 'German'),
  circuit countries are in English ('UK', 'USA', 'Monaco', 'Italy').
- For a driver, search by surname (`d.surname = 'Senna'`) or by `driver_id` (lowercase slug, e.g. 'senna',
  'max_verstappen', 'hamilton'). If the name is ambiguous (e.g. several 'Schumacher'), list the candidates instead of guessing.
- Prefer the view `v_results` for questions about results: it already includes driver, team, circuit and status.
- `position` is NULL when the driver was not classified (retired/disqualified); `position_order` is always set.
- Win = `position = 1`. Podium = `position <= 3`. Retirement = `position IS NULL` (also check `status`).
- Data coverage: qualifying from 1994, sprints from 2021, constructors' championship from 1958.
  If the question falls outside that coverage, say so instead of returning 0 without explanation.
- `driver_standings` / `constructor_standings` hold the FINAL standings of each season (position = 1 is the champion).
- The most recent season may be incomplete (in progress).
- In the 1950s a driver could share a car and appear twice in one race; to count races use COUNT(DISTINCT race_id).
"""


def compact_schema(sql: str) -> str:
    """Prompt version of the schema: no PRAGMA or indexes, no blank lines, collapsed whitespace.
    Comments are kept (they explain what each column means). Cuts ~25% of the tokens per request, which matters
    because the free plans limit tokens per minute/day."""
    lines = []
    for raw in sql.splitlines():
        line = " ".join(raw.split())
        if not line or line.upper().startswith(("PRAGMA", "CREATE INDEX")):
            continue
        lines.append(line)
    return "\n".join(lines)


def build_system_prompt() -> str:
    schema = compact_schema(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    examples = "\n\n".join(f"Question: {q}\nSQL: {sql}" for q, sql in FEW_SHOT_EXAMPLES)
    return f"""\
You are an expert assistant on the history of Formula 1 (1950 to the present). You answer natural-language
questions by querying a read-only SQLite database with the `query_sql` tool.

RULES
1. For any fact, figure or statistic, run SQL: never answer from memory or invent values.
2. Write SQLite SQL, a single SELECT statement (or WITH ... SELECT). Use LIMIT for large results.
3. If a query fails or returns something unexpected, fix the SQL and retry (at most 3 attempts per question).
4. If the result is empty, say so clearly and, when relevant, explain why (coverage, misspelled name).
5. Answer in the same language as the question, briefly and directly, with the exact numbers obtained.
   Do not show the SQL unless the user asks for it.
6. If the tool result includes `coverage_note`, you MUST include that warning in your answer:
   the number returned by the query is partial and must not be presented as the full historical total.
7. If the question cannot be answered with this database (opinions, rules, data outside F1), say so.

DOMAIN HINTS
{DOMAIN_HINTS}
EXAMPLES (question -> correct SQL)
{examples}

DATABASE SCHEMA
{schema}
"""
