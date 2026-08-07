import re
import sys
from pathlib import Path

# mud_manager isn't a pip-installed package — it's a sibling local library
# at week0_explore/mud_manager/python/, mirroring how the Ruby gem lives at
# week0_explore/mud_manager/ and is pulled in via a Gemfile path dependency.
_MUD_MANAGER_DIR = Path(__file__).resolve().parents[4] / "week0_explore" / "mud_manager" / "python"
if str(_MUD_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(_MUD_MANAGER_DIR))

from mud_manager.session import Session
from mud_manager import primitives as p

from .. import world
from ..world import parser, pathfind

# goto_tool_plan §6: pure circuit breaker against an unexpectedly long BFS
# result dumping a huge hop list into one tool call -- BFS itself can't loop
# forever (finite graph, visited-set), this just keeps any single result
# reasonably sized. Tune freely; not derived from anything load-bearing.
GO_TO_MAX_HOPS = 50


# needs_management_plan §6: matches already-owned inventory lines against
# classify_consumable() so an already-owned "a bread"/"a bottle" is
# recognized without needing a DB lookup -- the DB is only consulted (via
# _supply_note below) once nothing's on hand, same "check locally before
# falling back to a lookup" ordering go_to's resolver already uses.
def _match_inventory_to_needs(inv_lines):
    have_food = None
    have_drink = None
    for line in inv_lines:
        item_type = parser.classify_consumable(line)
        if item_type == "food" and have_food is None:
            have_food = line
        elif item_type == "drink" and have_drink is None:
            have_drink = line
    return have_food, have_drink


def _supply_note(conn, item_type, need_word):
    current_id = world.current_location_id()
    if current_id is None:
        return f"You are {need_word} and have nothing on hand; current location unknown -- call look first."
    found = pathfind.find_nearest_supply(conn, current_id, item_type)
    if found is None:
        return f"You are {need_word}, have nothing on hand, and no known {item_type} source has been discovered yet."
    _, loc_name, item_name, hops = found
    return (f'You are {need_word} and have nothing on hand. Nearest known {item_type} source: '
            f'"{loc_name}" ({hops} hop{"s" if hops != 1 else ""} away, sells "{item_name}").')


