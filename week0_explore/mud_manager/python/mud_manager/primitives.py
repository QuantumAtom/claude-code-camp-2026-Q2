"""Stateless generic primitives over the CircleMUD player-facing command
surface. Each function validates its enum-typed arguments and returns a
Command describing the line to send to the MUD. Runtime preconditions
(position, skill availability, flags, room state, equipment requirements,
etc.) are intentionally NOT checked here — they require live game state and
belong to the tool layer that wraps these primitives as agent tool calls.
"""

from dataclasses import dataclass, field


@dataclass
class Command:
    primitive: str
    verb: str
    raw: str
    args: dict = field(default_factory=dict)

    def __str__(self):
        return self.raw


DIRECTIONS = ["north", "east", "south", "west", "up", "down"]
POSITIONS = ["stand", "sit", "rest", "sleep", "wake"]
ATTACK_STYLES = ["hit", "murder", "kill"]
STRIKE_SKILLS = ["backstab", "bash", "kick", "rescue", "assist"]
LOCAL_SAY = ["say", "emote", "reply"]
TARGETED_SAY = ["tell", "whisper", "ask"]
CHANNELS = ["shout", "gossip", "auction", "grats", "holler"]
REPORT_KINDS = ["bug", "typo", "idea"]
DROP_MODES = ["drop", "donate", "junk"]
EQUIP_OPS = ["wear", "wield", "grab", "hold", "remove"]
CONSUME_MODES = ["eat", "taste", "drink", "sip"]
LIQUID_MODES = ["pour", "fill"]
DOOR_VERBS = ["open", "close", "lock", "unlock", "pick"]
LOOK_MODES = ["look", "read"]
LOOK_PREPS = ["in", "at", "north", "east", "south", "west", "up", "down"]
INFO_SELF = ["score", "inventory", "equipment", "gold", "exits", "time", "weather",
             "levels", "wimpy", "toggle", "where"]
INFO_WORLD = ["who", "users", "help", "credits", "news", "info", "motd", "policies",
              "version", "wizlist", "immlist", "clear", "whoami"]
LIST_KINDS = ["commands", "socials"]
COLOR_LEVELS = ["off", "sparse", "normal", "complete"]
PREF_FLAGS = ["autoexit", "brief", "compact", "noauction", "nogossip", "nograts",
              "norepeat", "noshout", "nosummon", "notell", "quest"]
STEALTH_MODES = ["hide", "sneak", "visible"]
SPELL_ITEM = ["use", "quaff", "recite"]
GROUP_OPS = ["group", "ungroup"]
SHOP_OPS = ["buy", "sell", "list", "value", "offer"]
BANK_OPS = ["balance", "deposit", "withdraw"]
MAIL_OPS = ["mail", "receive", "check"]


def _cmd(primitive, verb, raw, **args):
    return Command(primitive=primitive, verb=verb, raw=raw, args=args)


def _check_enum(value, allowed, name):
    v = str(value).lower()
    if v not in allowed:
        raise ValueError(f"invalid {name}: {value!r} (expected one of {', '.join(allowed)})")
    return v


def _require_str(value, name):
    if value is None or not str(value).strip():
        raise ValueError(f"{name} is required")


# ---------- Movement & posture ----------

def move(direction):
    verb = _check_enum(direction, DIRECTIONS, "direction")
    return _cmd("move", verb, verb)


def enter(keyword=None):
    raw = f"enter {keyword}" if keyword else "enter"
    return _cmd("enter", "enter", raw, target=keyword)


def leave():
    return _cmd("leave", "leave", "leave")


def set_position(pos):
    verb = _check_enum(pos, POSITIONS, "pos")
    return _cmd("set_position", verb, verb)


def follow(leader=None):
    raw = f"follow {leader}" if leader else "follow"
    return _cmd("follow", "follow", raw, leader=leader)


def flee():
    return _cmd("flee", "flee", "flee")


def track(victim):
    _require_str(victim, "victim")
    return _cmd("track", "track", f"track {victim}", victim=victim)


# ---------- Combat ----------

def attack(style, target):
    verb = _check_enum(style, ATTACK_STYLES, "style")
    _require_str(target, "target")
    return _cmd("attack", verb, f"{verb} {target}", target=target)


def skill_strike(skill, target):
    verb = _check_enum(skill, STRIKE_SKILLS, "skill")
    _require_str(target, "target")
    return _cmd("skill_strike", verb, f"{verb} {target}", target=target)


def order(who, command):
    _require_str(who, "who")
    _require_str(command, "command")
    return _cmd("order", "order", f"order {who} {command}", who=who, command=command)


def insult(target):
    _require_str(target, "target")
    return _cmd("insult", "insult", f"insult {target}", target=target)


# ---------- Communication ----------

