require "mud_manager"

module Boukensha
  module Tools
    # Mud registers MUD-gameplay tools against a registry.
    #
    # A single MudManager::Session is created when the tools are registered and
    # shared by every tool via closure — the agent logs in once and reuses the
    # connection for all subsequent tool calls.
    #
    # Tools registered (grouped by concern):
    #
    #   Connection
    #     mud_connect       — open socket and log in
    #     mud_disconnect    — close socket gracefully
    #     mud_status        — report whether the session is open
    #
    #   Perception
    #     look              — look at the room or a specific target
    #     examine           — examine something in detail
    #     read              — read a sign, book, letter, or other readable item
    #     check             — query self-info (score, inventory, equipment, exits, gold…)
    #
    #   Movement
    #     move              — go a compass direction or up/down
    #     go_to             — walk directly to a known location using the mapped world DB
    #     return_to_start   — walk back to wherever the last go_to call departed from
    #     flee              — flee from combat
    #     set_position      — change body position (stand/sit/rest/sleep/wake)
    #     track             — track a mob or player by name to find their direction
    #
    #   Needs
    #     check_needs       — detect hunger/thirst and resolve it locally where possible
    #
    #   Doors
    #     check_door        — check whether a door is locked (subtool used by open_door)
    #     open_door         — open a door, unlocking it first if it's locked and unlockable
    #
    #   Combat
    #     attack            — attack a target (kill / hit / murder)
    #     skill_strike      — use a combat skill (bash, kick, backstab, rescue, assist)
    #     consider          — assess a mob's relative strength before fighting
    #
    #   Communication
    #     say               — say/emote/reply in the room
    #     tell              — tell/whisper/ask a specific player
    #     channel_say       — broadcast over a channel (shout, gossip, auction…)
    #
    #   Inventory & equipment
    #     get_item          — pick up an item (optionally from a container)
    #     drop_item         — drop, donate, or junk an item
    #     put_item          — put an item into a container
    #     equip_item        — wear, wield, hold, grab, or remove an item
    #     consume_item      — eat, drink, taste, or sip something
    #
    #   Magic
    #     cast_spell        — cast a named spell with an optional target
    #     use_magic_item    — quaff a potion, recite a scroll, or use a wand/staff
    #
    #   Utility
    #     shop              — buy, sell, list, or value items at a shop
    #     practice          — list or practice a skill with a guildmaster
    #     save_character    — save the character to disk
    #     send_raw          — send an arbitrary command string (escape hatch)
    #
    # Usage:
    #
    #   Boukensha::Tools::Mud.register(
    #     registry,
    #     host:     "localhost",
    #     port:     4000,
    #     name:     "Gandalf",
    #     password: "secret"
    #   )
    #
    module Mud
      def self.register(registry, host: "localhost", port: 4000, name:, password:)
        session = MudManager::Session.new(host: host, port: port)
        p       = MudManager::Primitives

        # Send a primitive command and return the MUD's response text.
        # Raises if the session is not open.
        #
        # We drain any stale buffered bytes (leftover login output, async ticks,
        # etc.) before sending so that read_until_prompt sees only fresh data
        # produced by this command. Then we wait for CircleMUD's "> " prompt
        # sentinel, which the server always appends at the end of a response.
        send_cmd = lambda do |command|
          session.drain
          session.send_command(command)
          session.read_until_prompt
        end

        # Return an error string if the session is not open so the agent
        # can decide whether to call mud_connect first.
        guard = lambda do
          unless session.open?
            "error: not connected — call mud_connect first"
          end
        end

        # ── Connection ─────────────────────────────────────────────────────

        registry.tool "mud_connect",
          description: "Open the connection to the MUD server and log in with the configured " \
                       "character name and password. Safe to call when already connected " \
                       "(returns current status instead of reconnecting).",
          parameters: {} do
          if session.open?
            "already connected to #{session.host}:#{session.port}"
          else
            begin
              session.open
              welcome = session.login(name, password)
              "connected to #{session.host}:#{session.port}\n#{welcome}"
            rescue MudManager::Session::Error => e
              "error: #{e.message}"
            end
          end
        end

        registry.tool "mud_disconnect",
          description: "Close the connection to the MUD server gracefully.",
          parameters: {} do
          if session.open?
            session.close
            "disconnected"
          else
            "already disconnected"
          end
        end

        registry.tool "mud_status",
          description: "Return whether the MUD session is currently connected.",
          parameters: {} do
          session.open? ? "connected to #{session.host}:#{session.port}" : "disconnected"
        end

        # ── Perception ──────────────────────────────────────────────────────

        registry.tool "look",
          description: "Look at the current room or at a specific target. " \
                       "Call with NO arguments to describe the current room (do NOT pass target: 'room'). " \
                       "Pass a target to inspect a specific item, mob, or player (e.g. target: 'sword'). " \
                       "Use preposition 'in' to look inside a container, 'at' to inspect something, " \
                       "or a direction (north/east/south/west/up/down) to peek into an adjacent room.",
          parameters: {
            target:      { type: "string", description: "Item, mob, or player name to inspect. Omit entirely to describe the current room." },
            preposition: { type: "string", description: "Preposition: in, at, north, east, south, west, up, down (optional)" }
          } do |target: nil, preposition: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.look(target: target, preposition: preposition))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "examine",
          description: "Examine a target in detail (more verbose than look).",
          parameters: {
            target: { type: "string", description: "The item, mob, or player to examine" }
          } do |target:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.examine(target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "read",
          description: "Read text on a sign, book, letter, scroll, or other readable item.",
          parameters: {
            target: { type: "string", description: "The sign, book, or other readable item to read" }
          } do |target:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.look(mode: "read", target: target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "check",
          description: "Query information about your character or surroundings. " \
                       "Kinds: score, inventory, equipment, gold, exits, time, weather, " \
                       "levels, wimpy, toggle, where.",
          parameters: {
            kind: { type: "string", description: "What to check: score | inventory | equipment | gold | exits | time | weather | levels | wimpy | toggle | where" }
          } do |kind:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.info_self(kind))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Movement ────────────────────────────────────────────────────────

        registry.tool "move",
          description: "Move in a compass direction or up/down.",
          parameters: {
            direction: { type: "string", description: "Direction: north | east | south | west | up | down" }
          } do |direction:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.move(direction))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # goto_tool_plan §6: pure circuit breaker against an unexpectedly
        # long BFS result dumping a huge hop list into one tool call -- BFS
        # itself can't loop forever (finite graph, visited-set), this just
        # keeps any single result reasonably sized. Tune freely; not
        # derived from anything load-bearing.
        go_to_max_hops = 50

        # needs_management_plan follow-up: remembers where the player was
        # right before the most recent go_to departed, so a food/drink/shop
        # errand can be undone with a plain return_to_start call afterward.
        # Deliberately just "last go_to's origin", not a full history stack
        # -- simplest thing that covers the single-errand case; a
        # nested-trip breadcrumb trail is a bigger feature nobody's asked
        # for yet.
        return_point = { location_id: nil }

        registry.tool "go_to",
          description: "Walk directly to a known location using the mapped world database " \
                       "instead of issuing individual move commands. Pass a place name (e.g. " \
                       "'weapon shop') or 'place in town' (e.g. 'weapon shop in midgaard'). " \
                       "Only works for places already discovered through play — if the exact " \
                       "place isn't mapped yet but its town is, this walks to the nearest " \
                       "known point in that town instead and explains that the rest needs " \
                       "manual exploring. Returns either the walk result or an explanation of " \
                       "why it couldn't route there.",
          parameters: {
            destination: { type: "string", description: "Where to go, e.g. 'weapon shop', 'the temple', 'weapon shop in midgaard'" }
          } do |destination:|
          # goto_tool_plan: multi-hop walk, driven entirely by world.db --
          # pathfinding and every intermediate `move` happen right here in
          # Ruby, costing zero extra LLM round-trips; only this call and its
          # single return value ever touch the model.
          next guard.call if guard.call

          current_id = Boukensha::World.current_location_id
          next "error: current location unknown — call look first" if current_id.nil?

          db = Boukensha::World.connection
          target_id, note = Boukensha::World::Pathfind.resolve_destination(db, current_id, destination)
          next note if target_id.nil?

          path = Boukensha::World::Pathfind.bfs_path(db, current_id, target_id)
          next "'#{destination}' is known but no discovered route reaches it yet." if path.nil?
          if path.empty?
            # Empty path from bfs_path only ever means start == target (§6)
            # -- confirmed live: querying a destination that already
            # matches the current room. No move happened, so there's no
            # fresh room text to append (unlike the loop below, which gets
            # one for free from the last move's auto-echo).
            msg = "Already at \"#{destination}\"."
            msg += "\n#{note}" if note
            next msg
          end
          if path.length > go_to_max_hops
            next "route to '#{destination}' is #{path.length} hops — too long to auto-walk " \
                 "(cap #{go_to_max_hops}); needs manual travel or a shorter waypoint."
          end

          # Only recorded once we know a real walk is about to happen --
          # never overwrites a good return point with a failed/no-op call.
          return_point[:location_id] = current_id

          taken = []
          result_text = ""
          failure = nil
          path.each do |direction|
            begin
              result_text = send_cmd.call(p.move(direction))
            rescue ArgumentError => e
              failure = "stopped after #{taken.length}/#{path.length} hops (#{taken.join(', ')}) — error: #{e.message}"
              break
            end
            # Same write-back hook a manual move call goes through (§6a) --
            # go_to is a scheduler for the move primitive, not a bypass of it.
            Boukensha::World.observe("move", { direction: direction }, result_text)
            if Boukensha::World.move_failed?(result_text)
              failure = "stopped after #{taken.length}/#{path.length} hops (#{taken.join(', ')}) — " \
                        "#{direction} failed: #{result_text.strip}"
              break
            end
            taken << direction
          end
          next failure if failure

          summary = "Walked #{taken.length} rooms (#{taken.join(', ')}) to \"#{destination}\"."
          summary += "\n#{note}" if note
          "#{summary}\n\n#{result_text}"
        end

        registry.tool "return_to_start",
          description: "Walk back to the location you were at right before your most recent " \
                       "go_to call -- e.g. after visiting a shop or fountain to resolve " \
                       "hunger/thirst. Uses the same mapped-route walking as go_to. Fails if " \
                       "you haven't called go_to yet this session, or if no discovered route " \
                       "back exists.",
          parameters: {} do
          # needs_management_plan follow-up: deliberately its own small
          # loop rather than sharing code with go_to's (already
          # live-verified) hop loop above -- avoids touching working,
          # tested code for a same-day addition.
          next guard.call if guard.call

          return_id = return_point[:location_id]
          next "error: no remembered starting point -- call go_to at least once first" if return_id.nil?

          current_id = Boukensha::World.current_location_id
          next "error: current location unknown — call look first" if current_id.nil?
          next "Already back at the starting point." if current_id == return_id

          db = Boukensha::World.connection
          path = Boukensha::World::Pathfind.bfs_path(db, current_id, return_id)
          if path.nil?
            # Confirmed live: the exact remembered location_id can be
            # stranded on an unreachable island (duplicate-row tradeoff,
            # same root cause go_to's disambiguation fallback already
            # handles) even though a physically-identical duplicate room
            # is reachable. Try that before giving up.
            fallback = Boukensha::World::Pathfind.find_reachable_duplicate(db, current_id, return_id)
            next "no discovered route back to the starting point from here." if fallback.nil?

            return_id, path = fallback
            # Confirmed live: the fallback can resolve to a same-name
            # duplicate that's actually zero hops away (current position
            # already matches it) -- same "Already back" case as the
            # exact-id check above, just reached via the duplicate path.
            next "Already back at the starting point." if path.empty?
          end
          if path.length > go_to_max_hops
            next "route back is #{path.length} hops — too long to auto-walk " \
                 "(cap #{go_to_max_hops}); needs manual travel."
          end

          taken = []
          result_text = ""
          failure = nil
          path.each do |direction|
            begin
              result_text = send_cmd.call(p.move(direction))
            rescue ArgumentError => e
              failure = "stopped after #{taken.length}/#{path.length} hops (#{taken.join(', ')}) — error: #{e.message}"
              break
            end
            Boukensha::World.observe("move", { direction: direction }, result_text)
            if Boukensha::World.move_failed?(result_text)
              failure = "stopped after #{taken.length}/#{path.length} hops (#{taken.join(', ')}) — " \
                        "#{direction} failed: #{result_text.strip}"
              break
            end
            taken << direction
          end
          next failure if failure

          "Walked #{taken.length} rooms (#{taken.join(', ')}) back to the starting point.\n\n#{result_text}"
        end

        # needs_management_plan §6: matches already-owned inventory lines
        # against Parser.classify_consumable so an already-owned "a
        # bread"/"a bottle" is recognized without needing a DB lookup --
        # the DB is only consulted (via supply_note below) once nothing's
        # on hand, same "check locally before falling back to a lookup"
        # ordering go_to's resolver already uses.
        match_inventory_to_needs = lambda do |inv_lines|
          have_food = nil
          have_drink = nil
          inv_lines.each do |line|
            item_type = Boukensha::World::Parser.classify_consumable(line)
            have_food ||= line if item_type == "food"
            have_drink ||= line if item_type == "drink"
          end
          [have_food, have_drink]
        end

        supply_note = lambda do |db, item_type, need_word|
          current_id = Boukensha::World.current_location_id
          next "You are #{need_word} and have nothing on hand; current location unknown — call look first." if current_id.nil?

          found = Boukensha::World::Pathfind.find_nearest_supply(db, current_id, item_type)
          next "You are #{need_word}, have nothing on hand, and no known #{item_type} source has been discovered yet." if found.nil?

          _, loc_name, item_name, hops = found
          "You are #{need_word} and have nothing on hand. Nearest known #{item_type} source: " \
            "\"#{loc_name}\" (#{hops} hop#{hops == 1 ? '' : 's'} away, sells \"#{item_name}\")."
        end

        registry.tool "check_needs",
          description: "Check whether you're hungry or thirsty, and if so, try to resolve it: drinks " \
                       "straight from a fountain here for free if one exists, checks your inventory " \
                       "for something already on hand, and if nothing's available, looks up the " \
                       "nearest known place (from the mapped world database) that sells food or " \
                       "drink. Does not eat or drink anything from your inventory on its own -- it " \
                       "reports what's available so you can decide whether to consume it. Returns " \
                       "'not hungry or thirsty' if neither applies.",
          parameters: {} do
          # needs_management_plan: collapses the Week 2 "check each empty
          # water bottle" flailing into one deterministic sweep -- worst
          # case 3 MUD round-trips (score, fountain attempt, inventory)
          # behind a single LLM tool call, same value proposition as go_to.
          next guard.call if guard.call

          score_text = send_cmd.call(p.info_self("score"))
          lowered_score = score_text.downcase
          hungry = lowered_score.include?("you are hungry")
          thirsty = lowered_score.include?("you are thirsty")
          next "Not hungry or thirsty -- no action needed." unless hungry || thirsty

          notes = []

          if thirsty
            # Free first move: no need to have detected a fountain in
            # advance, the MUD's own response tells us whether one exists
            # here (§2 -- "You drink the clear water." vs. not seeing one).
            fountain_result = send_cmd.call(p.consume("drink", "fountain"))
            if fountain_result.downcase.include?("you drink")
              thirsty = false
              notes << "Drank from a fountain here: #{fountain_result.strip}"
            end
          end

          if hungry || thirsty
            inv_text = send_cmd.call(p.info_self("inventory"))
            inv_lines = Boukensha::World::Parser.parse_inventory(inv_text)
            have_food, have_drink = match_inventory_to_needs.call(inv_lines)
            db = Boukensha::World.connection

            if hungry
              notes << if have_food
                         "You are hungry and already have \"#{have_food}\" -- consume it?"
                       else
                         supply_note.call(db, "food", "hungry")
                       end
            end
            if thirsty
              notes << if have_drink
                         "You are thirsty and already have \"#{have_drink}\" -- consume it?"
                       else
                         supply_note.call(db, "drink", "thirsty")
                       end
            end
          end

          notes.join("\n")
        end

        registry.tool "flee",
          description: "Attempt to flee from combat in a random available direction.",
          parameters: {} do
          next guard.call if guard.call
          send_cmd.call(p.flee)
        end

        registry.tool "set_position",
          description: "Change body position. Use 'rest' or 'sleep' between fights to recover " \
                       "HP and mana. Must be standing to move or fight.",
          parameters: {
            position: { type: "string", description: "Position: stand | sit | rest | sleep | wake" }
          } do |position:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.set_position(position))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "track",
          description: "Attempt to track a mob or player by name, revealing which direction " \
                       "they are in. Requires the Track skill.",
          parameters: {
            target: { type: "string", description: "Name of the mob or player to track" }
          } do |target:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.track(target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Doors ───────────────────────────────────────────────────────────

        # Attempt to open a door and report whether the response indicates it's
        # locked. There is no separate "peek" command on the MUD — the only way
        # to learn a door's lock state is to try opening it — so this doubles as
        # the actual open attempt: if it turns out to be unlocked, it's now open.
        check_door_locked = lambda do |target, direction|
          response = send_cmd.call(p.door("open", target, direction: direction))
          [response.to_s.match?(/lock/i), response]
        end

        # Heuristic for a failed unlock attempt (wrong/missing key, stuck lock,
        # etc.) versus a successful one (typically a terse "*Click*").
        unlock_failed = lambda do |response|
          response.to_s.match?(/don'?t have|do not have|no key|won'?t (turn|budge)|can'?t seem|cannot seem/i)
        end

        registry.tool "check_door",
          description: "Check whether a door or exit is locked, without forcing it open. " \
                       "This is the subtool open_door uses internally; call it directly if you " \
                       "only want to know the lock state. Note: if the door turns out to be " \
                       "unlocked, this check opens it as a side effect (there's no separate " \
                       "peek command on the MUD).",
          parameters: {
            target:    { type: "string", description: "Name of the door or exit (e.g. 'door', 'gate')" },
            direction: { type: "string", description: "Direction the door is in (optional): north | east | south | west | up | down" }
          } do |target:, direction: nil|
          next guard.call if guard.call
          begin
            locked, response = check_door_locked.call(target, direction)
            "#{locked ? 'locked' : 'not locked'}: #{response}"
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "open_door",
          description: "Open a door or exit. Checks whether it's locked first; if it is, " \
                       "attempts to unlock it and then opens it. If it cannot be unlocked " \
                       "(e.g. no key), reports that the door is locked and unable to be unlocked.",
          parameters: {
            target:    { type: "string", description: "Name of the door or exit (e.g. 'door', 'gate')" },
            direction: { type: "string", description: "Direction the door is in (optional): north | east | south | west | up | down" }
          } do |target:, direction: nil|
          next guard.call if guard.call
          begin
            locked, response = check_door_locked.call(target, direction)
            next response unless locked

            unlock_response = send_cmd.call(p.door("unlock", target, direction: direction))
            if unlock_failed.call(unlock_response)
              "the door is locked and unable to be unlocked (#{unlock_response.strip})"
            else
              send_cmd.call(p.door("open", target, direction: direction))
            end
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Combat ──────────────────────────────────────────────────────────

        registry.tool "attack",
          description: "Attack a target. Style 'kill' is the standard approach; " \
                       "'murder' bypasses the mercy check; 'hit' is a one-off strike.",
          parameters: {
            target: { type: "string", description: "Name of the mob or player to attack" },
            style:  { type: "string", description: "Attack style: kill | hit | murder (default: kill)" }
          } do |target:, style: "kill"|
          next guard.call if guard.call
          begin
            send_cmd.call(p.attack(style, target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "skill_strike",
          description: "Use a combat skill against a target.",
          parameters: {
            skill:  { type: "string", description: "Skill: bash | kick | backstab | rescue | assist" },
            target: { type: "string", description: "Name of the mob or player" }
          } do |skill:, target:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.skill_strike(skill, target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "consider",
          description: "Assess a mob's relative strength before engaging in combat. " \
                       "Returns a phrase such as 'You could kill it easily' or " \
                       "'Death awaits you'. Always consider before attacking an unknown mob.",
          parameters: {
            target: { type: "string", description: "Name of the mob to consider" }
          } do |target:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.consider(target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Communication ───────────────────────────────────────────────────

        registry.tool "say",
          description: "Speak or emote in the current room.",
          parameters: {
            text: { type: "string", description: "What to say or emote" },
            mode: { type: "string", description: "Mode: say | emote | reply (default: say)" }
          } do |text:, mode: "say"|
          next guard.call if guard.call
          begin
            send_cmd.call(p.say_local(mode, text))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "tell",
          description: "Send a private message to a specific player.",
          parameters: {
            target: { type: "string", description: "Player name to message" },
            text:   { type: "string", description: "The message" },
            mode:   { type: "string", description: "Mode: tell | whisper | ask (default: tell)" }
          } do |target:, text:, mode: "tell"|
          next guard.call if guard.call
          begin
            send_cmd.call(p.say_targeted(mode, target, text))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "channel_say",
          description: "Broadcast a message over a global channel.",
          parameters: {
            channel: { type: "string", description: "Channel: shout | gossip | auction | grats | holler" },
            text:    { type: "string", description: "The message to broadcast" }
          } do |channel:, text:|
          next guard.call if guard.call
          begin
            send_cmd.call(p.say_channel(channel, text))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Inventory & equipment ────────────────────────────────────────────

        registry.tool "get_item",
          description: "Pick up an item from the room or from a container.",
          parameters: {
            item:      { type: "string",  description: "Name of the item to get" },
            container: { type: "string",  description: "Container to get it from (optional)" },
            count:     { type: "integer", description: "Number of items to get (optional)" }
          } do |item:, container: nil, count: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.get(item, container: container, count: count))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "drop_item",
          description: "Drop, donate, or junk an item.",
          parameters: {
            item:  { type: "string",  description: "Name of the item" },
            mode:  { type: "string",  description: "Mode: drop | donate | junk (default: drop)" },
            count: { type: "integer", description: "Number of items (optional)" }
          } do |item:, mode: "drop", count: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.drop(mode, item, count: count))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "put_item",
          description: "Put an item into a container.",
          parameters: {
            item:      { type: "string",  description: "Name of the item to put" },
            container: { type: "string",  description: "Name of the container" },
            count:     { type: "integer", description: "Number of items (optional)" }
          } do |item:, container:, count: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.put(item, container, count: count))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "equip_item",
          description: "Wear, wield, hold, grab, or remove an item.",
          parameters: {
            item:     { type: "string", description: "Name of the item" },
            action:   { type: "string", description: "Action: wear | wield | hold | grab | remove" },
            body_loc: { type: "string", description: "Body location to wear on (optional, e.g. 'head', 'finger')" }
          } do |item:, action:, body_loc: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.equip(action, item, body_loc: body_loc))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "consume_item",
          description: "Eat, drink, taste, or sip a consumable item.",
          parameters: {
            item: { type: "string", description: "Name of the item to consume" },
            mode: { type: "string", description: "Mode: eat | drink | taste | sip (default: eat)" }
          } do |item:, mode: "eat"|
          next guard.call if guard.call
          begin
            send_cmd.call(p.consume(mode, item))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Magic ────────────────────────────────────────────────────────────

        registry.tool "cast_spell",
          description: "Cast a spell, optionally at a target.",
          parameters: {
            spell:  { type: "string", description: "Full spell name (e.g. 'cure light wounds', 'magic missile')" },
            target: { type: "string", description: "Target mob, player, or object (optional)" }
          } do |spell:, target: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.cast(spell, target: target))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "use_magic_item",
          description: "Activate a magic item: quaff a potion, recite a scroll, or use a wand/staff.",
          parameters: {
            item:        { type: "string", description: "Name of the item to activate" },
            mode:        { type: "string", description: "Mode: quaff | recite | use" },
            target_args: { type: "string", description: "Optional target arguments (e.g. mob name for a wand)" }
          } do |item:, mode:, target_args: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.use_magic_item(mode, item, target_args: target_args))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        # ── Utility ──────────────────────────────────────────────────────────

        registry.tool "shop",
          description: "Interact with a shop NPC: list stock, buy, sell, or get the value of an item.",
          parameters: {
            action: { type: "string", description: "Action: list | buy | sell | value | offer" },
            args:   { type: "string", description: "Item name or number (optional)" }
          } do |action:, args: nil|
          next guard.call if guard.call
          begin
            send_cmd.call(p.shop(action, args: args))
          rescue ArgumentError => e
            "error: #{e.message}"
          end
        end

        registry.tool "practice",
          description: "List your known skills at a guildmaster, or practice a specific skill.",
          parameters: {
            skill: { type: "string", description: "Skill name to practice (omit to list all)" }
          } do |skill: nil|
          next guard.call if guard.call
          send_cmd.call(p.practice(skill))
        end

        registry.tool "save_character",
          description: "Save your character to disk so progress is not lost on disconnect.",
          parameters: {} do
          next guard.call if guard.call
          send_cmd.call(p.save_char)
        end

        registry.tool "send_raw",
          description: "Send an arbitrary command string to the MUD and return the response. " \
                       "Use this as an escape hatch when no structured tool fits.",
          parameters: {
            command: { type: "string", description: "The raw command to send (e.g. 'who', 'help backstab')" }
          } do |command:|
          next guard.call if guard.call
          session.send_command(command)
          session.read_until_quiet
        end

        # Auto-connect at startup so the session is ready immediately and the
        # agent doesn't need to waste a turn calling mud_connect first.
        begin
          session.open
          session.login(name, password)
        rescue MudManager::Session::Error => e
          warn "[boukensha] MUD auto-connect failed: #{e.message} — call mud_connect manually"
        end

      end # def self.register
    end # Mud
  end # Tools
end # Boukensha
