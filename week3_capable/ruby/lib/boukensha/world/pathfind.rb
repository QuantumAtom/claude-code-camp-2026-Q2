# goto_tool_plan: turns a free-text destination into a walkable route over
# the exits graph already recorded in world.db. Read-only against the DB --
# no writes happen here, and nothing here ever invents a path through
# unmapped territory (same "don't fabricate" principle as observer.rb's
# write-back). Callers (tools/mud.rb's go_to) are expected to have already
# confirmed current_location_id is not nil before calling into this module.

module Boukensha
  module World
    module Pathfind
      # Shortest sequence of directions from start to target, following
      # only known `exits` rows. BFS, not Dijkstra -- every hop costs
      # exactly one `move` call, so unweighted shortest-path-by-hop-count
      # is the right notion of "shortest" here. Directed, matching `exits`
      # itself (a `north` exit existing doesn't imply a `south` exit
      # back). Returns nil if no route is known yet.
      def self.bfs_path(db, start_location_id, target_location_id)
        return [] if start_location_id == target_location_id

        frontier = [start_location_id]
        visited = Set.new([start_location_id])
        came_from = {} # location_id -> [prev_location_id, direction]

        until frontier.empty?
          next_frontier = []
          frontier.each do |loc_id|
            rows = db.execute(
              "SELECT direction, leads_to_location_id FROM exits WHERE location_id = ?",
              [loc_id]
            )
            rows.each do |row|
              dest_id = row["leads_to_location_id"]
              next if visited.include?(dest_id)

              visited << dest_id
              came_from[dest_id] = [loc_id, row["direction"]]
              return reconstruct(came_from, target_location_id) if dest_id == target_location_id

              next_frontier << dest_id
            end
          end
          frontier = next_frontier
        end

        nil
      end

      def self.reconstruct(came_from, target_location_id)
        path = []
        node = target_location_id
        while came_from.key?(node)
          prev, direction = came_from[node]
          path << direction
          node = prev
        end
        path.reverse
      end
      private_class_method :reconstruct

      def self.distance(db, start_location_id, target_location_id)
        path = bfs_path(db, start_location_id, target_location_id)
        path.nil? ? nil : path.length
      end
      private_class_method :distance

      # Turns free-text destination into a target location_id
      # (goto_tool_plan §4/§5). Returns [target_location_id, note]:
      # - target is nil on outright failure; note explains why.
      # - target is set and note is nil on an exact, unambiguous match.
      # - target is set and note is non-nil on a town-anchor fallback (§5)
      #   -- the note is an informational heads-up for the caller to
      #   surface, not a failure.
      def self.resolve_destination(db, current_location_id, destination_text)
        destination_text = (destination_text || "").strip
        return [nil, "no destination given"] if destination_text.empty?

        lowered = destination_text.downcase
        if lowered.include?(" in ")
          idx = lowered.index(" in ")
          place = destination_text[0...idx].strip
          town = destination_text[(idx + 4)..].strip
        else
          place = destination_text
          town = nil
        end

        rows = db.execute(
          "SELECT location_id, name, zone_name FROM locations WHERE name LIKE ? ESCAPE '\\'",
          ["%#{escape_like(place)}%"]
        )

        if town && !rows.empty?
          town_rows = rows.select { |r| r["zone_name"] && r["zone_name"].downcase == town.downcase }
          rows = town_rows unless town_rows.empty?
        end

        return [rows.first["location_id"], nil] if rows.length == 1

        return disambiguate(db, current_location_id, town, destination_text, rows) if rows.length > 1

        # Zero direct matches -- town-level fallback (§5): treat the town
        # token (or the whole query, if no " in " was given) as a possible
        # zone_name and route to the nearest known room already tagged
        # with it.
        zone_query = town || destination_text
        resolve_town_anchor(db, current_location_id, zone_query, destination_text)
      end

      # §4 step 5: room names aren't unique on purpose (sewers/mazes).
      # Prefer the reachable match nearest the current position; a genuine
      # tie is handed back to the caller rather than guessed at.
      #
      # Confirmed live: separate play sessions each text-match a fresh
      # start into their own location row (world_state_db_plan §5's
      # accepted duplicate-row tradeoff), which can leave every
      # name-matched row stranded on an unreachable island even though the
      # town itself is well-mapped. If a town was given and none of the
      # exact matches are reachable, fall back to routing toward the town
      # anchor (§5) instead of failing outright -- same behavior the
      # zero-match case already gets.
      def self.disambiguate(db, current_location_id, town, destination_text, rows)
        scored = rows.map { |r| [r["location_id"], r["name"], distance(db, current_location_id, r["location_id"])] }
        reachable = scored.reject { |s| s[2].nil? }
        if reachable.empty?
          return resolve_town_anchor(db, current_location_id, town, destination_text) if town

          return [nil, "'#{destination_text}' matches #{rows.length} known locations, none reachable by a discovered route"]
        end

        best_dist = reachable.map { |s| s[2] }.min
        tied = reachable.select { |s| s[2] == best_dist }
        return [tied.first[0], nil] if tied.length == 1

        names = tied.map { |t| "\"#{t[1]}\" (location_id=#{t[0]})" }.join(", ")
        [nil, "'#{destination_text}' is ambiguous -- #{tied.length} equally-close matches: #{names}. Pick one and retry with a more specific name."]
      end
      private_class_method :disambiguate

      def self.resolve_town_anchor(db, current_location_id, zone_query, original_text)
        rows = db.execute(
          "SELECT location_id, name FROM locations WHERE zone_name = ? COLLATE NOCASE",
          [zone_query]
        )
        if rows.empty?
          return [nil, "no known route toward '#{zone_query}' -- nothing there has been discovered yet"]
        end

        scored = rows.map { |r| [r["location_id"], r["name"], distance(db, current_location_id, r["location_id"])] }
        reachable = scored.reject { |s| s[2].nil? }
        if reachable.empty?
          return [nil, "'#{zone_query}' is known but no discovered route reaches any of it yet"]
        end

        anchor_id, anchor_name, = reachable.min_by { |s| s[2] }
        [anchor_id,
         "nearest known point in \"#{zone_query}\" to \"#{original_text}\" is \"#{anchor_name}\"; " \
         "exact location isn't mapped yet -- explore from here"]
      end
      private_class_method :resolve_town_anchor

      def self.escape_like(text)
        text.gsub("\\", "\\\\\\\\").gsub("%", "\\%").gsub("_", "\\_")
      end
      private_class_method :escape_like

      # needs_management_plan §5: nearest reachable location known to
      # carry an item of item_type (BFS reachability, goto_tool_plan-style).
      # Returns [location_id, location_name, item_name, hops], or nil if
      # nothing's been discovered yet -- never fabricates a source.
      def self.find_nearest_supply(db, current_location_id, item_type)
        rows = db.execute(
          "SELECT li.location_id AS location_id, l.name AS location_name, i.name AS item_name " \
          "FROM location_items li " \
          "JOIN items i ON i.item_id = li.item_id " \
          "JOIN locations l ON l.location_id = li.location_id " \
          "WHERE i.item_type = ?",
          [item_type]
        )
        return nil if rows.empty?

        best = nil
        rows.each do |row|
          path = bfs_path(db, current_location_id, row["location_id"])
          next if path.nil?

          best = [row["location_id"], row["location_name"], row["item_name"], path.length] if best.nil? || path.length < best[3]
        end
        best
      end

      # needs_management_plan §9a follow-up, confirmed live: when
      # location_id itself isn't BFS-reachable, another location row can
      # still exist for what's physically the same room --
      # world_state_db_plan §5's accepted duplicate-row tradeoff (separate
      # sessions each text-match a fresh start into their own row, and an
      # edge recorded from one session can point at a different duplicate
      # than the one a caller remembers). Returns [other_location_id, path]
      # for the nearest *other* row sharing the same name that IS
      # reachable, or nil.
      def self.find_reachable_duplicate(db, current_location_id, location_id)
        row = db.execute("SELECT name FROM locations WHERE location_id = ?", [location_id]).first
        return nil if row.nil? || row["name"].nil?

        candidates = db.execute(
          "SELECT location_id FROM locations WHERE name = ? AND location_id != ?",
          [row["name"], location_id]
        )
        best = nil
        candidates.each do |cand|
          path = bfs_path(db, current_location_id, cand["location_id"])
          next if path.nil?

          best = [cand["location_id"], path] if best.nil? || path.length < best[1].length
        end
        best
      end
    end
  end
end
