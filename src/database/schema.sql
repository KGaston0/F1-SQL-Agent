-- Esquema relacional de Formula 1 (1950-presente). Fuente de datos: Jolpica-F1 (API compatible con Ergast).
-- Este archivo es la unica fuente de verdad: se ejecuta para crear la BD y se inyecta en el prompt del agente,
-- por eso los comentarios describen el significado de las columnas.

PRAGMA foreign_keys = ON;

-- Temporadas (un campeonato por anio)
CREATE TABLE seasons (
    year INTEGER PRIMARY KEY,
    url  TEXT
);

-- Circuitos / pistas
CREATE TABLE circuits (
    circuit_id TEXT PRIMARY KEY,          -- slug estable, ej. 'monza'
    name       TEXT NOT NULL,             -- ej. 'Autodromo Nazionale di Monza'
    locality   TEXT,                      -- ciudad
    country    TEXT,
    lat        REAL,
    lng        REAL,
    url        TEXT
);

-- Pilotos (identidad y datos personales; no dependen de la temporada)
CREATE TABLE drivers (
    driver_id        TEXT PRIMARY KEY,    -- slug estable, ej. 'max_verstappen'
    code             TEXT,                -- codigo de 3 letras (solo pilotos modernos), ej. 'VER'
    permanent_number INTEGER,             -- numero permanente (solo era moderna)
    forename         TEXT NOT NULL,
    surname          TEXT NOT NULL,
    dob              TEXT,                -- fecha de nacimiento ISO (YYYY-MM-DD)
    nationality      TEXT,
    url              TEXT
);

-- Constructores / equipos
CREATE TABLE constructors (
    constructor_id TEXT PRIMARY KEY,      -- slug, ej. 'ferrari'
    name           TEXT NOT NULL,
    nationality    TEXT,
    url            TEXT
);

-- Estados de finalizacion de una carrera ('Finished', '+1 Lap', 'Engine', 'Accident', ...)
CREATE TABLE status (
    status_id INTEGER PRIMARY KEY,
    status    TEXT NOT NULL UNIQUE
);

-- Grandes Premios (una fila por carrera)
CREATE TABLE races (
    race_id    INTEGER PRIMARY KEY,
    year       INTEGER NOT NULL REFERENCES seasons(year),
    round      INTEGER NOT NULL,          -- nro de fecha dentro de la temporada
    circuit_id TEXT    NOT NULL REFERENCES circuits(circuit_id),
    name       TEXT    NOT NULL,          -- ej. 'Italian Grand Prix'
    date       TEXT,                      -- ISO YYYY-MM-DD
    time       TEXT,                      -- hora UTC de largada si esta disponible
    url        TEXT,
    UNIQUE (year, round)
);

-- Resultado de cada piloto en cada carrera (tabla central de hechos)
CREATE TABLE results (
    result_id          INTEGER PRIMARY KEY,
    race_id            INTEGER NOT NULL REFERENCES races(race_id),
    driver_id          TEXT    NOT NULL REFERENCES drivers(driver_id),
    constructor_id     TEXT    NOT NULL REFERENCES constructors(constructor_id),
    car_number         INTEGER,
    grid               INTEGER,           -- posicion de largada (0 = largo desde boxes)
    position           INTEGER,           -- posicion final; NULL si no clasifico (retiro, descalificacion)
    position_text      TEXT,              -- '1', '2', ..., 'R' (retiro), 'D' (descalificado), 'W' (retirado), etc.
    position_order     INTEGER NOT NULL,  -- orden total de llegada, incluidos los no clasificados
    points             REAL NOT NULL,
    laps               INTEGER,           -- vueltas completadas
    status_id          INTEGER NOT NULL REFERENCES status(status_id),
    time_text          TEXT,              -- tiempo total o diferencia, ej. '1:32:07.986' / '+5.3'
    milliseconds       INTEGER,           -- tiempo total del ganador / diferencia en ms
    fastest_lap_rank   INTEGER,           -- ranking de vuelta rapida en esa carrera (1 = la mas rapida)
    fastest_lap_number INTEGER,
    fastest_lap_time   TEXT,
    UNIQUE (race_id, driver_id, constructor_id, car_number)  -- un piloto puede figurar 2 veces (autos compartidos, anos 50)
);

