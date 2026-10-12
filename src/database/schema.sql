-- Relational schema for Formula 1 (1950-present). Data source: Jolpica-F1 (Ergast-compatible API).
-- Single source of truth: it is executed to create the DB and injected into the agent's prompt,
-- so the comments describe the meaning of the columns.

PRAGMA foreign_keys = ON;

-- Seasons (one championship per year)
CREATE TABLE seasons (
    year INTEGER PRIMARY KEY,
    url  TEXT
);

-- Circuits
CREATE TABLE circuits (
    circuit_id TEXT PRIMARY KEY,          -- stable slug, e.g. 'monza'
    name       TEXT NOT NULL,             -- ej. 'Autodromo Nazionale di Monza'
    locality   TEXT,                      -- city
    country    TEXT,
    lat        REAL,
    lng        REAL,
    url        TEXT
);

-- Drivers (identity and personal data; independent of the season)
CREATE TABLE drivers (
    driver_id        TEXT PRIMARY KEY,    -- stable slug, e.g. 'max_verstappen'
    code             TEXT,                -- 3-letter code (modern drivers only), e.g. 'VER'
    permanent_number INTEGER,             -- permanent number (modern era only)
    forename         TEXT NOT NULL,
    surname          TEXT NOT NULL,
    dob              TEXT,                -- date of birth, ISO (YYYY-MM-DD)
    nationality      TEXT,
    url              TEXT
);

-- Constructors / teams
CREATE TABLE constructors (
    constructor_id TEXT PRIMARY KEY,      -- slug, e.g. 'ferrari'
    name           TEXT NOT NULL,
    nationality    TEXT,
    url            TEXT
);

-- How a driver finished a race ('Finished', '+1 Lap', 'Engine', 'Accident', ...)
CREATE TABLE status (
    status_id INTEGER PRIMARY KEY,
    status    TEXT NOT NULL UNIQUE
);

-- Grands Prix (one row per race)
CREATE TABLE races (
    race_id    INTEGER PRIMARY KEY,
    year       INTEGER NOT NULL REFERENCES seasons(year),
    round      INTEGER NOT NULL,          -- race number within the season
    circuit_id TEXT    NOT NULL REFERENCES circuits(circuit_id),
    name       TEXT    NOT NULL,          -- e.g. 'Italian Grand Prix'
    date       TEXT,                      -- ISO YYYY-MM-DD
    time       TEXT,                      -- UTC start time when available
    url        TEXT,
    UNIQUE (year, round)
);

-- Result of each driver in each race (central fact table)
CREATE TABLE results (
    result_id          INTEGER PRIMARY KEY,
    race_id            INTEGER NOT NULL REFERENCES races(race_id),
    driver_id          TEXT    NOT NULL REFERENCES drivers(driver_id),
    constructor_id     TEXT    NOT NULL REFERENCES constructors(constructor_id),
    car_number         INTEGER,
    grid               INTEGER,           -- starting grid position (0 = started from the pit lane)
    position           INTEGER,           -- final position; NULL if not classified (retirement, disqualification)
    position_text      TEXT,              -- '1', '2', ..., 'R' (retired), 'D' (disqualified), 'W' (withdrawn), etc.
    position_order     INTEGER NOT NULL,  -- overall finishing order, including unclassified drivers
    points             REAL NOT NULL,
    laps               INTEGER,           -- laps completed
    status_id          INTEGER NOT NULL REFERENCES status(status_id),
    time_text          TEXT,              -- total time or gap, e.g. '1:32:07.986' / '+5.3'
    milliseconds       INTEGER,           -- total time (winner) / gap in ms
    fastest_lap_rank   INTEGER,           -- fastest-lap rank in that race (1 = fastest)
    fastest_lap_number INTEGER,
    fastest_lap_time   TEXT,
    UNIQUE (race_id, driver_id, constructor_id, car_number)  -- a driver can appear twice (shared cars, 1950s)
);

-- Qualifying, available from 1994
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

-- Sprint race results (from 2021)
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

-- Drivers' championship: FINAL position of each season
CREATE TABLE driver_standings (
    year      INTEGER NOT NULL REFERENCES seasons(year),
    driver_id TEXT    NOT NULL REFERENCES drivers(driver_id),
    position  INTEGER,                    -- 1 = world champion of that year
    points    REAL    NOT NULL,
    wins      INTEGER NOT NULL,
    PRIMARY KEY (year, driver_id)
);

-- Constructors' championship: FINAL position of each season (from 1958)
CREATE TABLE constructor_standings (
    year           INTEGER NOT NULL REFERENCES seasons(year),
    constructor_id TEXT    NOT NULL REFERENCES constructors(constructor_id),
    position       INTEGER,               -- 1 = constructors' champion
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

-- Convenience view for the agent: one result with all names already resolved
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
