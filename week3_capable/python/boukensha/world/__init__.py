import sys

from . import db as _db
from . import parser
from . import store

_conn = None

# Transient session state (§5, §8) -- not schema, reconstructable from the
# exits graph / next wield+attack, so it lives here as plain module state
# rather than a DB table.
_current_location_id = None
_current_weapon_id = None
_current_fight_mob_id = None
_current_fight_hits_landed = 0

_MOVE_FAILURE_RE = __import__("re").compile(
    r"alas, you (?:cannot|can'?t) go that way|nothing (?:that way|to that direction)"
    r"|too relaxed to do that",  # confirmed live: resting blocks movement with this phrase,
    # not the "cannot go that way" text -- without this alternation go_to/return_to_start
    # silently believed a resting-refused move had succeeded (needs_management_plan §9a
    # follow-up testing caught this).
    __import__("re").IGNORECASE,
)


def _connection():
    global _conn
    if _conn is None:
        _conn = _db.connect()
    return _conn


# ---------- public accessors (goto_tool_plan §6/§8: pathfind.py and the ----
# ---------- go_to tool need read access to the same pointer/connection ----
# ---------- this module already tracks internally) -------------------------

def connection():
    return _connection()


def current_location_id():
    return _current_location_id


def move_failed(result_text):
    """True if a `move` result indicates the hop didn't actually happen (bad
    direction / blocked) or the pointer just went stale (death/recall
    mid-walk) -- reuses the exact same grounded checks _observe_move already
    applies for write-back, so go_to's hop-by-hop loop (goto_tool_plan §6)
    stops on the same signals the DB itself trusts."""
    if parser.is_stale_pointer_signal(result_text):
        return True
    return bool(_MOVE_FAILURE_RE.search(parser.strip_ansi(result_text)))


def reset_session():
    """Clears in-memory pointer/fight state -- called on (re)connect, since
    a fresh session can't trust whatever the previous connection's pointer
    was."""
    global _current_location_id, _current_weapon_id
    global _current_fight_mob_id, _current_fight_hits_landed
    _current_location_id = None
    _current_weapon_id = None
    _current_fight_mob_id = None
    _current_fight_hits_landed = 0


def observe(name, args, result):
    """The Registry.dispatch() hook point (plan §6a). Pattern-matches on
    tool name; no-op for tools it doesn't recognize. Never raises -- a
    parsing bug here is a missed observation, not a reason to break the
    agent's turn (same philosophy as agent.py's own tool-error handling)."""
    args = args or {}
    text = "" if result is None else str(result)

    try:
        if name == "mud_connect":
            reset_session()
        elif name == "look":
            # Deliberately not gated on args.get("target") being empty: the
            # tool's own docstring tells the model not to pass target:
            # "room"/"here", but it doesn't always comply (confirmed live --
            # the model called look(target="room", ...) and look(target=
            # "here", ...) in one run, which would've silently skipped room
            # observation entirely if gated on args). parse_room() already
            # returns None for anything that isn't shaped like a room
            # response (no exits line) -- that's the correct discriminator,
            # not the tool's own arguments.
            _observe_room(text)
        elif name == "check" and args.get("kind") == "exits":
            _observe_exits(text)
        elif name == "move":
            _observe_move(args, text)
        elif name == "get_item":
            _observe_pickup(args, text)
        elif name == "equip_item" and args.get("action") == "wield":
            _observe_wield(text)
        elif name in ("attack", "skill_strike"):
            _observe_combat(name, args, text)
        elif name == "consider":
            _observe_consider(args, text)
        elif name == "shop" and args.get("action") == "list":
            _observe_shop(text)
        elif name == "cast_spell":
            _observe_spell_identity_only(args)
        elif name == "use_magic_item":
            _observe_magic_item_identity_only(args)
    except Exception as e:  # pragma: no cover -- write-back must never break the turn
        print(f"warning: world.observe({name!r}) failed: {e}", file=sys.stderr)


# ---------- rooms / exits / movement (§5) -----------------------------------

def _apply_zone(conn, location_id, name, description):
    """goto_tool_plan §5: if this room's own text names a known town and the
    room isn't already zoned, tag it and flood-fill that zone outward
    through the exits graph. No-ops (cheaply) once a room already has a
    zone_name, whether from a prior seed or a prior propagation."""
    if store.get_zone_name(conn, location_id) is not None:
        return
    zone = parser.detect_seed_zone(name, description)
    if zone:
        store.propagate_zone(conn, location_id, zone)


