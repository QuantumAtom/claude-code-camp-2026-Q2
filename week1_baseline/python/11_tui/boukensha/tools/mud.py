import sys
from pathlib import Path

# mud_manager isn't a pip-installed package — it's a sibling local library
# at week0_explore/mud_manager/python/, mirroring how the Ruby gem lives at
# week0_explore/mud_manager/ and is pulled in via a Gemfile path dependency.
_MUD_MANAGER_DIR = Path(__file__).resolve().parents[5] / "week0_explore" / "mud_manager" / "python"
if str(_MUD_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(_MUD_MANAGER_DIR))

from mud_manager.session import Session
from mud_manager import primitives as p


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
    registry.tool("check",
        "Query information about your character or surroundings. Kinds: score, inventory, "
        "equipment, gold, exits, time, weather, levels, wimpy, toggle, where.",
        {"kind": {"type": "string", "description": "What to check: score | inventory | equipment | gold | exits | time | weather | levels | wimpy | toggle | where"}}, check)

    registry.tool("move",
        "Move in a compass direction or up/down.",
        {"direction": {"type": "string", "description": "Direction: north | east | south | west | up | down"}}, move)
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
