import sqlite3
from pathlib import Path

# week3_capable/ root: world/db.py -> world -> boukensha -> python -> week3_capable
_ROOT_DIR = Path(__file__).resolve().parents[3]
SCHEMA_PATH = _ROOT_DIR / "schema.sql"
DEFAULT_DB_PATH = _ROOT_DIR / "data" / "world.db"


def connect(db_path=None):
    """Open a connection to the shared world.db, applying schema.sql
    (idempotent, CREATE TABLE IF NOT EXISTS) and the per-connection pragmas
    every connection needs — SQLite does not persist PRAGMA foreign_keys or
    journal_mode across connections, so both are set here every time, not
    just once at DB creation (plan §9)."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    _migrate(conn)
    return conn


def _migrate(conn):
    """CREATE TABLE IF NOT EXISTS above can't add a column to a table that
    already exists -- this covers additive column migrations for world.db
    files created before that column existed (goto_tool_plan §5's
    zone_name). No-op on a fresh DB, since schema.sql's own CREATE TABLE
    already includes the column there."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(locations)")}
    if "zone_name" not in cols:
        conn.execute("ALTER TABLE locations ADD COLUMN zone_name TEXT")
    # Not in schema.sql itself -- see schema.sql's comment on why the index
    # has to be created here, after the column is guaranteed to exist,
    # rather than in the script that runs before this migration does.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_zone_name ON locations(zone_name)")
    conn.commit()
