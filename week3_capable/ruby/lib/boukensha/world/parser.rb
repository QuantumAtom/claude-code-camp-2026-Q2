module Boukensha
  module World
    module Parser
      ANSI_RE = /\e\[[0-9;]*m/.freeze
      # Every response ends in the player's own status bar -- a reliable
      # end-of-response delimiter, grounded in plan §4.
      STATUS_BAR_RE = /\d+H\s+\d+M\s+\d+V\s*\([^)]*\)\s*>\s*$/.freeze

      DIRECTION_LETTERS = { "n" => "north", "s" => "south", "e" => "east",
                             "w" => "west", "u" => "up", "d" => "down" }.freeze

      STALE_POINTER_PHRASES = [
        "you have been killed",
        "you suddenly feel a wrenching sensation",
      ].freeze

      def self.strip_ansi(text)
        (text || "").gsub(ANSI_RE, "")
      end

      # ANSI-stripped, status-bar-trimmed, blank-line-free lines.
      def self.lines(text)
        t = strip_ansi(text).gsub(STATUS_BAR_RE, "")
        t.gsub("\r\n", "\n").split("\n").map(&:strip).reject(&:empty?)
      end

      # §5: death/recall/teleport -- the graph pointer can no longer be
      # trusted, next room observation must fall back to text-matching.
      def self.stale_pointer_signal?(raw_text)
        text = strip_ansi(raw_text).downcase
        STALE_POINTER_PHRASES.any? { |phrase| text.include?(phrase) }
      end

      # ---------- rooms (look / move's auto room-echo) ----------------------

      EXITS_LINE_RE = /\[\s*Exits?:\s*([a-z\s]*)\]/i.freeze

      ParsedRoom = Struct.new(:name, :description, :exit_directions, :mob_lines, keyword_init: true)

      # Parses a `look`-shaped response: title, description, the compact
      # `[ Exits: n s w ]` line (letters only, no destination names -- see
      # parse_exits for the fuller `check("exits")` form), and whatever's
      # left as candidate mob-presence lines. Returns nil if this doesn't
      # look like a room description at all (no exits line found) -- e.g.
      # it's an `examine`/`consider` response instead, not a room.
      def self.parse_room(raw_text)
        ls = lines(raw_text)
        exits_idx = ls.find_index { |ln| EXITS_LINE_RE.match?(ln) }
        return nil if exits_idx.nil? || exits_idx.zero?

        m = EXITS_LINE_RE.match(ls[exits_idx])
        letters = m[1].split
        exit_directions = letters.map { |l| DIRECTION_LETTERS.fetch(l.downcase, l.downcase) }

        ParsedRoom.new(
          name: ls[0],
          description: ls[1...exits_idx].join(" ").strip,
          exit_directions: exit_directions,
          mob_lines: ls[(exits_idx + 1)..] || [],
        )
      end

      # ---------- exits (check("exits")) -------------------------------------

      EXIT_ENTRY_RE = /^(north|south|east|west|up|down)\s*-\s*(.+)$/i.freeze

      # `check("exits")` gives full direction words *and* the destination
      # room's name -- strictly more useful than look's letter-only line
      # (§4). Returns {direction => destination_name}, or {} if nothing
      # matched.
      def self.parse_exits(raw_text)
        result = {}
        lines(raw_text).each do |line|
          m = EXIT_ENTRY_RE.match(line)
          result[m[1].downcase] = m[2].strip if m
        end
        result
      end

      # ---------- item pickups (get_item) -------------------------------------

      ParsedPickup = Struct.new(:item_name, :quantity, :item_type, keyword_init: true)

      GOLD_QUANTITY_RE = /There were (\d+) coins?\./i.freeze
      GET_FAILURE_RE = /you (?:can'?t find|don'?t see|do not see)/i.freeze

      # Gold gives an exact, reliably-parseable quantity (§4's grounded
      # example) -- everything else falls back to the tool call's own
      # `item` argument for identity, since a generic 'you get the X' isn't
      # consistently phrased across item types the way the gold message is.
      def self.parse_pickup(raw_text, item_arg: nil)
        text = strip_ansi(raw_text)
        return nil if GET_FAILURE_RE.match?(text)

        gold_m = GOLD_QUANTITY_RE.match(text)
        return ParsedPickup.new(item_name: "gold", quantity: gold_m[1].to_i, item_type: "gold") if gold_m

        if text.match?(/^You get /) && item_arg
          return ParsedPickup.new(item_name: item_arg, quantity: nil)
        end
        nil
      end

      # ---------- equip / wield -----------------------------------------------

      WIELD_RE = /[Yy]ou wield (?:a|an|)\s*(.+?) in your/.freeze

      # Grounded directly in §4: 'You wield a short sword in your right
      # hand.' Returns the weapon name, or nil if this result wasn't a
      # successful wield (e.g. 'You don't have that item.').
      def self.parse_wield(raw_text)
        m = WIELD_RE.match(strip_ansi(raw_text))
        m && m[1].strip
      end

      # ---------- melee combat (attack / skill_strike) ------------------------

      ParsedCombatResult = Struct.new(:landed, :killed, keyword_init: true)

      KILL_RE = /is dead!\s*R\.I\.P\./i.freeze
      MISS_RE = /(the air instead|you miss|misses you|dodge|parr(?:y|ies)|block(?:s)?)/i.freeze
      # Anchored to the very start of the response on purpose: in every
      # sampled case (§4) the outcome of the player's own swing is the
      # opening line, not a later status line -- matching only there avoids
      # a false "landed" from an unrelated later "You ..." line (a proc
      # message, a status effect, etc.).
      LANDED_RE = /\A\e\[[0-9;]*mYou |\AYou /i.freeze

      # Grounded in §4's four melee samples (landed, missed, kill, and the
      # fact that a kill is its own unambiguous message). Landed-vs-missed
      # beyond those exact samples is a heuristic (checking for known miss
      # phrasing vs. an outgoing 'You ...' line) -- CircleMUD has many more
      # combat message variants than the handful sampled so far; treat this
      # as provisional and expand it as more real combat text gets
      # collected (plan §8's grounding-gap note).
      def self.parse_combat_result(raw_text)
        text = strip_ansi(raw_text)
        killed = KILL_RE.match?(text)
        return ParsedCombatResult.new(landed: false, killed: killed) if MISS_RE.match?(text)
        return ParsedCombatResult.new(landed: true, killed: killed) if LANDED_RE.match?(text) || killed

        ParsedCombatResult.new(landed: nil, killed: killed)
      end

      # ---------- consider (qualitative mob condition, §3's 7-bucket ladder) -

      # Best-effort mapping to stock CircleMUD's condition-ladder phrasing
      # (the same seven buckets the schema's CHECK constraint encodes) --
      # not directly grounded in a sampled `consider` transcript the way
      # melee combat is (§4 only shows one condition-reading example), so
      # treat this table as provisional pending more real samples, same
      # caveat as parse_combat_result.
      CONDITION_PHRASES = [
        [/excellent condition/i, "excellent"],
        [/a few scratches/i, "scratches"],
        [/some small wounds/i, "small_wounds"],
        [/quite a few wounds/i, "quite_a_few_wounds"],
        [/big nasty wounds|some big wounds/i, "big_wounds"],
        [/pretty hurt/i, "pretty_hurt"],
        [/awful condition|about to die/i, "awful"],
      ].freeze

      def self.parse_condition(raw_text)
        text = strip_ansi(raw_text)
        pair = CONDITION_PHRASES.find { |(pattern, _)| pattern.match?(text) }
        pair && pair[1]
      end

      # ---------- shop stock (needs_management_plan §4) -----------------------
      # shop("list") is free (no gold, no inventory change) and reveals the
      # whole stock in one tabular response -- grounded directly against
      # real session-log samples (needs_management_plan §2). shop("buy") is
      # deliberately NOT parsed for item identity: CircleMUD's purchase
      # confirmation only echoes the generic base name ("You now have a
      # bottle.") even when the shop's own listing distinguishes several
      # different bottled drinks ("A bottle of ale" vs "A bottle of
      # firebreather") -- trusting that text would silently collapse
      # distinct items into one row. `list` is strictly more specific and
      # it's free, so only it feeds the DB.
      SHOP_LINE_RE = /^\s*\d+\)\s+\S+\s+(.+?)\s+\d+\s*$/.freeze
      LEADING_ARTICLE_RE = /\A(?:a|an)\s+/i.freeze

      def self.parse_shop_stock(raw_text)
        text = strip_ansi(raw_text)
        text.scan(SHOP_LINE_RE).flatten.map { |name| name.sub(LEADING_ARTICLE_RE, "").strip }
      end

      # ---------- consumable classification (needs_management_plan §4/§5) ----
      # Best-effort keyword classifier, same "provisional, ground it further
      # as more shops get sampled" caveat as CONDITION_PHRASES above.
      # Grounded against real shop listings: "danish pastry"/"bread"/
      # "waybread" -> food; "bottle of X"/"barrel of X" -> drink;
      # "cashcard"/"box"/"bag"/"lantern"/"torch" -> correctly
      # unclassified, not guessed.
      FOOD_KEYWORDS = %w[bread pastry cake pie meat fruit cheese].freeze
      DRINK_KEYWORDS = %w[bottle barrel water ale beer wine juice].freeze

      def self.classify_consumable(name)
        lowered = (name || "").downcase
        return "food" if FOOD_KEYWORDS.any? { |k| lowered.include?(k) }
        return "drink" if DRINK_KEYWORDS.any? { |k| lowered.include?(k) }

        nil
      end

      # ---------- inventory (check("inventory")) ------------------------------
      # Grounded in a real transcript: "You are carrying:\r\na bottle\r\n...".

      # Returns [] for "You are carrying nothing." (or anything that
      # doesn't start with the expected header) rather than guessing.
      def self.parse_inventory(raw_text)
        ls = lines(raw_text)
        return [] if ls.empty? || !ls[0].downcase.start_with?("you are carrying")

        ls[1..] || []
      end

      # ---------- doors (check_door / open_door) --------------------------------
      # tools/mud.rb's own return value already prefixes "locked: "/
      # "not locked: " ahead of the raw server text -- a reliable signal
      # from the tool's own code, not something parsed out of prose.

      def self.parse_door_lock_state(raw_text)
        text = strip_ansi(raw_text)
        return true if text.start_with?("locked:")
        return false if text.start_with?("not locked:")

        nil
      end

      # ---------- spells / magic items -------------------------------------------
      # Decision #8: identity resolution (spell/item name from the tool
      # call's own args) is safe to use now -- see world.rb, which reads
      # args[:spell]/args[:item] directly rather than calling into this
      # parser. There is deliberately no parse_spell_result/
      # parse_magic_item_result here yet: no mage/spellcasting-class
      # account exists on this MUD to sample real cast_spell/
      # use_magic_item output from (plan §8's grounding-gap note,
      # discussed and confirmed in the plan's decision #8). Add it here,
      # following the same "ground it in real text first" method as
      # everything else in this module, once that account exists.

      # ---------- zone/town identity (goto_tool_plan §5) -----------------------
      # Deliberately NOT a general "extract the place name from this text"
      # parser: checked real session-log room text and most in-town rooms
      # ("The Bakery", "The General Store", "The Grunting Boar") never
      # mention the town's name in either their title or description at all
      # -- only a handful of "anchor" rooms do (gate rooms, Market Square,
      # the Great Field). A small known-name list matched against those
      # anchors, same pattern as STALE_POINTER_PHRASES above -- add to this
      # array as new towns get sampled from real play; the actual reach
      # into every other room is Store.propagate_zone's flood-fill, not
      # this method.
      KNOWN_ZONE_NAMES = ["Midgaard"].freeze
      ZONE_NAME_RE = Regexp.new(
        "\\b(#{KNOWN_ZONE_NAMES.map { |z| Regexp.escape(z) }.join('|')})\\b", Regexp::IGNORECASE
      ).freeze

      # Returns the canonical zone name if this room's own title/description
      # explicitly names a known town, else nil.
      def self.detect_seed_zone(name, description)
        text = "#{name} #{description}"
        m = ZONE_NAME_RE.match(text)
        return nil if m.nil?

        matched = m[1].downcase
        KNOWN_ZONE_NAMES.find { |canonical| canonical.downcase == matched }
      end
    end
  end
end