def say_local(mode, text):
    verb = _check_enum(mode, LOCAL_SAY, "mode")
    _require_str(text, "text")
    return _cmd("say_local", verb, f"{verb} {text}", text=text)


def say_targeted(mode, target, text):
    verb = _check_enum(mode, TARGETED_SAY, "mode")
    _require_str(target, "target")
    _require_str(text, "text")
    return _cmd("say_targeted", verb, f"{verb} {target} {text}", target=target, text=text)


def say_channel(channel, text):
    verb = _check_enum(channel, CHANNELS, "channel")
    _require_str(text, "text")
    return _cmd("say_channel", verb, f"{verb} {text}", text=text)


def say_group(text):
    _require_str(text, "text")
    return _cmd("say_group", "gsay", f"gsay {text}", text=text)


def say_quest(text):
    _require_str(text, "text")
    return _cmd("say_quest", "qsay", f"qsay {text}", text=text)


def report_player(kind, text):
    verb = _check_enum(kind, REPORT_KINDS, "kind")
    _require_str(text, "text")
    return _cmd("report_player", verb, f"{verb} {text}", text=text)


def write_note(paper, pen=None):
    _require_str(paper, "paper")
    raw = f"write {paper} {pen}" if pen else f"write {paper}"
    return _cmd("write_note", "write", raw, paper=paper, pen=pen)


# ---------- Inventory & objects ----------

def get(obj, container=None, count=None):
    _require_str(obj, "obj")
    parts = ["get"]
    if count:
        parts.append(str(count))
    parts.append(obj)
    if container:
        parts.append(container)
    return _cmd("get", "get", " ".join(parts), obj=obj, container=container, count=count)


def drop(mode, obj, count=None):
    verb = _check_enum(mode, DROP_MODES, "mode")
    _require_str(obj, "obj")
    parts = [verb]
    if count:
        parts.append(str(count))
    parts.append(obj)
    return _cmd("drop", verb, " ".join(parts), obj=obj, count=count)


def put(obj, container, count=None):
    _require_str(obj, "obj")
    _require_str(container, "container")
    parts = ["put"]
    if count:
        parts.append(str(count))
    parts.extend([obj, container])
    return _cmd("put", "put", " ".join(parts), obj=obj, container=container, count=count)


def give(obj, target, count=None):
    _require_str(obj, "obj")
    _require_str(target, "target")
    parts = ["give"]
    if count:
        parts.append(str(count))
    parts.extend([obj, target])
    return _cmd("give", "give", " ".join(parts), obj=obj, target=target, count=count)


def equip(slot_op, obj, body_loc=None):
    verb = _check_enum(slot_op, EQUIP_OPS, "slot_op")
    _require_str(obj, "obj")
    raw = f"{verb} {obj} {body_loc}" if body_loc else f"{verb} {obj}"
    return _cmd("equip", verb, raw, obj=obj, body_loc=body_loc)


def consume(mode, obj):
    verb = _check_enum(mode, CONSUME_MODES, "mode")
    _require_str(obj, "obj")
    return _cmd("consume", verb, f"{verb} {obj}", obj=obj)


def transfer_liquid(mode, from_, to):
    # Ruby's keyword is `from:` — a reserved word in Python, so the
    # parameter is `from_`, but the Command's args dict keeps the literal
    # key "from" to preserve exact field naming for anything inspecting
    # `.args`.
    verb = _check_enum(mode, LIQUID_MODES, "mode")
    _require_str(from_, "from")
    _require_str(to, "to")
    raw = f"pour {from_} {to}" if verb == "pour" else f"fill {to} {from_}"
    return _cmd("transfer_liquid", verb, raw, **{"from": from_, "to": to})


def split_gold(amount):
    if not isinstance(amount, int) or amount <= 0:
        raise ValueError("amount must be a positive integer")
    return _cmd("split_gold", "split", f"split {amount}", amount=amount)


# ---------- Doors ----------

def door(verb, target, direction=None):
    if direction is not None and not str(direction).strip():
        direction = None
    v = _check_enum(verb, DOOR_VERBS, "verb")
    _require_str(target, "target")
    if direction:
        _check_enum(direction, DIRECTIONS, "direction")
    raw = f"{v} {target} {direction}" if direction else f"{v} {target}"
    return _cmd("door", v, raw, target=target, direction=direction)


# ---------- Perception & info ----------

def look(mode="look", target=None, preposition=None):
    if target is not None and not str(target).strip():
        target = None
    if preposition is not None and not str(preposition).strip():
        preposition = None
    verb = _check_enum(mode, LOOK_MODES, "mode")
    if preposition:
        _check_enum(preposition, LOOK_PREPS, "preposition")
    parts = [verb]
    if preposition:
        parts.append(preposition)
    if target:
        parts.append(target)
    return _cmd("look", verb, " ".join(parts), target=target, preposition=preposition)


