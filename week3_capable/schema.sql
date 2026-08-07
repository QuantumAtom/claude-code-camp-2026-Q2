-- Shared world-state schema, loaded by both boukensha/world/db.py and
-- boukensha/world/db.rb (neither language embeds its own copy — see
-- docs/plans/sqlite_plans/world_state_db_plan.md §2/§2a). Applied with
-- CREATE TABLE IF NOT EXISTS on every connection startup; whichever
-- language's agent runs first bootstraps the file, the other just opens it.
--
-- PRAGMA foreign_keys is per-connection in SQLite, so it must also be set at
-- connect time in each language's own connection helper (§9) — this
-- statement here only affects the connection that runs schema.sql itself.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    location_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,                 -- NULL until the placeholder is filled in
    area_type       TEXT,                 -- town | sewer | castle | dungeon | ...
    description     TEXT,
    visited         INTEGER NOT NULL DEFAULT 0 CHECK (visited IN (0,1)),
    -- Town/zone identity (docs/plans/sqlite_plans/goto_tool_plan.md §5) --
    -- deliberately NOT filled by matching this room's own name/description
    -- text (confirmed against real session logs: most in-town rooms, e.g.
    -- "The Bakery"/"The General Store", never mention the town's name at
    -- all). Instead flood-filled outward from a handful of rooms whose own
    -- text *does* name a town, through the exits graph -- see
    -- world/store.{py,rb}'s propagate_zone(). Fill-once, like an identity
    -- field, never overwritten once set.
    zone_name       TEXT,
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS exits (
    location_id         INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    direction            TEXT NOT NULL,   -- normalized: north|south|east|west|up|down|...
    leads_to_location_id INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, direction)
);

CREATE TABLE IF NOT EXISTS mobs (
    mob_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,   -- see §5 on why name is the identity key
    disposition          TEXT CHECK (disposition IN ('friendly','enemy','neutral') OR disposition IS NULL),
    hp                   INTEGER,
    level                INTEGER,
    is_dialogue_enabled  INTEGER CHECK (is_dialogue_enabled IN (0,1) OR is_dialogue_enabled IS NULL)
);

CREATE TABLE IF NOT EXISTS location_mobs (
    location_id   INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    mob_id        INTEGER NOT NULL REFERENCES mobs(mob_id) ON DELETE CASCADE,
    condition     TEXT CHECK (condition IN (
                      'excellent', 'scratches', 'small_wounds', 'quite_a_few_wounds',
                      'big_wounds', 'pretty_hurt', 'awful'
                  ) OR condition IS NULL),   -- latest qualitative reading; see §8's cold-start fallback
    last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (location_id, mob_id)
);

CREATE TABLE IF NOT EXISTS items (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    item_type  TEXT CHECK (item_type IN ('gold','armor','weapon','food','drink','misc') OR item_type IS NULL),
    level      INTEGER
);

CREATE TABLE IF NOT EXISTS location_items (
    location_id  INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    item_id      INTEGER NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    quantity     INTEGER,
    PRIMARY KEY (location_id, item_id)
);

CREATE TABLE IF NOT EXISTS weapons (
    weapon_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE   -- any damage source: a melee weapon ("short sword"), a
                                       -- bare-handed row ("fists"), a skill ("kick"), or a spell/
                                       -- magic item name — see §8
);

CREATE TABLE IF NOT EXISTS mob_weapon_stats (
    mob_id             INTEGER NOT NULL REFERENCES mobs(mob_id) ON DELETE CASCADE,
    weapon_id          INTEGER NOT NULL REFERENCES weapons(weapon_id) ON DELETE CASCADE,
    hits_landed_total  INTEGER NOT NULL DEFAULT 0,   -- running count across every fight with this pairing
    kills_total        INTEGER NOT NULL DEFAULT 0,   -- how many of those fights ended in a kill
    PRIMARY KEY (mob_id, weapon_id)
);

CREATE TABLE IF NOT EXISTS features (
    feature_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_type         TEXT NOT NULL,   -- door | chair | lever | ...
    is_locked             INTEGER CHECK (is_locked IN (0,1) OR is_locked IS NULL),
    is_lockpickable        INTEGER CHECK (is_lockpickable IN (0,1) OR is_lockpickable IS NULL),
    available_actions      TEXT           -- JSON array, e.g. '["open","sit","pull"]'
);

CREATE TABLE IF NOT EXISTS location_features (
    location_id  INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    feature_id   INTEGER NOT NULL REFERENCES features(feature_id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, feature_id)
);

CREATE INDEX IF NOT EXISTS idx_exits_leads_to ON exits(leads_to_location_id);
-- idx_locations_zone_name is NOT created here: on a pre-existing DB (from
-- before zone_name existed), this script's CREATE TABLE IF NOT EXISTS above
-- is a no-op against the already-existing locations table, so an index on
-- a column that doesn't exist yet there would fail this whole script
-- before db.{py,rb}'s migration ever gets a chance to add the column.
-- world/db.{py,rb}'s post-schema migration step creates this index instead,
-- unconditionally, after the column is guaranteed to exist either way.
