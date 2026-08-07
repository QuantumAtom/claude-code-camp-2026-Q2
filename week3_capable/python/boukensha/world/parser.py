import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------- shared building blocks ------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Every response ends in the player's own status bar -- a reliable
# end-of-response delimiter, grounded in plan §4.
_STATUS_BAR_RE = re.compile(r"\d+H\s+\d+M\s+\d+V\s*\([^)]*\)\s*>\s*$")

_DIRECTION_LETTERS = {"n": "north", "s": "south", "e": "east", "w": "west", "u": "up", "d": "down"}

_STALE_POINTER_PHRASES = (
    "you have been killed",
    "you suddenly feel a wrenching sensation",
)


def strip_ansi(text):
    return _ANSI_RE.sub("", text or "")


def _lines(text):
    """ANSI-stripped, status-bar-trimmed, blank-line-free lines."""
    text = strip_ansi(text)
    text = _STATUS_BAR_RE.sub("", text)
    return [ln.strip() for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


def is_stale_pointer_signal(raw_text):
    """§5: death/recall/teleport -- the graph pointer can no longer be
    trusted, next room observation must fall back to text-matching."""
    text = strip_ansi(raw_text).lower()
    return any(phrase in text for phrase in _STALE_POINTER_PHRASES)


# ---------- rooms (look / move's auto room-echo) ----------------------------

_EXITS_LINE_RE = re.compile(r"\[\s*Exits?:\s*([a-z\s]*)\]", re.IGNORECASE)


@dataclass
class ParsedRoom:
    name: str
    description: str
    exit_directions: List[str] = field(default_factory=list)
    mob_lines: List[str] = field(default_factory=list)


def parse_room(raw_text):
    """Parses a `look`-shaped response: title, description, the compact
    `[ Exits: n s w ]` line (letters only, no destination names -- see
    parse_exits for the fuller `check("exits")` form), and whatever's left
    as candidate mob-presence lines. Returns None if this doesn't look like
    a room description at all (no exits line found) -- e.g. it's an
    `examine`/`consider` response instead, not a room."""
    lines = _lines(raw_text)
    exits_idx, exits_match = None, None
    for i, ln in enumerate(lines):
        m = _EXITS_LINE_RE.search(ln)
        if m:
            exits_idx, exits_match = i, m
            break
    if exits_idx is None or exits_idx == 0 or exits_match is None:
        return None
    letters = exits_match.group(1).split()
    exit_directions = [_DIRECTION_LETTERS.get(letter.lower(), letter.lower()) for letter in letters]
    return ParsedRoom(
        name=lines[0],
        description=" ".join(lines[1:exits_idx]).strip(),
        exit_directions=exit_directions,
        mob_lines=lines[exits_idx + 1:],
    )


# ---------- exits (check("exits")) ------------------------------------------

_EXIT_ENTRY_RE = re.compile(r"^(north|south|east|west|up|down)\s*-\s*(.+)$", re.IGNORECASE)


def parse_exits(raw_text):
    """`check("exits")` gives full direction words *and* the destination
    room's name -- strictly more useful than look's letter-only line (§4).
    Returns {direction: destination_name}, or {} if nothing matched."""
    result = {}
    for line in _lines(raw_text):
        m = _EXIT_ENTRY_RE.match(line)
        if m:
            result[m.group(1).lower()] = m.group(2).strip()
    return result


# ---------- item pickups (get_item) -----------------------------------------

@dataclass
class ParsedPickup:
    item_name: str
    quantity: Optional[int] = None
    item_type: Optional[str] = None


_GOLD_QUANTITY_RE = re.compile(r"There were (\d+) coins?\.", re.IGNORECASE)
_GET_FAILURE_RE = re.compile(r"you (?:can'?t find|don'?t see|do not see)", re.IGNORECASE)


def parse_pickup(raw_text, *, item_arg=None):
    """Gold gives an exact, reliably-parseable quantity (§4's grounded
    example) -- everything else falls back to the tool call's own `item`
    argument for identity, since a generic 'you get the X' isn't
    consistently phrased across item types the way the gold message is."""
    text = strip_ansi(raw_text)
    if _GET_FAILURE_RE.search(text):
        return None
    gold_m = _GOLD_QUANTITY_RE.search(text)
    if gold_m:
        return ParsedPickup(item_name="gold", quantity=int(gold_m.group(1)), item_type="gold")
    if re.search(r"^You get ", text, re.MULTILINE) and item_arg:
        return ParsedPickup(item_name=item_arg, quantity=None)
    return None


# ---------- equip / wield ----------------------------------------------------

_WIELD_RE = re.compile(r"[Yy]ou wield (?:a|an|)\s*(.+?) in your", re.IGNORECASE)


def parse_wield(raw_text):
    """Grounded directly in §4: 'You wield a short sword in your right
    hand.' Returns the weapon name, or None if this result wasn't a
    successful wield (e.g. 'You don't have that item.')."""
    m = _WIELD_RE.search(strip_ansi(raw_text))
    return m.group(1).strip() if m else None


# ---------- melee combat (attack / skill_strike) ----------------------------

@dataclass
class ParsedCombatResult:
    landed: Optional[bool]   # None if this result can't be confidently classified
    killed: bool


_KILL_RE = re.compile(r"is dead!\s*R\.I\.P\.", re.IGNORECASE)
_MISS_RE = re.compile(r"(the air instead|you miss|misses you|dodge|parr(?:y|ies)|block(?:s)?)", re.IGNORECASE)
# Anchored to the very start of the response (no re.MULTILINE) on purpose:
# in every sampled case (§4) the outcome of the player's own swing is the
# opening line, not a later status line -- matching only there avoids a
# false "landed" from an unrelated later "You ..." line (a proc message,
# a status effect, etc.).
_LANDED_RE = re.compile(r"^\x1b\[[0-9;]*mYou |^You ", re.IGNORECASE)


def parse_combat_result(raw_text):
    """Grounded in §4's four melee samples (landed, missed, kill, and the
    fact that a kill is its own unambiguous message). Landed-vs-missed
    beyond those exact samples is a heuristic (checking for known miss
    phrasing vs. an outgoing 'You ...' line) -- CircleMUD has many more
    combat message variants than the handful sampled so far; treat this as
    provisional and expand it as more real combat text gets collected
    (plan §8's grounding-gap note)."""
    text = strip_ansi(raw_text)
    killed = bool(_KILL_RE.search(text))
    if _MISS_RE.search(text):
        return ParsedCombatResult(landed=False, killed=killed)
    if _LANDED_RE.search(text) or killed:
        return ParsedCombatResult(landed=True, killed=killed)
    return ParsedCombatResult(landed=None, killed=killed)


# ---------- consider (qualitative mob condition, §3's 7-bucket ladder) -----

# Best-effort mapping to stock CircleMUD's condition-ladder phrasing (the
# same seven buckets the schema's CHECK constraint encodes) -- not directly
# grounded in a sampled `consider` transcript the way melee combat is
# (§4 only shows one condition-reading example), so treat this table as
# provisional pending more real samples, same caveat as parse_combat_result.
_CONDITION_PHRASES = (
    (re.compile(r"excellent condition", re.IGNORECASE), "excellent"),
    (re.compile(r"a few scratches", re.IGNORECASE), "scratches"),
    (re.compile(r"some small wounds", re.IGNORECASE), "small_wounds"),
    (re.compile(r"quite a few wounds", re.IGNORECASE), "quite_a_few_wounds"),
    (re.compile(r"big nasty wounds|some big wounds", re.IGNORECASE), "big_wounds"),
    (re.compile(r"pretty hurt", re.IGNORECASE), "pretty_hurt"),
    (re.compile(r"awful condition|about to die", re.IGNORECASE), "awful"),
)


def parse_condition(raw_text):
    text = strip_ansi(raw_text)
    for pattern, bucket in _CONDITION_PHRASES:
        if pattern.search(text):
            return bucket
    return None


# ---------- shop stock (needs_management_plan §4) ---------------------------
# shop("list") is free (no gold, no inventory change) and reveals the whole
# stock in one tabular response -- grounded directly against real
# session-log samples (needs_management_plan §2). shop("buy") is
# deliberately NOT parsed for item identity: CircleMUD's purchase
# confirmation only echoes the generic base name ("You now have a bottle.")
# even when the shop's own listing distinguishes several different bottled
# drinks ("A bottle of ale" vs "A bottle of firebreather") -- trusting that
# text would silently collapse distinct items into one row. `list` is
# strictly more specific and it's free, so only it feeds the DB.
_SHOP_LINE_RE = re.compile(r"^\s*\d+\)\s+\S+\s+(.+?)\s+\d+\s*$", re.MULTILINE)
_LEADING_ARTICLE_RE = re.compile(r"^(?:a|an)\s+", re.IGNORECASE)


def parse_shop_stock(raw_text):
    text = strip_ansi(raw_text)
    return [_LEADING_ARTICLE_RE.sub("", name).strip() for name in _SHOP_LINE_RE.findall(text)]


# ---------- consumable classification (needs_management_plan §4/§5) --------
# Best-effort keyword classifier, same "provisional, ground it further as
# more shops get sampled" caveat as _CONDITION_PHRASES above. Grounded
# against real shop listings: "danish pastry"/"bread"/"waybread" -> food;
# "bottle of X"/"barrel of X" -> drink; "cashcard"/"box"/"bag"/"lantern"/
# "torch" -> correctly unclassified, not guessed.
_FOOD_KEYWORDS = ("bread", "pastry", "cake", "pie", "meat", "fruit", "cheese")
_DRINK_KEYWORDS = ("bottle", "barrel", "water", "ale", "beer", "wine", "juice")


def classify_consumable(name):
    lowered = (name or "").lower()
    if any(k in lowered for k in _FOOD_KEYWORDS):
        return "food"
    if any(k in lowered for k in _DRINK_KEYWORDS):
        return "drink"
    return None  # e.g. "a cashcard", "a box", "a lantern" -- correctly unclassified, not guessed


# ---------- inventory (check("inventory")) ----------------------------------
# Grounded in a real transcript: "You are carrying:\r\na bottle\r\n...".


def parse_inventory(raw_text):
    """Returns [] for "You are carrying nothing." (or anything that doesn't
    start with the expected header) rather than guessing."""
    ls = _lines(raw_text)
    if not ls or not ls[0].lower().startswith("you are carrying"):
        return []
    return ls[1:]


# ---------- doors (check_door / open_door) -----------------------------------
# tools/mud.py's own return value already prefixes "locked: "/"not locked: "
# ahead of the raw server text (see boukensha/tools/mud.py's
# _check_door_locked) -- a reliable signal from the tool's own code, not
# something parsed out of prose.

def parse_door_lock_state(raw_text):
    text = strip_ansi(raw_text)
    if text.startswith("locked:"):
        return True
    if text.startswith("not locked:"):
        return False
    return None


# ---------- spells / magic items ---------------------------------------------
# Decision #8: identity resolution (spell/item name from the tool call's
# own args) is safe to use now -- see world/__init__.py, which reads
# args["spell"]/args["item"] directly rather than calling into this parser.
# There is deliberately no parse_spell_result()/parse_magic_item_result()
# here yet: no mage/spellcasting-class account exists on this MUD to sample
# real cast_spell/use_magic_item output from (plan §8's grounding-gap note,
# discussed and confirmed in the plan's decision #8). Add it here, following
# the same "ground it in real text first" method as everything else in this
# module, once that account exists.


# ---------- zone/town identity (goto_tool_plan §5) ----------------------------
# Deliberately NOT a general "extract the place name from this text" parser:
# checked real session-log room text and most in-town rooms ("The Bakery",
# "The General Store", "The Grunting Boar") never mention the town's name in
# either their title or description at all -- only a handful of "anchor"
# rooms do (gate rooms, Market Square, the Great Field). A small known-name
# list matched against those anchors, same pattern as _STALE_POINTER_PHRASES
# above -- add to this tuple as new towns get sampled from real play; the
# actual reach into every other room is world/store.py's propagate_zone()
# flood-fill, not this function.
_KNOWN_ZONE_NAMES = ("Midgaard",)
_ZONE_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(z) for z in _KNOWN_ZONE_NAMES) + r")\b", re.IGNORECASE
)


def detect_seed_zone(name, description):
    """Returns the canonical zone name if this room's own title/description
    explicitly names a known town, else None."""
    text = f"{name or ''} {description or ''}"
    m = _ZONE_NAME_RE.search(text)
    if not m:
        return None
    matched = m.group(1).lower()
    for canonical in _KNOWN_ZONE_NAMES:
        if canonical.lower() == matched:
            return canonical
    return None  # pragma: no cover -- unreachable, every regex alternative maps back to a canonical entry
