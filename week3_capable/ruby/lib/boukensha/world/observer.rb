require_relative "db"
require_relative "store"
require_relative "parser"

module Boukensha
  module World
    # Transient session state (§5, §8) -- not schema, reconstructable from
    # the exits graph / next wield+attack, so it lives here as plain module
    # state rather than a DB table.
    @db = nil
    @current_location_id = nil
    @current_weapon_id = nil
    @current_fight_mob_id = nil
    @current_fight_hits_landed = 0

    # "too relaxed to do that" confirmed live: resting blocks movement with
    # this phrase, not the "cannot go that way" text -- without this
    # alternation go_to/return_to_start silently believed a resting-refused
    # move had succeeded (needs_management_plan §9a follow-up testing
    # caught this).
    MOVE_FAILURE_RE = /alas, you (?:cannot|can'?t) go that way|nothing (?:that way|to that direction)|too relaxed to do that/i.freeze

    def self.connection
      @db ||= Db.connect
    end

    # ---------- public accessors (goto_tool_plan §6/§8: pathfind.rb and ------
    # ---------- the go_to tool need read access to the same pointer/-----------
    # ---------- connection this module already tracks internally) -----------

    def self.current_location_id
      @current_location_id
    end

    # True if a `move` result indicates the hop didn't actually happen (bad
    # direction / blocked) or the pointer just went stale (death/recall
    # mid-walk) -- reuses the exact same grounded checks observe_move
    # already applies for write-back, so go_to's hop-by-hop loop
    # (goto_tool_plan §6) stops on the same signals the DB itself trusts.
    def self.move_failed?(result_text)
      return true if Parser.stale_pointer_signal?(result_text)

      MOVE_FAILURE_RE.match?(Parser.strip_ansi(result_text))
    end

    # Clears in-memory pointer/fight state -- called on (re)connect, since
    # a fresh session can't trust whatever the previous connection's
    # pointer was.
    def self.reset_session
      @current_location_id = nil
      @current_weapon_id = nil
      @current_fight_mob_id = nil
      @current_fight_hits_landed = 0
    end

    # The Registry#dispatch hook point (plan §6a). Pattern-matches on tool
    # name; no-op for tools it doesn't recognize. Never raises -- a parsing
    # bug here is a missed observation, not a reason to break the agent's
    # turn (same philosophy as agent.rb's own tool-error handling).
    def self.observe(name, args, result)
      args = (args || {}).transform_keys(&:to_sym)
      text = result.nil? ? "" : result.to_s

      case name.to_s
      when "mud_connect"
        reset_session
      when "look"
        # Deliberately not gated on args[:target] being empty: the tool's
        # own docstring tells the model not to pass target: "room"/"here",
        # but it doesn't always comply (confirmed live in the Python port --
        # the model called look(target: "room", ...) and look(target:
        # "here", ...) in one run, which would've silently skipped room
        # observation entirely if gated on args). Parser.parse_room already
        # returns nil for anything that isn't shaped like a room response
        # (no exits line) -- that's the correct discriminator, not the
        # tool's own arguments.
        observe_room(text)
      when "check"
        observe_exits(text) if args[:kind] == "exits"
      when "move"
        observe_move(args, text)
      when "get_item"
        observe_pickup(args, text)
      when "equip_item"
        observe_wield(text) if args[:action] == "wield"
      when "attack", "skill_strike"
        observe_combat(name.to_s, args, text)
      when "consider"
        observe_consider(args, text)
      when "shop"
        observe_shop(text) if args[:action] == "list"
      when "cast_spell"
        observe_spell_identity_only(args)
      when "use_magic_item"
        observe_magic_item_identity_only(args)
      end
    rescue StandardError => e
      warn "warning: World.observe(#{name.inspect}) failed: #{e.message}"
    end

    # ---------- rooms / exits / movement (§5) --------------------------------

    # goto_tool_plan §5: if this room's own text names a known town and the
    # room isn't already zoned, tag it and flood-fill that zone outward
    # through the exits graph. No-ops (cheaply) once a room already has a
    # zone_name, whether from a prior seed or a prior propagation.
    def self.apply_zone(db, location_id, name, description)
      return unless Store.get_zone_name(db, location_id).nil?

      zone = Parser.detect_seed_zone(name, description)
      Store.propagate_zone(db, location_id, zone) if zone
    end
    private_class_method :apply_zone

    # Shared by observe_room (letters only) and observe_exits (full names)
    # -- for each direction not already scanned from this location, create
    # a placeholder destination and the exits row (§5).
    def self.link_room_exits(db, location_id, exit_directions, destination_names = {})
      exit_directions.each do |direction|
        next unless Store.get_exit(db, location_id, direction).nil?

        dest_name = destination_names[direction]
        dest_id = Store.get_or_create_location(db, name: dest_name, visited: false)
        Store.get_or_create_exit(db, location_id, direction, dest_id)
      end
    end
    private_class_method :link_room_exits

    def self.observe_room(text)
      parsed = Parser.parse_room(text)
      return if parsed.nil?

      db = connection

      if @current_location_id.nil?
        # Text-matching fallback (§5): session start, or pointer went stale.
        @current_location_id = Store.get_or_create_location(
          db, name: parsed.name, description: parsed.description, visited: true
        )
      else
        Store.touch_location(db, @current_location_id,
                              name: parsed.name, description: parsed.description, visited: true)
      end

      link_room_exits(db, @current_location_id, parsed.exit_directions)
      link_mob_lines(db, @current_location_id, parsed.mob_lines)
      apply_zone(db, @current_location_id, parsed.name, parsed.description)
    end
    private_class_method :observe_room

    def self.observe_exits(text)
      return if @current_location_id.nil?

      db = connection
      exits = Parser.parse_exits(text)
      return if exits.empty?

      link_room_exits(db, @current_location_id, exits.keys, exits)
      # check("exits") gives real destination names -- backfill any
      # already-scanned placeholder that's still nameless (§5), and give it
      # a zone-detection pass too: a placeholder can carry an anchor name
      # (e.g. "Inside The East Gate Of Midgaard") before it's ever visited.
      exits.each do |direction, dest_name|
        dest_id = Store.get_exit(db, @current_location_id, direction)
        next if dest_id.nil?

        Store.touch_location(db, dest_id, name: dest_name)
        apply_zone(db, dest_id, dest_name, nil)
      end
    end
    private_class_method :observe_exits

    def self.observe_move(args, text)
      if Parser.stale_pointer_signal?(text)
        @current_location_id = nil
        return
      end
      if MOVE_FAILURE_RE.match?(Parser.strip_ansi(text))
        return # didn't actually move -- pointer unchanged
      end

      direction = args[:direction]
      if direction.nil?
        @current_location_id = nil
        return
      end

      if @current_location_id.nil?
        # Pointer was never established or went stale, but this move's own
        # result usually auto-echoes the destination room in full -- the
        # same text shape a `look` would produce (confirmed live in the
        # Python port: every `move` in a session where an earlier
        # `look(target: ...)` had failed still returned a complete room
        # description). Treat it exactly like a fresh room observation
        # (text-matching fallback, §5) instead of silently discarding it --
        # we don't know the *origin* here, so we can't backfill an
        # origin->destination exits row, but the destination itself still
        # gets recorded.
        observe_room(text)
        return
      end

      db = connection
      known_dest = Store.get_exit(db, @current_location_id, direction)
      parsed_room = Parser.parse_room(text) # `move` usually auto-echoes the new room

      if known_dest
        # Known by graph position, full stop -- no text matching needed (§5).
        @current_location_id = known_dest
        Store.touch_location(db, @current_location_id, visited: true)
        if parsed_room
          Store.touch_location(db, @current_location_id,
                                name: parsed_room.name, description: parsed_room.description)
          link_room_exits(db, @current_location_id, parsed_room.exit_directions)
          link_mob_lines(db, @current_location_id, parsed_room.mob_lines)
          apply_zone(db, @current_location_id, parsed_room.name, parsed_room.description)
        end
        return
      end

      # Unscanned exit -- text-matching fallback, then backfill the exits row.
      origin_id = @current_location_id
      if parsed_room
        @current_location_id = Store.get_or_create_location(
          db, name: parsed_room.name, description: parsed_room.description, visited: true
        )
        Store.get_or_create_exit(db, origin_id, direction, @current_location_id)
        link_room_exits(db, @current_location_id, parsed_room.exit_directions)
        link_mob_lines(db, @current_location_id, parsed_room.mob_lines)
        apply_zone(db, @current_location_id, parsed_room.name, parsed_room.description)
      else
        # Moved, but this result didn't parse as a room -- pointer unknown
        # until the next successful room observation.
        @current_location_id = nil
      end
    end
    private_class_method :observe_move

    # ---------- mobs seen in a room (best-effort, per §4) ---------------------

    # §4: mob-presence lines during `look` are free-form sentences in the
    # same color code as the room title, with no delimiter other than
    # position and a loose "proper-noun + verb" shape -- explicitly
    # flagged there as best-effort, not a reliable parse. This extracts a
    # leading capitalized phrase as the mob's name; anything that doesn't
    # match that shape is skipped rather than guessed at.
    MOB_LINE_NAME_RE = /^([A-Z][a-zA-Z' ]*?)(?:,| (?:walks|sits|stands|is|paces|inspects))/.freeze
    # Plain item/scenery description lines ("There is a long, black stick
    # lying here.") also match the shape above, since "There" is
    # capitalized and followed by "is" -- this is exactly the
    # false-positive risk §4 already flagged. Excluding narrative
    # sentence-starters that are never how CircleMUD refers to a mob cuts
    # that specific false positive. NOT excluding "a"/"an"/"the" here --
    # those are legitimate, common leading words for generic (unnamed)
    # mobs ("A dwarven mining worker") -- excluding them would silently
    # drop real mob sightings.
    MOB_LINE_STOPWORDS = %w[there it you this these those].freeze

    def self.link_mob_lines(db, location_id, mob_lines)
      mob_lines.each do |line|
        m = MOB_LINE_NAME_RE.match(line)
        next if m.nil? || MOB_LINE_STOPWORDS.include?(m[1].strip.split.first.downcase)

        mob_id = Store.get_or_create_mob(db, m[1].strip)
        Store.link_mob(db, location_id, mob_id)
      end
    end
    private_class_method :link_mob_lines

    # ---------- item pickups ---------------------------------------------------

    def self.observe_pickup(args, text)
      return if @current_location_id.nil?

      parsed = Parser.parse_pickup(text, item_arg: args[:item])
      return if parsed.nil?

      db = connection
      item_id = Store.get_or_create_item(db, parsed.item_name, item_type: parsed.item_type)
      Store.link_item(db, @current_location_id, item_id, quantity: parsed.quantity)
    end
    private_class_method :observe_pickup

    # ---------- wield / current weapon (§8) -----------------------------------

    def self.observe_wield(text)
      weapon_name = Parser.parse_wield(text)
      return if weapon_name.nil?

      @current_weapon_id = Store.get_or_create_weapon(connection, weapon_name)
    end
    private_class_method :observe_wield

    # ---------- combat (§8) -----------------------------------------------------

    def self.resolve_combat_weapon_id(db, tool_name, args)
      if tool_name == "skill_strike"
        # Own identity from args, always its own row -- never merged with
        # "fists" or whatever's wielded (decision #7).
        skill = args[:skill] || "unknown_skill"
        return Store.get_or_create_weapon(db, skill)
      end
      # tool_name == "attack"
      return @current_weapon_id if @current_weapon_id

      Store.get_or_create_weapon(db, "fists")
    end
    private_class_method :resolve_combat_weapon_id

    def self.observe_combat(tool_name, args, text)
      target_name = args[:target]
      return if target_name.nil?

      parsed = Parser.parse_combat_result(text)
      return if parsed.landed.nil? && !parsed.killed # couldn't classify this result at all -- don't guess

      db = connection
      mob_id = Store.get_or_create_mob(db, target_name, disposition: "enemy")
      weapon_id = resolve_combat_weapon_id(db, tool_name, args)

      if mob_id != @current_fight_mob_id
        @current_fight_mob_id = mob_id
        @current_fight_hits_landed = 0
      end

      if parsed.landed
        Store.record_attack(db, mob_id, weapon_id, landed: true)
        @current_fight_hits_landed += 1
      end

      if parsed.killed
        Store.record_kill(db, mob_id, weapon_id)
        @current_fight_mob_id = nil
        @current_fight_hits_landed = 0
      end
    end
    private_class_method :observe_combat

    # ---------- consider (qualitative condition, §3/§8 cold-start fallback) --

    def self.observe_consider(args, text)
      return if @current_location_id.nil?

      target_name = args[:target]
      return if target_name.nil?

      condition = Parser.parse_condition(text)
      return if condition.nil?

      db = connection
      mob_id = Store.get_or_create_mob(db, target_name)
      Store.link_mob(db, @current_location_id, mob_id, condition: condition)
    end
    private_class_method :observe_consider

    # ---------- shop stock (needs_management_plan §4) -------------------------

    def self.observe_shop(text)
      return if @current_location_id.nil?

      db = connection
      Parser.parse_shop_stock(text).each do |item_name|
        item_type = Parser.classify_consumable(item_name)
        item_id = Store.get_or_create_item(db, item_name, item_type: item_type)
        # Shop stock is "Unlimited" in practice -- quantity isn't a
        # meaningful count here the way a gold pile's "There were 50
        # coins." is, so this deliberately passes quantity: nil rather
        # than inventing a number. Contrast with observe_pickup, where
        # quantity IS a real observed value.
        Store.link_item(db, @current_location_id, item_id, quantity: nil)
      end
    end
    private_class_method :observe_shop

    # ---------- spells / magic items (decision #8 -- identity only for now) --

    def self.observe_spell_identity_only(args)
      spell = args[:spell]
      Store.get_or_create_weapon(connection, spell) if spell
    end
    private_class_method :observe_spell_identity_only

    def self.observe_magic_item_identity_only(args)
      item = args[:item]
      Store.get_or_create_weapon(connection, item) if item
    end
    private_class_method :observe_magic_item_identity_only
  end
end