def _link_room_exits(conn, location_id, exit_directions, destination_names=None):
    """Shared by _observe_room (letters only) and _observe_exits (full
    names) -- for each direction not already scanned from this location,
    create a placeholder destination and the exits row (§5)."""
    destination_names = destination_names or {}
    for direction in exit_directions:
        if store.get_exit(conn, location_id, direction) is not None:
            continue
        dest_name = destination_names.get(direction)
        dest_id = store.get_or_create_location(conn, name=dest_name, visited=False)
        store.get_or_create_exit(conn, location_id, direction, dest_id)


def _observe_room(text):
    global _current_location_id
    parsed = parser.parse_room(text)
    if parsed is None:
        return
    conn = _connection()

    if _current_location_id is None:
        # Text-matching fallback (§5): session start, or pointer went stale.
        _current_location_id = store.get_or_create_location(
            conn, name=parsed.name, description=parsed.description, visited=True,
        )
    else:
        store.touch_location(
            conn, _current_location_id,
            name=parsed.name, description=parsed.description, visited=True,
        )

    _link_room_exits(conn, _current_location_id, parsed.exit_directions)
    _link_mob_lines(conn, _current_location_id, parsed.mob_lines)
    _apply_zone(conn, _current_location_id, parsed.name, parsed.description)


def _observe_exits(text):
    if _current_location_id is None:
        return
    conn = _connection()
    exits = parser.parse_exits(text)
    if not exits:
        return
    _link_room_exits(conn, _current_location_id, list(exits.keys()), destination_names=exits)
    # check("exits") gives real destination names -- backfill any
    # already-scanned placeholder that's still nameless (§5), and give it a
    # zone-detection pass too: a placeholder can carry an anchor name (e.g.
    # "Inside The East Gate Of Midgaard") before it's ever been visited.
    for direction, dest_name in exits.items():
        dest_id = store.get_exit(conn, _current_location_id, direction)
        if dest_id is not None:
            store.touch_location(conn, dest_id, name=dest_name)
            _apply_zone(conn, dest_id, dest_name, None)


def _observe_move(args, text):
    global _current_location_id

    if parser.is_stale_pointer_signal(text):
        _current_location_id = None
        return
    if _MOVE_FAILURE_RE.search(parser.strip_ansi(text)):
        return  # didn't actually move -- pointer unchanged

    direction = args.get("direction")
    if not direction:
        _current_location_id = None
        return

    if _current_location_id is None:
        # Pointer was never established or went stale, but this move's own
        # result usually auto-echoes the destination room in full -- the
        # same text shape a `look` would produce (confirmed live: every
        # `move` in a session where an earlier `look(target=...)` had
        # failed still returned a complete room description). Treat it
        # exactly like a fresh room observation (text-matching fallback,
        # §5) instead of silently discarding it -- we don't know the
        # *origin* here, so we can't backfill an origin->destination exits
        # row, but the destination itself still gets recorded.
        _observe_room(text)
        return

    conn = _connection()
    known_dest = store.get_exit(conn, _current_location_id, direction)
    parsed_room = parser.parse_room(text)  # `move` usually auto-echoes the new room

    if known_dest is not None:
        # Known by graph position, full stop -- no text matching needed (§5).
        _current_location_id = known_dest
        store.touch_location(conn, _current_location_id, visited=True)
        if parsed_room:
            store.touch_location(
                conn, _current_location_id,
                name=parsed_room.name, description=parsed_room.description,
            )
            _link_room_exits(conn, _current_location_id, parsed_room.exit_directions)
            _link_mob_lines(conn, _current_location_id, parsed_room.mob_lines)
            _apply_zone(conn, _current_location_id, parsed_room.name, parsed_room.description)
        return

    # Unscanned exit -- text-matching fallback, then backfill the exits row.
    origin_id = _current_location_id
    if parsed_room:
        _current_location_id = store.get_or_create_location(
            conn, name=parsed_room.name, description=parsed_room.description, visited=True,
        )
        store.get_or_create_exit(conn, origin_id, direction, _current_location_id)
        _link_room_exits(conn, _current_location_id, parsed_room.exit_directions)
        _link_mob_lines(conn, _current_location_id, parsed_room.mob_lines)
        _apply_zone(conn, _current_location_id, parsed_room.name, parsed_room.description)
    else:
        # Moved, but this result didn't parse as a room -- pointer unknown
        # until the next successful room observation.
        _current_location_id = None


# ---------- mobs seen in a room (best-effort, per §4) -----------------------

