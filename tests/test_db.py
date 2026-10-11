"""Pruebas de la base de datos de F1. Requieren haber ejecutado `python scripts/init_db.py`."""
import sqlite3

import pytest

from src import config
from src.database.connection import SQLNotAllowed, connect_readonly, execute_select

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists(), reason="Primero ejecutá scripts/init_db.py")

CORE_TABLES = ["circuits", "constructors", "drivers", "races", "results", "seasons", "status"]


@pytest.fixture(scope="module")
def db():
    conn = connect_readonly()
    yield conn
    conn.close()


def _tables(db):
    return [r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]


def test_al_menos_5_tablas(db):
    assert len(_tables(db)) >= 5


def test_cada_tabla_tiene_mas_de_15_registros(db):
    for t in _tables(db):
        n = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        assert n > 15, f"{t} tiene solo {n} filas"


def test_sin_violaciones_de_claves_foraneas():
    conn = sqlite3.connect(config.DB_PATH)
    try:
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def test_datos_historicos_conocidos(db):
    # Hechos verificables de la historia de la F1 (sirven también de ground truth para el agente)
    assert db.execute("SELECT MIN(year) FROM races").fetchone()[0] == 1950
    champ = db.execute(
        "SELECT d.forename || ' ' || d.surname FROM driver_standings s JOIN drivers d USING(driver_id) "
        "WHERE s.year = 2008 AND s.position = 1").fetchone()[0]
    assert champ == "Lewis Hamilton"
    wins = db.execute("SELECT COUNT(*) FROM v_results WHERE driver_id='senna' AND position = 1").fetchone()[0]
    assert wins == 41
    first = db.execute("SELECT driver FROM v_results WHERE year=1950 AND round=1 AND position=1").fetchone()[0]
    assert first == "Nino Farina"


def test_posiciones_y_puntos_coherentes(db):
    assert db.execute("SELECT COUNT(*) FROM results WHERE points < 0").fetchone()[0] == 0
    # toda carrera con resultados tiene ganador; solo 3 carreras históricas tuvieron victoria compartida
    # (Francia 1951, Argentina 1956, Gran Bretaña 1957)
    sin_ganador = db.execute(
        "SELECT COUNT(*) FROM (SELECT race_id FROM results GROUP BY race_id "
        "HAVING SUM(position = 1) = 0)").fetchone()[0]
    compartidas = db.execute(
        "SELECT COUNT(*) FROM (SELECT race_id FROM results GROUP BY race_id "
        "HAVING SUM(position = 1) > 1)").fetchone()[0]
    assert sin_ganador == 0
    assert compartidas == 3


def test_select_valido():
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
def test_sql_peligroso_rechazado(sql):
    with pytest.raises(SQLNotAllowed):
        execute_select(sql)


def test_tope_de_filas():
    res = execute_select("SELECT * FROM results", max_rows=10)
    assert len(res.rows) == 10 and res.truncated
