require "json"
require "set"
require "time"

module Boukensha
  module World
    module Store
      def self.now_iso
        Time.now.iso8601
      end

      # ---------- locations (plan §5: identity is graph-position-first, ----
      # ---------- name-matching-second -- this module only does the SQL; --
      # ---------- the graph-pointer logic lives in world.rb) ---------------

      # Two call shapes, per §5:
      # - name=nil (a fresh placeholder for an unscanned exit): always
      #   inserts a new row -- a placeholder is definitionally new, no
      #   lookup needed.
      # - name given (the text-matching fallback path): looks for an exact
      #   (name, description) match first, since room names alone aren't
      #   unique (§5) -- only a full match counts as "the same room
      #   already known".
      def self.get_or_create_location(db, name: nil, area_type: nil, description: nil, visited: false)
        if name
          row = db.execute(
            "SELECT location_id FROM locations WHERE name = ? AND description IS ?",
            [name, description]
          ).first
          return row["location_id"] if row
        end
        db.execute(
          "INSERT INTO locations (name, area_type, description, visited) VALUES (?, ?, ?, ?)",
          [name, area_type, description, visited ? 1 : 0]
        )
        db.last_insert_row_id
      end

      # Update name/description/area_type/visited/last_seen_at, only
      # overwriting fields explicitly passed as non-nil -- this is how a
      # placeholder (name=NULL) gets filled in on first real visit without
      # clobbering fields nothing new was observed for.
      def self.touch_location(db, location_id, **updates)
        # SQLite3's Ruby gem, unlike Python's stdlib sqlite3, can't bind a
        # raw true/false (Ruby TrueClass/FalseClass) -- only the "visited"
        # column is ever boolean-shaped here, so normalize it to 0/1 like
        # get_or_create_location already does.
        fields = updates.compact
        fields[:visited] = fields[:visited] ? 1 : 0 if fields.key?(:visited)
        fields[:last_seen_at] = now_iso
        set_clause = fields.keys.map { |k| "#{k} = ?" }.join(", ")
        db.execute(
          "UPDATE locations SET #{set_clause} WHERE location_id = ?",
          [*fields.values, location_id]
        )
      end

      def self.get_or_create_exit(db, location_id, direction, leads_to_location_id)
        db.execute(
          "INSERT OR IGNORE INTO exits (location_id, direction, leads_to_location_id) VALUES (?, ?, ?)",
          [location_id, direction, leads_to_location_id]
        )
      end

      # The graph-pointer lookup §5 relies on: known by position, no text
      # matching needed, if this returns non-nil.
      def self.get_exit(db, location_id, direction)
        row = db.execute(
          "SELECT leads_to_location_id FROM exits WHERE location_id = ? AND direction = ?",
          [location_id, direction]
        ).first
        row && row["leads_to_location_id"]
      end

      # ---------- mobs / items -- identity by UNIQUE name (§3), update -----
      # ---------- rules per §7: fields describing the mob/item's *identity* -
      # ---------- are fill-once; fields describing *transient state* -------
      # ---------- overwrite with the latest observation. --------------------

      def self.get_or_create_mob(db, name, disposition: nil, hp: nil, level: nil, is_dialogue_enabled: nil)
        row = db.execute("SELECT mob_id FROM mobs WHERE name = ?", [name]).first
        if row
          mob_id = row["mob_id"]
          update_mob(db, mob_id, disposition: disposition, hp: hp, level: level,
                                  is_dialogue_enabled: is_dialogue_enabled)
          return mob_id
        end
        db.execute(
          "INSERT INTO mobs (name, disposition, hp, level, is_dialogue_enabled) VALUES (?, ?, ?, ?, ?)",
          [name, disposition, hp, level, is_dialogue_enabled]
        )
        db.last_insert_row_id
      end

      def self.update_mob(db, mob_id, disposition:, hp:, level:, is_dialogue_enabled:)
        sets, vals = [], []
        unless disposition.nil?                          # transient -> always overwrite
          sets << "disposition = ?"; vals << disposition
        end
        unless hp.nil?                                    # only a real number overwrites (§7 --
          sets << "hp = ?"; vals << hp                     # otherwise stays NULL; nothing here fabricates one)
        end
        unless level.nil?                                 # identity -> fill-once
          sets << "level = COALESCE(level, ?)"; vals << level
        end
        unless is_dialogue_enabled.nil?                   # identity -> fill-once
          sets << "is_dialogue_enabled = COALESCE(is_dialogue_enabled, ?)"; vals << is_dialogue_enabled
        end
        return if sets.empty?
        vals << mob_id
        db.execute("UPDATE mobs SET #{sets.join(', ')} WHERE mob_id = ?", vals)
      end

      # Plan §6 lists this as link_mob(conn, location_id, mob_id) -> None;
      # condition: is an addition beyond that minimal signature, since §3's
      # location_mobs.condition ("latest qualitative reading") has to be
      # set somewhere, and this junction row is where it lives.
      def self.link_mob(db, location_id, mob_id, condition: nil)
        db.execute(
          "INSERT INTO location_mobs (location_id, mob_id, condition, last_seen_at) " \
          "VALUES (?, ?, ?, ?) " \
          "ON CONFLICT(location_id, mob_id) DO UPDATE SET " \
          "condition = COALESCE(excluded.condition, location_mobs.condition), " \
          "last_seen_at = excluded.last_seen_at",
          [location_id, mob_id, condition, now_iso]
        )
      end

      def self.get_or_create_item(db, name, item_type: nil, level: nil)
        row = db.execute("SELECT item_id FROM items WHERE name = ?", [name]).first
        if row
          item_id = row["item_id"]
          sets, vals = [], []
          sets << "item_type = COALESCE(item_type, ?)" and vals << item_type unless item_type.nil?
          sets << "level = COALESCE(level, ?)" and vals << level unless level.nil?
          unless sets.empty?
            vals << item_id
            db.execute("UPDATE items SET #{sets.join(', ')} WHERE item_id = ?", vals)
          end
          return item_id
        end
        db.execute(
          "INSERT INTO items (name, item_type, level) VALUES (?, ?, ?)",
          [name, item_type, level]
        )
        db.last_insert_row_id
      end

      # quantity overwrites with the latest observed count (§7 -- the one
      # junction-table field that's genuinely mutable, per the spec's own
      # gold-amount example).
      def self.link_item(db, location_id, item_id, quantity: nil)
        db.execute(
          "INSERT INTO location_items (location_id, item_id, quantity) VALUES (?, ?, ?) " \
          "ON CONFLICT(location_id, item_id) DO UPDATE SET quantity = excluded.quantity",
          [location_id, item_id, quantity]
        )
      end

      # ---------- features (doors, etc.) -- schema has no UNIQUE key on ----
      # ---------- feature_type (§3), so unlike mobs/items/weapons there's --
      # ---------- no name-identity lookup possible here -- every call ------
      # ---------- inserts a new row, matching the schema as specified. -----

      def self.get_or_create_feature(db, feature_type, is_locked: nil, is_lockpickable: nil, available_actions: nil)
        actions_json = available_actions.nil? ? nil : JSON.generate(available_actions)
        db.execute(
          "INSERT INTO features (feature_type, is_locked, is_lockpickable, available_actions) VALUES (?, ?, ?, ?)",
          [feature_type, is_locked, is_lockpickable, actions_json]
        )
        db.last_insert_row_id
      end

      def self.link_feature(db, location_id, feature_id)
        db.execute(
          "INSERT OR IGNORE INTO location_features (location_id, feature_id) VALUES (?, ?)",
          [location_id, feature_id]
        )
      end

      # ---------- weapons / pseudo-weapons + combat estimation (§8) --------
      # ---------- "anything that can damage a mob is a weapon or pseudo- ---
      # ---------- weapon" (decision #8) -- a melee weapon, "fists", a ------
      # ---------- skill name, or (once grounded) a spell/item name are -----
      # ---------- all just rows in this one table, identified by name ------
      # ---------- like mobs/items. ------------------------------------------

      def self.get_or_create_weapon(db, name)
        row = db.execute("SELECT weapon_id FROM weapons WHERE name = ?", [name]).first
        return row["weapon_id"] if row
        db.execute("INSERT INTO weapons (name) VALUES (?)", [name])
        db.last_insert_row_id
      end

      def self.record_attack(db, mob_id, weapon_id, landed:)
        return unless landed
        db.execute(
          "INSERT INTO mob_weapon_stats (mob_id, weapon_id, hits_landed_total, kills_total) " \
          "VALUES (?, ?, 1, 0) " \
          "ON CONFLICT(mob_id, weapon_id) DO UPDATE SET hits_landed_total = hits_landed_total + 1",
          [mob_id, weapon_id]
        )
      end

      def self.record_kill(db, mob_id, weapon_id)
        db.execute(
          "INSERT INTO mob_weapon_stats (mob_id, weapon_id, hits_landed_total, kills_total) " \
          "VALUES (?, ?, 0, 1) " \
          "ON CONFLICT(mob_id, weapon_id) DO UPDATE SET kills_total = kills_total + 1",
          [mob_id, weapon_id]
        )
      end

      # Decision #6: don't trust the numeric estimate until kills_total
      # clears this threshold for the exact (mob, weapon) pairing -- below
      # it, callers should fall back to location_mobs.condition's
      # qualitative reading instead.
      KILLS_TOTAL_TRUST_THRESHOLD = 3

      # Returns estimated fraction of health remaining (0.0-1.0), or nil if
      # there isn't enough data yet (§8) -- callers fall back to §3's
      # qualitative location_mobs.condition in that case.
      def self.estimate_condition(db, mob_id, weapon_id, hits_landed_this_fight)
        row = db.execute(
          "SELECT hits_landed_total, kills_total FROM mob_weapon_stats WHERE mob_id = ? AND weapon_id = ?",
          [mob_id, weapon_id]
        ).first
        return nil if row.nil? || row["kills_total"] < KILLS_TOTAL_TRUST_THRESHOLD

        avg_hits_to_kill = row["hits_landed_total"].to_f / row["kills_total"]
        return nil if avg_hits_to_kill <= 0

        percent_remaining = 1 - (hits_landed_this_fight.to_f / avg_hits_to_kill)
        [[percent_remaining, 0.0].max, 1.0].min
      end

      # ---------- zone/town identity (goto_tool_plan §5) ---------------------
      # zone_name is a derived enrichment, not text-matched per room -- it's
      # flood-filled outward from a handful of "seed" rooms whose own text
      # does explicitly name a town (Parser.detect_seed_zone), through the
      # exits graph. Treated as identity-like: fill-once, never overwritten
      # -- same rule as mobs.level (§7). A room's town doesn't change out
      # from under it.

      # Town cores are compact (confirmed against real Midgaard room
      # samples -- well under a dozen hops end to end); this caps a
      # flood-fill from leaking deep into an unrelated connected
      # maze/sewer that has no distinguishing seed of its own to stop at.
      ZONE_PROPAGATION_MAX_HOPS = 12

      # Fill-once: only writes if zone_name is currently unset.
      def self.fill_zone_name(db, location_id, zone_name)
        db.execute(
          "UPDATE locations SET zone_name = ? WHERE location_id = ? AND zone_name IS NULL",
          [zone_name, location_id]
        )
      end

      def self.get_zone_name(db, location_id)
        row = db.execute("SELECT zone_name FROM locations WHERE location_id = ?", [location_id]).first
        row && row["zone_name"]
      end

      # Bounded flood-fill (goto_tool_plan §5): tags every location
      # reachable from start_location_id within max_hops with zone_name,
      # stopping expansion through any room that already carries a
      # *different* zone_name (never crosses into another town's
      # already-claimed territory). Exits are treated as undirected for
      # this purpose -- physical adjacency doesn't care which direction the
      # game lets you walk it.
      def self.propagate_zone(db, start_location_id, zone_name, max_hops: ZONE_PROPAGATION_MAX_HOPS)
        fill_zone_name(db, start_location_id, zone_name)
        frontier = [start_location_id]
        visited = Set.new([start_location_id])
        max_hops.times do
          break if frontier.empty?

          next_frontier = []
          frontier.each do |loc_id|
            neighbors = db.execute(
              "SELECT leads_to_location_id AS nid FROM exits WHERE location_id = ? " \
              "UNION " \
              "SELECT location_id AS nid FROM exits WHERE leads_to_location_id = ?",
              [loc_id, loc_id]
            )
            neighbors.each do |row|
              nid = row["nid"]
              next if visited.include?(nid)

              visited << nid
              existing = get_zone_name(db, nid)
              if existing.nil?
                fill_zone_name(db, nid, zone_name)
                next_frontier << nid
              elsif existing == zone_name
                next_frontier << nid
              end
              # else: a different zone already claims this room -- stop here
            end
          end
          frontier = next_frontier
        end
      end
    end
  end
end
