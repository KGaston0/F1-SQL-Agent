"""Construye la base SQLite de Fórmula 1 a partir de datos históricos reales (API Jolpica-F1).

Flujo: crear esquema -> descargar/leer caché de cada endpoint -> insertar en orden de dependencias
(FKs respetadas) -> verificar integridad. Es idempotente: la BD se recrea desde cero en cada corrida.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from src import config
from src.database.jolpica import JolpicaClient

FIRST_CONSTRUCTOR_CHAMPIONSHIP = 1958  # antes de ese año no existía el campeonato de constructores


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ----------------------------------------------------------------------------- tablas maestras
def _load_seasons(db, client):
    rows = [(int(s["season"]), s.get("url"))
            for p in client.pages("seasons") for s in p["SeasonTable"]["Seasons"]]
    db.executemany("INSERT INTO seasons VALUES (?, ?)", rows)
    return [r[0] for r in rows]


def _load_circuits(db, client):
    rows = []
    for p in client.pages("circuits"):
        for c in p["CircuitTable"]["Circuits"]:
            loc = c.get("Location", {})
            rows.append((c["circuitId"], c["circuitName"], loc.get("locality"), loc.get("country"),
                         _float(loc.get("lat")), _float(loc.get("long")), c.get("url")))
    db.executemany("INSERT INTO circuits VALUES (?, ?, ?, ?, ?, ?, ?)", rows)


def _load_drivers(db, client):
    rows = []
    for p in client.pages("drivers"):
        for d in p["DriverTable"]["Drivers"]:
            rows.append((d["driverId"], d.get("code"), _int(d.get("permanentNumber")), d["givenName"],
                         d["familyName"], d.get("dateOfBirth"), d.get("nationality"), d.get("url")))
    db.executemany("INSERT INTO drivers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)


def _load_constructors(db, client):
    rows = [(c["constructorId"], c["name"], c.get("nationality"), c.get("url"))
            for p in client.pages("constructors") for c in p["ConstructorTable"]["Constructors"]]
    db.executemany("INSERT INTO constructors VALUES (?, ?, ?, ?)", rows)


def _load_status(db, client):
    rows = [(int(s["statusId"]), s["status"])
            for p in client.pages("status") for s in p["StatusTable"]["Status"]]
    db.executemany("INSERT INTO status VALUES (?, ?)", rows)


def _load_races(db, client) -> dict[tuple[int, int], int]:
    races = [r for p in client.pages("races") for r in p["RaceTable"]["Races"]]
    races.sort(key=lambda r: (int(r["season"]), int(r["round"])))
    race_ids: dict[tuple[int, int], int] = {}
    rows = []
    for i, r in enumerate(races, start=1):
        key = (int(r["season"]), int(r["round"]))
        race_ids[key] = i
        rows.append((i, key[0], key[1], r["Circuit"]["circuitId"], r["raceName"], r.get("date"),
                     r.get("time"), r.get("url")))
    db.executemany("INSERT INTO races VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return race_ids


# ----------------------------------------------------------------------------- hechos
class _StatusIds:
    """Resuelve el texto de estado a status_id; crea estados que la tabla maestra no tuviera."""

    def __init__(self, db):
        self.db = db
        self.ids = {s: i for i, s in db.execute("SELECT status_id, status FROM status")}

    def get(self, text: str) -> int:
        if text not in self.ids:
            new_id = max(self.ids.values(), default=0) + 1
            self.db.execute("INSERT INTO status VALUES (?, ?)", (new_id, text))
            self.ids[text] = new_id
        return self.ids[text]


def _load_results(db, client, race_ids, statuses):
    n = total = 0
    for p in client.pages("results"):
        total = int(p["total"])
        for race in p["RaceTable"]["Races"]:
            race_id = race_ids[(int(race["season"]), int(race["round"]))]
            rows = []
            for r in race["Results"]:
                fl = r.get("FastestLap", {})
                t = r.get("Time", {})
                pos_text = r.get("positionText")
                rows.append((
                    race_id, r["Driver"]["driverId"], r["Constructor"]["constructorId"], _int(r.get("number")),
                    _int(r.get("grid")), int(pos_text) if pos_text and pos_text.isdigit() else None, pos_text,
                    int(r["position"]), float(r["points"]), _int(r.get("laps")), statuses.get(r["status"]),
                    t.get("time"), _int(t.get("millis")),
                    _int(fl.get("rank")), _int(fl.get("lap")), fl.get("Time", {}).get("time"),
                ))
            cur = db.executemany(
                "INSERT OR IGNORE INTO results (race_id, driver_id, constructor_id, car_number, grid, position,"
                " position_text, position_order, points, laps, status_id, time_text, milliseconds,"
                " fastest_lap_rank, fastest_lap_number, fastest_lap_time)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            n += cur.rowcount
    if n != total:  # control de completitud contra el total que informa la API
        raise RuntimeError(f"results: se insertaron {n} filas pero la API informa {total}")
    return n


def _load_qualifying(db, client, race_ids):
    n = 0
    for p in client.pages("qualifying"):
        for race in p["RaceTable"]["Races"]:
            race_id = race_ids[(int(race["season"]), int(race["round"]))]
            rows = [(race_id, q["Driver"]["driverId"], q["Constructor"]["constructorId"], _int(q.get("number")),
                     _int(q.get("position")), q.get("Q1"), q.get("Q2"), q.get("Q3"))
                    for q in race["QualifyingResults"]]
            n += db.executemany(
                "INSERT OR IGNORE INTO qualifying (race_id, driver_id, constructor_id, car_number, position,"
                " q1, q2, q3) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows).rowcount
    return n


def _load_sprints(db, client, race_ids, statuses):
    n = 0
    for p in client.pages("sprint"):
        for race in p["RaceTable"]["Races"]:
            race_id = race_ids[(int(race["season"]), int(race["round"]))]
            rows = []
            for r in race["SprintResults"]:
                pos_text = r.get("positionText")
                rows.append((race_id, r["Driver"]["driverId"], r["Constructor"]["constructorId"],
                             _int(r.get("number")), _int(r.get("grid")),
                             int(pos_text) if pos_text and pos_text.isdigit() else None, pos_text,
                             float(r["points"]), _int(r.get("laps")), statuses.get(r["status"]),
                             r.get("Time", {}).get("time")))
            n += db.executemany(
                "INSERT OR IGNORE INTO sprint_results (race_id, driver_id, constructor_id, car_number, grid,"
                " position, position_text, points, laps, status_id, time_text)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows).rowcount
    return n


def _load_standings(db, client, years):
    n_d = n_c = 0
    for year in years:
        for p in client.pages(f"{year}/driverstandings"):
            for sl in p["StandingsTable"]["StandingsLists"]:
                rows = [(year, s["Driver"]["driverId"], _int(s.get("position")), float(s["points"]), int(s["wins"]))
                        for s in sl["DriverStandings"]]
                n_d += db.executemany("INSERT OR IGNORE INTO driver_standings VALUES (?, ?, ?, ?, ?)",
                                      rows).rowcount
        if year < FIRST_CONSTRUCTOR_CHAMPIONSHIP:
            continue
        for p in client.pages(f"{year}/constructorstandings"):
            for sl in p["StandingsTable"]["StandingsLists"]:
                rows = [(year, s["Constructor"]["constructorId"], _int(s.get("position")), float(s["points"]),
                         int(s["wins"])) for s in sl["ConstructorStandings"]]
                n_c += db.executemany("INSERT OR IGNORE INTO constructor_standings VALUES (?, ?, ?, ?, ?)",
                                      rows).rowcount
    return n_d, n_c


# ----------------------------------------------------------------------------- orquestación
def build_database(db_path: Path | None = None, offline: bool = False, refresh: bool = False) -> dict[str, int]:
    """Recrea la BD completa y devuelve el conteo de filas por tabla."""
    db_path = Path(db_path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(".building")
    tmp_path.unlink(missing_ok=True)

    client = JolpicaClient(config.JOLPICA_BASE_URL, config.RAW_DIR, offline=offline, refresh=refresh)
    db = sqlite3.connect(tmp_path)
    try:
        db.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
        _log("Tablas maestras...")
        years = _load_seasons(db, client)
        _load_circuits(db, client)
        _load_drivers(db, client)
        _load_constructors(db, client)
        _load_status(db, client)
        race_ids = _load_races(db, client)
        statuses = _StatusIds(db)
        _log("Resultados de carreras...")
        _load_results(db, client, race_ids, statuses)
        _log("Clasificación...")
        _load_qualifying(db, client, race_ids)
        _log("Sprints...")
        _load_sprints(db, client, race_ids, statuses)
        _log("Campeonatos...")
        _load_standings(db, client, years)

        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Violaciones de clave foránea: {violations[:5]}")
        db.commit()
        counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for (t,) in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()}
        db.execute("VACUUM")
    except BaseException:
        db.close()
        tmp_path.unlink(missing_ok=True)
        raise
    db.close()
    tmp_path.replace(db_path)  # solo reemplaza la BD vieja si la construcción terminó bien
    return counts
