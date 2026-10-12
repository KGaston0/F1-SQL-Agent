"""Tests for the F1 database. They require `python scripts/init_db.py` to have been run (or the shipped f1.db)."""
import sqlite3

import pytest

from src import config
from src.database.connection import SQLNotAllowed, connect_readonly, execute_select

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="Run scripts/init_db.py first")


@pytest.fixture(scope="module")
def db():
    conn = connect_readonly()
    yield conn
    conn.close()


def _tables(db):
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def test_at_least_5_tables(db):
    assert len(_tables(db)) >= 5


def test_every_table_has_more_than_15_rows(db):
    for t in _tables(db):
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        assert n > 15, f"{t} has only {n} rows"


def test_no_foreign_key_violations():
    conn = sqlite3.connect(config.DB_PATH)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_known_historical_facts(db):
    # Verifiable F1 history (also serves as ground truth for the agent)
    assert db.execute("SELECT MIN(year) FROM races").fetchone()[0] == 1950
    champ = db.execute(
        "SELECT d.forename || ' ' || d.surname FROM driver_standings s JOIN drivers d USING(driver_id) "
        "WHERE s.year = 2008 AND s.position = 1").fetchone()[0]
    assert champ == "Lewis Hamilton"
    wins = db.execute("SELECT COUNT(*) FROM v_results WHERE driver_id='senna' AND position = 1").fetchone()[0]
    assert wins == 41
    first = db.execute("SELECT driver FROM v_results WHERE year=1950 AND round=1 AND position=1").fetchone()[0]
    assert first == "Nino Farina"


def test_positions_and_points_are_consistent(db):
    assert db.execute("SELECT COUNT(*) FROM results WHERE points < 0").fetchone()[0] == 0
    # every race with results has a winner; only 3 historic races had a shared win
    # (France 1951, Argentina 1956, Great Britain 1957)
    no_winner = db.execute(
        "SELECT COUNT(*) FROM (SELECT race_id FROM results GROUP BY race_id "
        "HAVING SUM(position = 1) = 0)").fetchone()[0]
    shared = db.execute(
        "SELECT COUNT(*) FROM (SELECT race_id FROM results GROUP BY race_id "
        "HAVING SUM(position = 1) > 1)").fetchone()[0]
    assert no_winner == 0
    assert shared == 3


def test_valid_select():
    res = execute_select("SELECT COUNT(*) AS n FROM drivers;")
    assert res.columns == ["n"] and res.rows[0][0] > 15


@pytest.mark.parametrize("sql", [
    "DROP TABLE drivers",
    "DELETE FROM drivers",
    "INSERT INTO status VALUES (9999, 'x')",
    "UPDATE drivers SET forename = 'x'",
    "SELECT 1; DROP TABLE drivers",
    "PRAGMA writable_schema = 1",
    "ATTACH DATABASE 'x.db' AS x",
    "WITH t AS (SELECT 1) DELETE FROM drivers",
])
def test_dangerous_sql_is_rejected(sql):
    with pytest.raises(SQLNotAllowed):
        execute_select(sql)


def test_row_cap():
    res = execute_select("SELECT * FROM results", max_rows=10)
    assert len(res.rows) == 10 and res.truncated