# §4: mob-presence lines during `look` are free-form sentences in the same
# color code as the room title, with no delimiter other than position and a
# loose "proper-noun + verb" shape -- explicitly flagged there as
# best-effort, not a reliable parse. This extracts a leading capitalized
# phrase as the mob's name; anything that doesn't match that shape is
# skipped rather than guessed at.
_MOB_LINE_NAME_RE = __import__("re").compile(r"^([A-Z][a-zA-Z' ]*?)(?:,| (?:walks|sits|stands|is|paces|inspects))")
# Confirmed live (first verification run): plain item/scenery description
# lines ("There is a long, black stick lying here.") also match the shape
# above, since "There" is capitalized and followed by "is" -- this is
# exactly the false-positive risk §4 already flagged. Excluding narrative
# sentence-starters that are never how CircleMUD refers to a mob cuts that
# specific false positive. NOT excluding "a"/"an"/"the" here -- those are
# legitimate, common leading words for generic (unnamed) mobs ("A dwarven
# mining worker", confirmed correctly captured this way in the same live
# run) -- excluding them would silently drop real mob sightings.
_MOB_LINE_STOPWORDS = {"there", "it", "you", "this", "these", "those"}


def _link_mob_lines(conn, location_id, mob_lines):
    for line in mob_lines:
        m = _MOB_LINE_NAME_RE.match(line)
        if not m or m.group(1).strip().split()[0].lower() in _MOB_LINE_STOPWORDS:
            continue
        mob_id = store.get_or_create_mob(conn, m.group(1).strip())
        store.link_mob(conn, location_id, mob_id)


# ---------- item pickups -----------------------------------------------------

def _observe_pickup(args, text):
    if _current_location_id is None:
        return
    parsed = parser.parse_pickup(text, item_arg=args.get("item"))
    if parsed is None:
        return
    conn = _connection()
    item_id = store.get_or_create_item(conn, parsed.item_name, item_type=parsed.item_type)
    store.link_item(conn, _current_location_id, item_id, quantity=parsed.quantity)


# ---------- wield / current weapon (§8) -------------------------------------

def _observe_wield(text):
    global _current_weapon_id
    weapon_name = parser.parse_wield(text)
    if weapon_name is None:
        return
    _current_weapon_id = store.get_or_create_weapon(_connection(), weapon_name)


# ---------- combat (§8) ------------------------------------------------------

def _resolve_combat_weapon_id(conn, tool_name, args):
    if tool_name == "skill_strike":
        # Own identity from args, always its own row -- never merged with
        # "fists" or whatever's wielded (decision #7).
        skill = args.get("skill") or "unknown_skill"
        return store.get_or_create_weapon(conn, skill)
    # tool_name == "attack"
    if _current_weapon_id is not None:
        return _current_weapon_id
    return store.get_or_create_weapon(conn, "fists")


def _observe_combat(tool_name, args, text):
    global _current_fight_mob_id, _current_fight_hits_landed

    target_name = args.get("target")
    if not target_name:
        return
    parsed = parser.parse_combat_result(text)
    if parsed.landed is None and not parsed.killed:
        return  # couldn't classify this result at all -- don't guess

    conn = _connection()
    mob_id = store.get_or_create_mob(conn, target_name, disposition="enemy")
    weapon_id = _resolve_combat_weapon_id(conn, tool_name, args)

    if mob_id != _current_fight_mob_id:
        _current_fight_mob_id = mob_id
        _current_fight_hits_landed = 0

    if parsed.landed:
        store.record_attack(conn, mob_id, weapon_id, landed=True)
        _current_fight_hits_landed += 1

    if parsed.killed:
        store.record_kill(conn, mob_id, weapon_id)
        _current_fight_mob_id = None
        _current_fight_hits_landed = 0


# ---------- consider (qualitative condition, §3/§8 cold-start fallback) ----

def _observe_consider(args, text):
    if _current_location_id is None:
        return
    target_name = args.get("target")
    if not target_name:
        return
    condition = parser.parse_condition(text)
    if condition is None:
        return
    conn = _connection()
    mob_id = store.get_or_create_mob(conn, target_name)
    store.link_mob(conn, _current_location_id, mob_id, condition=condition)


# ---------- shop stock (needs_management_plan §4) ---------------------------

def _observe_shop(text):
    if _current_location_id is None:
        return
    conn = _connection()
    for item_name in parser.parse_shop_stock(text):
        item_type = parser.classify_consumable(item_name)
        item_id = store.get_or_create_item(conn, item_name, item_type=item_type)
        # Shop stock is "Unlimited" in practice -- quantity isn't a
        # meaningful count here the way a gold pile's "There were 50
        # coins." is, so this deliberately passes quantity=None rather
        # than inventing a number. Contrast with _observe_pickup, where
        # quantity IS a real observed value.
        store.link_item(conn, _current_location_id, item_id, quantity=None)


# ---------- spells / magic items (decision #8 -- identity only for now) ----

def _observe_spell_identity_only(args):
    spell = args.get("spell")
    if spell:
        store.get_or_create_weapon(_connection(), spell)


def _observe_magic_item_identity_only(args):
    item = args.get("item")
    if item:
        store.get_or_create_weapon(_connection(), item)