-- Clasificacion (qualy), desde 1994
CREATE TABLE qualifying (
    qualify_id     INTEGER PRIMARY KEY,
    race_id        INTEGER NOT NULL REFERENCES races(race_id),
    driver_id      TEXT    NOT NULL REFERENCES drivers(driver_id),
    constructor_id TEXT    NOT NULL REFERENCES constructors(constructor_id),
    car_number     INTEGER,
    position       INTEGER,
    q1             TEXT,
    q2             TEXT,
    q3             TEXT,
    UNIQUE (race_id, driver_id)
);

-- Resultados de carreras sprint (desde 2021)
CREATE TABLE sprint_results (
    sprint_id      INTEGER PRIMARY KEY,
    race_id        INTEGER NOT NULL REFERENCES races(race_id),
    driver_id      TEXT    NOT NULL REFERENCES drivers(driver_id),
    constructor_id TEXT    NOT NULL REFERENCES constructors(constructor_id),
    car_number     INTEGER,
    grid           INTEGER,
    position       INTEGER,
    position_text  TEXT,
    points         REAL NOT NULL,
    laps           INTEGER,
    status_id      INTEGER NOT NULL REFERENCES status(status_id),
    time_text      TEXT,
    UNIQUE (race_id, driver_id)
);

-- Campeonato de pilotos: posicion FINAL de cada temporada
CREATE TABLE driver_standings (
    year      INTEGER NOT NULL REFERENCES seasons(year),
    driver_id TEXT    NOT NULL REFERENCES drivers(driver_id),
    position  INTEGER,                    -- 1 = campeon del mundo de ese anio
    points    REAL    NOT NULL,
    wins      INTEGER NOT NULL,
    PRIMARY KEY (year, driver_id)
);

-- Campeonato de constructores: posicion FINAL de cada temporada (desde 1958)
CREATE TABLE constructor_standings (
    year           INTEGER NOT NULL REFERENCES seasons(year),
    constructor_id TEXT    NOT NULL REFERENCES constructors(constructor_id),
    position       INTEGER,               -- 1 = campeon de constructores
    points         REAL    NOT NULL,
    wins           INTEGER NOT NULL,
    PRIMARY KEY (year, constructor_id)
);

CREATE INDEX idx_races_year        ON races(year);
CREATE INDEX idx_races_circuit     ON races(circuit_id);
CREATE INDEX idx_results_race      ON results(race_id);
CREATE INDEX idx_results_driver    ON results(driver_id);
CREATE INDEX idx_results_ctor      ON results(constructor_id);
CREATE INDEX idx_qualifying_driver ON qualifying(driver_id);

-- Vista de conveniencia para el agente: un resultado con todos los nombres ya resueltos
CREATE VIEW v_results AS
SELECT r.result_id, ra.year, ra.round, ra.name AS race_name, ra.date, c.name AS circuit, c.country,
       d.driver_id, d.forename || ' ' || d.surname AS driver, d.nationality AS driver_nationality,
       k.constructor_id, k.name AS constructor,
       r.grid, r.position, r.position_text, r.position_order, r.points, r.laps,
       s.status, r.time_text, r.fastest_lap_rank
FROM results r
JOIN races ra        ON ra.race_id = r.race_id
JOIN circuits c      ON c.circuit_id = ra.circuit_id
JOIN drivers d       ON d.driver_id = r.driver_id
JOIN constructors k  ON k.constructor_id = r.constructor_id
JOIN status s        ON s.status_id = r.status_id;