# Mud registers MUD-gameplay tools against a registry.
#
# A single MudManager Session is created when the tools are registered and
# shared by every tool via closure — the agent logs in once and reuses the
# connection for all subsequent tool calls.
def register(registry, *, host="localhost", port=4000, name, password):
    session = Session(host=host, port=port)

    # Send a primitive command and return the MUD's response text.
    #
    # We drain any stale buffered bytes (leftover login output, async ticks,
    # etc.) before sending so that read_until_prompt sees only fresh data
    # produced by this command. Then we wait for CircleMUD's "> " prompt
    # sentinel, which the server always appends at the end of a response.
    def send_cmd(command):
        session.drain()
        session.send_command(command)
        return session.read_until_prompt()

    # Return an error string if the session is not open so the agent
    # can decide whether to call mud_connect first.
    def guard():
        if not session.is_open():
            return "error: not connected — call mud_connect first"
        return None

    # ── Connection ─────────────────────────────────────────────────────

    def mud_connect():
        if session.is_open():
            return f"already connected to {session.host}:{session.port}"
        try:
            session.open()
            welcome = session.login(name, password) or ""
            return f"connected to {session.host}:{session.port}\n{welcome}"
        except Session.Error as e:
            return f"error: {e}"

    def mud_disconnect():
        if session.is_open():
            session.close()
            return "disconnected"
        return "already disconnected"

    def mud_status():
        return f"connected to {session.host}:{session.port}" if session.is_open() else "disconnected"

    # ── Perception ──────────────────────────────────────────────────────

    def look(target=None, preposition=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.look(target=target, preposition=preposition))
        except ValueError as e:
            return f"error: {e}"

    def examine(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.examine(target))
        except ValueError as e:
            return f"error: {e}"

    def read(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.look(mode="read", target=target))
        except ValueError as e:
            return f"error: {e}"

    def check(kind):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.info_self(kind))
        except ValueError as e:
            return f"error: {e}"

    # ── Movement ────────────────────────────────────────────────────────

    def move(direction):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.move(direction))
        except ValueError as e:
            return f"error: {e}"

    # needs_management_plan follow-up: remembers where the player was right
    # before the most recent go_to departed, so a food/drink/shop errand can
    # be undone with a plain return_to_start() call afterward. A dict (not
    # a bare variable) so the nested go_to/return_to_start closures below
    # can mutate it without `nonlocal`. Deliberately just "last go_to's
    # origin", not a full history stack -- simplest thing that covers the
    # single-errand case; a nested-trip breadcrumb trail is a bigger
    # feature nobody's asked for yet.
    _return_point: dict = {"location_id": None}

    def go_to(destination):
        # goto_tool_plan: multi-hop walk, driven entirely by world.db --
        # pathfinding and every intermediate `move` happen right here in
        # Python, costing zero extra LLM round-trips; only this call and its
        # single return value ever touch the model.
        err = guard()
        if err:
            return err

        current_id = world.current_location_id()
        if current_id is None:
            return "error: current location unknown — call look first"

        conn = world.connection()
        target_id, note = pathfind.resolve_destination(conn, current_id, destination)
        if target_id is None:
            return note

        path = pathfind.bfs_path(conn, current_id, target_id)
        if path is None:
            return f"'{destination}' is known but no discovered route reaches it yet."
        if not path:
            # Empty path from bfs_path only ever means start == target (§6)
            # -- confirmed live: querying a destination that already
            # matches the current room. No move happened, so there's no
            # fresh room text to append (unlike the loop below, which gets
            # one for free from the last move's auto-echo).
            return f'Already at "{destination}".' + (f"\n{note}" if note else "")
        if len(path) > GO_TO_MAX_HOPS:
            return (f"route to '{destination}' is {len(path)} hops — too long to auto-walk "
                     f"(cap {GO_TO_MAX_HOPS}); needs manual travel or a shorter waypoint.")

        # Only recorded once we know a real walk is about to happen --
        # never overwrites a good return point with a failed/no-op call.
        _return_point["location_id"] = current_id

        taken = []
        result_text = ""
        for direction in path:
            try:
                result_text = send_cmd(p.move(direction))
            except ValueError as e:
                return f"stopped after {len(taken)}/{len(path)} hops ({', '.join(taken)}) — error: {e}"
            # Same write-back hook a manual move call goes through (§6a) --
            # go_to is a scheduler for the move primitive, not a bypass of it.
            world.observe("move", {"direction": direction}, result_text)
            if world.move_failed(result_text):
                return (f"stopped after {len(taken)}/{len(path)} hops ({', '.join(taken)}) — "
                        f"{direction} failed: {result_text.strip()}")
            taken.append(direction)

        summary = f'Walked {len(taken)} rooms ({", ".join(taken)}) to "{destination}".'
        if note:
            summary += f"\n{note}"
        return f"{summary}\n\n{result_text}"

    def return_to_start():
        # needs_management_plan follow-up: walks back to wherever go_to's
        # most recent call departed from -- e.g. after a food/drink/shop
        # errand. Deliberately its own small loop rather than sharing code
        # with go_to's (already live-verified) hop loop above -- avoids
        # touching working, tested code for a same-day addition.
        err = guard()
        if err:
            return err

        return_id = _return_point["location_id"]
        if return_id is None:
            return "error: no remembered starting point -- call go_to at least once first"

        current_id = world.current_location_id()
        if current_id is None:
            return "error: current location unknown — call look first"
        if current_id == return_id:
            return "Already back at the starting point."

        conn = world.connection()
        path = pathfind.bfs_path(conn, current_id, return_id)
        if path is None:
            # Confirmed live: the exact remembered location_id can be
            # stranded on an unreachable island (duplicate-row tradeoff,
            # same root cause go_to's disambiguation fallback already
            # handles) even though a physically-identical duplicate room
            # is reachable. Try that before giving up.
            fallback = pathfind.find_reachable_duplicate(conn, current_id, return_id)
            if fallback is None:
                return "no discovered route back to the starting point from here."
            return_id, path = fallback
            # Confirmed live: the fallback can resolve to a same-name
            # duplicate that's actually zero hops away (current position
            # already matches it) -- same "Already back" case as the
            # exact-id check above, just reached via the duplicate path.
            if not path:
                return "Already back at the starting point."
        if len(path) > GO_TO_MAX_HOPS:
            return (f"route back is {len(path)} hops — too long to auto-walk "
                     f"(cap {GO_TO_MAX_HOPS}); needs manual travel.")

        taken = []
        result_text = ""
        for direction in path:
            try:
                result_text = send_cmd(p.move(direction))
            except ValueError as e:
                return f"stopped after {len(taken)}/{len(path)} hops ({', '.join(taken)}) — error: {e}"
            world.observe("move", {"direction": direction}, result_text)
            if world.move_failed(result_text):
                return (f"stopped after {len(taken)}/{len(path)} hops ({', '.join(taken)}) — "
                        f"{direction} failed: {result_text.strip()}")
            taken.append(direction)

        return f'Walked {len(taken)} rooms ({", ".join(taken)}) back to the starting point.\n\n{result_text}'

    def check_needs():
        # needs_management_plan: collapses the Week 2 "check each empty
        # water bottle" flailing into one deterministic sweep -- worst case
        # 3 MUD round-trips (score, fountain attempt, inventory) behind a
        # single LLM tool call, same value proposition as go_to.
        err = guard()
        if err:
            return err

        score_text = send_cmd(p.info_self("score"))
        lowered_score = score_text.lower()
        hungry = "you are hungry" in lowered_score
        thirsty = "you are thirsty" in lowered_score
        if not hungry and not thirsty:
            return "Not hungry or thirsty -- no action needed."

        notes = []

        if thirsty:
            # Free first move: no need to have detected a fountain in
            # advance, the MUD's own response tells us whether one exists
            # here (§2 -- "You drink the clear water." vs. not seeing one).
            fountain_result = send_cmd(p.consume("drink", "fountain"))
            if "you drink" in fountain_result.lower():
                thirsty = False
                notes.append(f"Drank from a fountain here: {fountain_result.strip()}")

        if hungry or thirsty:
            inv_text = send_cmd(p.info_self("inventory"))
            inv_lines = parser.parse_inventory(inv_text)
            have_food, have_drink = _match_inventory_to_needs(inv_lines)
            conn = world.connection()

            if hungry:
                if have_food:
                    notes.append(f'You are hungry and already have "{have_food}" -- consume it?')
                else:
                    notes.append(_supply_note(conn, "food", "hungry"))
            if thirsty:
                if have_drink:
                    notes.append(f'You are thirsty and already have "{have_drink}" -- consume it?')
                else:
                    notes.append(_supply_note(conn, "drink", "thirsty"))

        return "\n".join(notes)

    def flee():
        err = guard()
        if err:
            return err
        return send_cmd(p.flee())

    def set_position(position):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.set_position(position))
        except ValueError as e:
            return f"error: {e}"

    def track(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.track(target))
        except ValueError as e:
            return f"error: {e}"

    # ── Doors ───────────────────────────────────────────────────────────

    # Attempt to open a door and report whether the response indicates it's
    # locked. There is no separate "peek" command on the MUD — the only way
    # to learn a door's lock state is to try opening it — so this doubles as
    # the actual open attempt: if it turns out to be unlocked, it's now open.
    def _check_door_locked(target, direction):
        response = send_cmd(p.door("open", target, direction=direction))
        return bool(re.search(r"lock", str(response), re.IGNORECASE)), response

    # Heuristic for a failed unlock attempt (wrong/missing key, stuck lock,
    # etc.) versus a successful one (typically a terse "*Click*").
    def _unlock_failed(response):
        return bool(re.search(
            r"don'?t have|do not have|no key|won'?t (turn|budge)|can'?t seem|cannot seem",
            str(response), re.IGNORECASE))

    def check_door(target, direction=None):
        err = guard()
        if err:
            return err
        try:
            locked, response = _check_door_locked(target, direction)
            return f"{'locked' if locked else 'not locked'}: {response}"
        except ValueError as e:
            return f"error: {e}"

    def open_door(target, direction=None):
        err = guard()
        if err:
            return err
        try:
            locked, response = _check_door_locked(target, direction)
            if not locked:
                return response

            unlock_response = send_cmd(p.door("unlock", target, direction=direction))
            if _unlock_failed(unlock_response):
                return f"the door is locked and unable to be unlocked ({str(unlock_response).strip()})"
            return send_cmd(p.door("open", target, direction=direction))
        except ValueError as e:
            return f"error: {e}"

    # ── Combat ──────────────────────────────────────────────────────────

    def attack(target, style="kill"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.attack(style, target))
        except ValueError as e:
            return f"error: {e}"

    def skill_strike(skill, target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.skill_strike(skill, target))
        except ValueError as e:
            return f"error: {e}"

    def consider(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.consider(target))
        except ValueError as e:
            return f"error: {e}"

    # ── Communication ───────────────────────────────────────────────────

    def say(text, mode="say"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_local(mode, text))
        except ValueError as e:
            return f"error: {e}"

    def tell(target, text, mode="tell"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_targeted(mode, target, text))
        except ValueError as e:
            return f"error: {e}"

    def channel_say(channel, text):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_channel(channel, text))
        except ValueError as e:
            return f"error: {e}"

    # ── Inventory & equipment ────────────────────────────────────────────

    def get_item(item, container=None, count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.get(item, container=container, count=count))
        except ValueError as e:
            return f"error: {e}"

    def drop_item(item, mode="drop", count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.drop(mode, item, count=count))
        except ValueError as e:
            return f"error: {e}"

    def put_item(item, container, count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.put(item, container, count=count))
        except ValueError as e:
            return f"error: {e}"

    def equip_item(item, action, body_loc=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.equip(action, item, body_loc=body_loc))
        except ValueError as e:
            return f"error: {e}"

    def consume_item(item, mode="eat"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.consume(mode, item))
        except ValueError as e:
            return f"error: {e}"

    # ── Magic ────────────────────────────────────────────────────────────

    def cast_spell(spell, target=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.cast(spell, target=target))
        except ValueError as e:
            return f"error: {e}"

    def use_magic_item(item, mode, target_args=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.use_magic_item(mode, item, target_args=target_args))
        except ValueError as e:
            return f"error: {e}"

    # ── Utility ──────────────────────────────────────────────────────────

    def shop(action, args=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.shop(action, args=args))
        except ValueError as e:
            return f"error: {e}"

    def practice(skill=None):
        err = guard()
        if err:
            return err
        return send_cmd(p.practice(skill))

    def save_character():
        err = guard()
        if err:
            return err
        return send_cmd(p.save_char())

    def send_raw(command):
        err = guard()
        if err:
            return err
        session.send_command(command)
        return session.read_until_quiet()

    # ── Registration ───────────────────────────────────────────────────

    registry.tool("mud_connect",
        "Open the connection to the MUD server and log in with the configured character name "
        "and password. Safe to call when already connected (returns current status instead of "
        "reconnecting).",
        {}, mud_connect)
    registry.tool("mud_disconnect",
        "Close the connection to the MUD server gracefully.",
        {}, mud_disconnect)
    registry.tool("mud_status",
        "Return whether the MUD session is currently connected.",
        {}, mud_status)

    registry.tool("look",
        "Look at the current room or at a specific target. Call with NO arguments to describe "
        "the current room (do NOT pass target: 'room'). Pass a target to inspect a specific "
        "item, mob, or player (e.g. target: 'sword'). Use preposition 'in' to look inside a "
        "container, 'at' to inspect something, or a direction (north/east/south/west/up/down) "
        "to peek into an adjacent room.",
        {
            "target": {"type": "string", "description": "Item, mob, or player name to inspect. Omit entirely to describe the current room."},
            "preposition": {"type": "string", "description": "Preposition: in, at, north, east, south, west, up, down (optional)"},
        }, look)
    registry.tool("examine",
        "Examine a target in detail (more verbose than look).",
        {"target": {"type": "string", "description": "The item, mob, or player to examine"}}, examine)
    registry.tool("read",
        "Read text on a sign, book, letter, scroll, or other readable item.",
        {"target": {"type": "string", "description": "The sign, book, or other readable item to read"}}, read)
    registry.tool("check",
        "Query information about your character or surroundings. Kinds: score, inventory, "
        "equipment, gold, exits, time, weather, levels, wimpy, toggle, where.",
        {"kind": {"type": "string", "description": "What to check: score | inventory | equipment | gold | exits | time | weather | levels | wimpy | toggle | where"}}, check)

    registry.tool("move",
        "Move in a compass direction or up/down.",
        {"direction": {"type": "string", "description": "Direction: north | east | south | west | up | down"}}, move)
    registry.tool("go_to",
        "Walk directly to a known location using the mapped world database instead of issuing "
        "individual move commands. Pass a place name (e.g. 'weapon shop') or 'place in town' "
        "(e.g. 'weapon shop in midgaard'). Only works for places already discovered through "
        "play — if the exact place isn't mapped yet but its town is, this walks to the nearest "
        "known point in that town instead and explains that the rest needs manual exploring. "
        "Returns either the walk result or an explanation of why it couldn't route there.",
        {"destination": {"type": "string", "description": "Where to go, e.g. 'weapon shop', 'the temple', 'weapon shop in midgaard'"}}, go_to)
    registry.tool("return_to_start",
        "Walk back to the location you were at right before your most recent go_to call -- "
        "e.g. after visiting a shop or fountain to resolve hunger/thirst. Uses the same "
        "mapped-route walking as go_to. Fails if you haven't called go_to yet this session, "
        "or if no discovered route back exists.",
        {}, return_to_start)
    registry.tool("check_needs",
        "Check whether you're hungry or thirsty, and if so, try to resolve it: drinks straight "
        "from a fountain here for free if one exists, checks your inventory for something "
        "already on hand, and if nothing's available, looks up the nearest known place "
        "(from the mapped world database) that sells food or drink. Does not eat or drink "
        "anything from your inventory on its own -- it reports what's available so you can "
        "decide whether to consume it. Returns 'not hungry or thirsty' if neither applies.",
        {}, check_needs)
    registry.tool("flee",
        "Attempt to flee from combat in a random available direction.",
        {}, flee)
    registry.tool("set_position",
        "Change body position. Use 'rest' or 'sleep' between fights to recover HP and mana. "
        "Must be standing to move or fight.",
        {"position": {"type": "string", "description": "Position: stand | sit | rest | sleep | wake"}}, set_position)
    registry.tool("track",
        "Attempt to track a mob or player by name, revealing which direction they are in. "
        "Requires the Track skill.",
        {"target": {"type": "string", "description": "Name of the mob or player to track"}}, track)

    registry.tool("check_door",
        "Check whether a door or exit is locked, without forcing it open. This is the subtool "
        "open_door uses internally; call it directly if you only want to know the lock state. "
        "Note: if the door turns out to be unlocked, this check opens it as a side effect "
        "(there's no separate peek command on the MUD).",
        {
            "target": {"type": "string", "description": "Name of the door or exit (e.g. 'door', 'gate')"},
            "direction": {"type": "string", "description": "Direction the door is in (optional): north | east | south | west | up | down"},
        }, check_door)
    registry.tool("open_door",
        "Open a door or exit. Checks whether it's locked first; if it is, attempts to unlock "
        "it and then opens it. If it cannot be unlocked (e.g. no key), reports that the door "
        "is locked and unable to be unlocked.",
        {
            "target": {"type": "string", "description": "Name of the door or exit (e.g. 'door', 'gate')"},
            "direction": {"type": "string", "description": "Direction the door is in (optional): north | east | south | west | up | down"},
        }, open_door)

    registry.tool("attack",
        "Attack a target. Style 'kill' is the standard approach; 'murder' bypasses the mercy "
        "check; 'hit' is a one-off strike.",
        {
            "target": {"type": "string", "description": "Name of the mob or player to attack"},
            "style": {"type": "string", "description": "Attack style: kill | hit | murder (default: kill)"},
        }, attack)
    registry.tool("skill_strike",
        "Use a combat skill against a target.",
        {
            "skill": {"type": "string", "description": "Skill: bash | kick | backstab | rescue | assist"},
            "target": {"type": "string", "description": "Name of the mob or player"},
        }, skill_strike)
    registry.tool("consider",
        "Assess a mob's relative strength before engaging in combat. Returns a phrase such as "
        "'You could kill it easily' or 'Death awaits you'. Always consider before attacking an "
        "unknown mob.",
        {"target": {"type": "string", "description": "Name of the mob to consider"}}, consider)

    registry.tool("say",
        "Speak or emote in the current room.",
        {
            "text": {"type": "string", "description": "What to say or emote"},
            "mode": {"type": "string", "description": "Mode: say | emote | reply (default: say)"},
        }, say)
    registry.tool("tell",
        "Send a private message to a specific player.",
        {
            "target": {"type": "string", "description": "Player name to message"},
            "text": {"type": "string", "description": "The message"},
            "mode": {"type": "string", "description": "Mode: tell | whisper | ask (default: tell)"},
        }, tell)
    registry.tool("channel_say",
        "Broadcast a message over a global channel.",
        {
            "channel": {"type": "string", "description": "Channel: shout | gossip | auction | grats | holler"},
            "text": {"type": "string", "description": "The message to broadcast"},
        }, channel_say)

    registry.tool("get_item",
        "Pick up an item from the room or from a container.",
        {
            "item": {"type": "string", "description": "Name of the item to get"},
            "container": {"type": "string", "description": "Container to get it from (optional)"},
            "count": {"type": "integer", "description": "Number of items to get (optional)"},
        }, get_item)
    registry.tool("drop_item",
        "Drop, donate, or junk an item.",
        {
            "item": {"type": "string", "description": "Name of the item"},
            "mode": {"type": "string", "description": "Mode: drop | donate | junk (default: drop)"},
            "count": {"type": "integer", "description": "Number of items (optional)"},
        }, drop_item)
    registry.tool("put_item",
        "Put an item into a container.",
        {
            "item": {"type": "string", "description": "Name of the item to put"},
            "container": {"type": "string", "description": "Name of the container"},
            "count": {"type": "integer", "description": "Number of items (optional)"},
        }, put_item)
    registry.tool("equip_item",
        "Wear, wield, hold, grab, or remove an item.",
        {
            "item": {"type": "string", "description": "Name of the item"},
            "action": {"type": "string", "description": "Action: wear | wield | hold | grab | remove"},
            "body_loc": {"type": "string", "description": "Body location to wear on (optional, e.g. 'head', 'finger')"},
        }, equip_item)
    registry.tool("consume_item",
        "Eat, drink, taste, or sip a consumable item.",
        {
            "item": {"type": "string", "description": "Name of the item to consume"},
            "mode": {"type": "string", "description": "Mode: eat | drink | taste | sip (default: eat)"},
        }, consume_item)

    registry.tool("cast_spell",
        "Cast a spell, optionally at a target.",
        {
            "spell": {"type": "string", "description": "Full spell name (e.g. 'cure light wounds', 'magic missile')"},
            "target": {"type": "string", "description": "Target mob, player, or object (optional)"},
        }, cast_spell)
    registry.tool("use_magic_item",
        "Activate a magic item: quaff a potion, recite a scroll, or use a wand/staff.",
        {
            "item": {"type": "string", "description": "Name of the item to activate"},
            "mode": {"type": "string", "description": "Mode: quaff | recite | use"},
            "target_args": {"type": "string", "description": "Optional target arguments (e.g. mob name for a wand)"},
        }, use_magic_item)

    registry.tool("shop",
        "Interact with a shop NPC: list stock, buy, sell, or get the value of an item.",
        {
            "action": {"type": "string", "description": "Action: list | buy | sell | value | offer"},
            "args": {"type": "string", "description": "Item name or number (optional)"},
        }, shop)
    registry.tool("practice",
        "List your known skills at a guildmaster, or practice a specific skill.",
        {"skill": {"type": "string", "description": "Skill name to practice (omit to list all)"}}, practice)
    registry.tool("save_character",
        "Save your character to disk so progress is not lost on disconnect.",
        {}, save_character)
    registry.tool("send_raw",
        "Send an arbitrary command string to the MUD and return the response. Use this as an "
        "escape hatch when no structured tool fits.",
        {"command": {"type": "string", "description": "The raw command to send (e.g. 'who', 'help backstab')"}}, send_raw)

    # Auto-connect at startup so the session is ready immediately and the
    # agent doesn't need to waste a turn calling mud_connect first.
    try:
        session.open()
        session.login(name, password)
    except Session.Error as e:
        print(f"[boukensha] MUD auto-connect failed: {e} — call mud_connect manually", file=sys.stderr)
