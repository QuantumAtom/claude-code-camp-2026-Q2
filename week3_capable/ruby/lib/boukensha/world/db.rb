require "sqlite3"
require "fileutils"

module Boukensha
  module World
    module Db
      # week3_capable/ root: __dir__ is .../week3_capable/ruby/lib/boukensha/world,
      # so 4 ups reaches week3_capable/ (world -> boukensha -> lib -> ruby).
      ROOT_DIR        = File.expand_path("../../../..", __dir__).freeze
      SCHEMA_PATH     = File.join(ROOT_DIR, "schema.sql").freeze
      DEFAULT_DB_PATH = File.join(ROOT_DIR, "data", "world.db").freeze

      # Opens a connection to the shared world.db, applying schema.sql
      # (idempotent, CREATE TABLE IF NOT EXISTS) and the per-connection
      # pragmas every connection needs -- SQLite does not persist PRAGMA
      # foreign_keys or journal_mode across connections, so both are set
      # here every time, not just once at DB creation (plan §9).
      def self.connect(db_path = nil)
        path = db_path || DEFAULT_DB_PATH
        FileUtils.mkdir_p(File.dirname(path))
        db = SQLite3::Database.new(path)
        db.results_as_hash = true
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA journal_mode = WAL")
        db.execute_batch(File.read(SCHEMA_PATH))
        migrate(db)
        db
      end

      # CREATE TABLE IF NOT EXISTS above can't add a column to a table that
      # already exists -- this covers additive column migrations for
      # world.db files created before that column existed (goto_tool_plan
      # §5's zone_name). No-op on a fresh DB, since schema.sql's own CREATE
      # TABLE already includes the column there.
      def self.migrate(db)
        cols = db.execute("PRAGMA table_info(locations)").map { |row| row["name"] }
        db.execute("ALTER TABLE locations ADD COLUMN zone_name TEXT") unless cols.include?("zone_name")
        # Not in schema.sql itself -- see schema.sql's comment on why the
        # index has to be created here, after the column is guaranteed to
        # exist, rather than in the script that runs before this migration
        # does.
        db.execute("CREATE INDEX IF NOT EXISTS idx_locations_zone_name ON locations(zone_name)")
      end
      private_class_method :migrate
    end
  end
end