def examine(target):
    _require_str(target, "target")
    return _cmd("examine", "examine", f"examine {target}", target=target)


def info_self(kind):
    verb = _check_enum(kind, INFO_SELF, "kind")
    return _cmd("info_self", verb, verb)


def info_world(kind, filter=None):
    verb = _check_enum(kind, INFO_WORLD, "kind")
    raw = f"{verb} {filter}" if filter else verb
    return _cmd("info_world", verb, raw, filter=filter)


def consider(target):
    _require_str(target, "target")
    return _cmd("consider", "consider", f"consider {target}", target=target)


def diagnose(target=None):
    raw = f"diagnose {target}" if target else "diagnose"
    return _cmd("diagnose", "diagnose", raw, target=target)


def list_commands(kind, player=None):
    verb = _check_enum(kind, LIST_KINDS, "kind")
    raw = f"{verb} {player}" if player else verb
    return _cmd("list_commands", verb, raw, player=player)


# ---------- Character / preferences / lifecycle ----------

def social(name, target=None):
    _require_str(name, "name")
    raw = f"{name} {target}" if target else name
    return _cmd("social", name, raw, target=target)


def set_title(text):
    _require_str(text, "text")
    if "(" in text or ")" in text:
        raise ValueError("title may not contain parentheses")
    return _cmd("set_title", "title", f"title {text}", text=text)


def set_display(tokens):
    _require_str(tokens, "tokens")
    return _cmd("set_display", "display", f"display {tokens}", tokens=tokens)


def set_color(level):
    verb = _check_enum(level, COLOR_LEVELS, "level")
    return _cmd("set_color", "color", f"color {verb}", level=verb)


def set_wimpy(hp):
    if not isinstance(hp, int) or hp < 0:
        raise ValueError("hp must be a non-negative integer")
    return _cmd("set_wimpy", "wimpy", f"wimpy {hp}", hp=hp)


def toggle_pref(flag):
    verb = _check_enum(flag, PREF_FLAGS, "flag")
    return _cmd("toggle_pref", verb, verb, flag=verb)


def stealth(mode):
    verb = _check_enum(mode, STEALTH_MODES, "mode")
    return _cmd("stealth", verb, verb)


def steal(obj, victim):
    _require_str(obj, "obj")
    _require_str(victim, "victim")
    return _cmd("steal", "steal", f"steal {obj} {victim}", obj=obj, victim=victim)


def practice(skill=None):
    raw = f"practice {skill}" if skill else "practice"
    return _cmd("practice", "practice", raw, skill=skill)


def define_alias(name, replacement):
    _require_str(name, "name")
    if name == "alias":
        raise ValueError("cannot alias 'alias'")
    _require_str(replacement, "replacement")
    return _cmd("define_alias", "alias", f"alias {name} {replacement}", name=name, replacement=replacement)


def save_char():
    return _cmd("save_char", "save", "save")


def quit():
    # Shadows the Python REPL-only `quit` builtin (from the `site` module,
    # not a core builtin) inside this module's namespace only — harmless,
    # and matches Ruby's method name exactly.
    return _cmd("quit", "quit", "quit")


# ---------- Magic ----------

def cast(spell, target=None):
    _require_str(spell, "spell")
    raw = f"cast '{spell}' {target}" if target else f"cast '{spell}'"
    return _cmd("cast", "cast", raw, spell=spell, target=target)


def use_magic_item(mode, item, target_args=None):
    verb = _check_enum(mode, SPELL_ITEM, "mode")
    _require_str(item, "item")
    raw = f"{verb} {item} {target_args}" if target_args else f"{verb} {item}"
    return _cmd("use_magic_item", verb, raw, item=item, target_args=target_args)


# ---------- Group ----------

def group_manage(op, target=None):
    verb = _check_enum(op, GROUP_OPS, "op")
    raw = f"{verb} {target}" if target else verb
    return _cmd("group_manage", verb, raw, target=target)


def report_hp():
    return _cmd("report_hp", "report", "report")


# ---------- Room-procedural (SPEC_PROC-mediated) ----------

def shop(op, args=None):
    verb = _check_enum(op, SHOP_OPS, "op")
    raw = f"{verb} {args}" if args else verb
    return _cmd("shop", verb, raw, args=args)


def bank(op, amount=None):
    verb = _check_enum(op, BANK_OPS, "op")
    raw = f"{verb} {amount}" if amount else verb
    return _cmd("bank", verb, raw, amount=amount)


def mail(op, recipient=None):
    verb = _check_enum(op, MAIL_OPS, "op")
    raw = f"{verb} {recipient}" if recipient else verb
    return _cmd("mail", verb, raw, recipient=recipient)


def rent():
    return _cmd("rent", "rent", "rent")


def house_admin(player=None):
    raw = f"house {player}" if player else "house"
    return _cmd("house_admin", "house", raw, player=player)
