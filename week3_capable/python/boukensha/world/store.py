import json
from datetime import datetime


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- locations (plan §5: identity is graph-position-first, ----------
# ---------- name-matching-second — this module only does the SQL; the ------
# ---------- graph-pointer logic itself lives in world/__init__.py) ---------

def get_or_create_location(conn, *, name=None, area_type=None, description=None, visited=False):
    """Two call shapes, per §5:
    - name=None (a fresh placeholder for an unscanned exit): always inserts
      a new row — a placeholder is definitionally new, no lookup needed.
    - name given (the text-matching fallback path): looks for an exact
      (name, description) match first, since room names alone aren't
      unique (§5) — only a full match counts as "the same room already
      known"."""
    if name is not None:
        row = conn.execute(
            "SELECT location_id FROM locations WHERE name = ? AND description IS ?",
            (name, description),
        ).fetchone()
        if row:
            return row[0]
    cur = conn.execute(
        "INSERT INTO locations (name, area_type, description, visited) VALUES (?, ?, ?, ?)",
        (name, area_type, description, 1 if visited else 0),
    )
    conn.commit()
    return cur.lastrowid


def touch_location(conn, location_id, **updates):
    """Update name/description/area_type/visited/last_seen_at, only
    overwriting fields explicitly passed as non-None — this is how a
    placeholder (name=NULL) gets filled in on first real visit without
    clobbering fields nothing new was observed for."""
    fields = {k: v for k, v in updates.items() if v is not None}
    fields["last_seen_at"] = _now_iso()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE locations SET {set_clause} WHERE location_id = ?",
        (*fields.values(), location_id),
    )
    conn.commit()


def get_location(conn, location_id):
    return conn.execute(
        "SELECT location_id, name, area_type, description, visited FROM locations WHERE location_id = ?",
        (location_id,),
    ).fetchone()


def get_or_create_exit(conn, location_id, direction, leads_to_location_id):
    conn.execute(
        "INSERT OR IGNORE INTO exits (location_id, direction, leads_to_location_id) VALUES (?, ?, ?)",
        (location_id, direction, leads_to_location_id),
    )
    conn.commit()


def get_exit(conn, location_id, direction):
    """The graph-pointer lookup §5 relies on: known by position, no text
    matching needed, if this returns a row."""
    row = conn.execute(
        "SELECT leads_to_location_id FROM exits WHERE location_id = ? AND direction = ?",
        (location_id, direction),
    ).fetchone()
    return row[0] if row else None


# ---------- mobs / items — identity by UNIQUE name (§3), update rules ------
# ---------- per §7: fields describing the mob/item's *identity* are --------
# ---------- fill-once; fields describing *transient state* overwrite -------
# ---------- with the latest observation. -----------------------------------

def get_or_create_mob(conn, name, *, disposition=None, hp=None, level=None, is_dialogue_enabled=None):
    row = conn.execute("SELECT mob_id FROM mobs WHERE name = ?", (name,)).fetchone()
    if row:
        mob_id = row[0]
        _update_mob(conn, mob_id, disposition=disposition, hp=hp, level=level,
                    is_dialogue_enabled=is_dialogue_enabled)
        return mob_id
    cur = conn.execute(
        "INSERT INTO mobs (name, disposition, hp, level, is_dialogue_enabled) VALUES (?, ?, ?, ?, ?)",
        (name, disposition, hp, level, is_dialogue_enabled),
    )
    conn.commit()
    return cur.lastrowid


def _update_mob(conn, mob_id, *, disposition, hp, level, is_dialogue_enabled):
    sets, vals = [], []
    if disposition is not None:                      # transient -> always overwrite
        sets.append("disposition = ?"); vals.append(disposition)
    if hp is not None:                                # only a real number overwrites (§7 -- HP
        sets.append("hp = ?"); vals.append(hp)        # otherwise stays NULL; nothing here fabricates one)
    if level is not None:                             # identity -> fill-once
        sets.append("level = COALESCE(level, ?)"); vals.append(level)
    if is_dialogue_enabled is not None:                # identity -> fill-once
        sets.append("is_dialogue_enabled = COALESCE(is_dialogue_enabled, ?)"); vals.append(is_dialogue_enabled)
    if not sets:
        return
    vals.append(mob_id)
    conn.execute(f"UPDATE mobs SET {', '.join(sets)} WHERE mob_id = ?", vals)
    conn.commit()


def link_mob(conn, location_id, mob_id, *, condition=None):
    """Plan §6 lists this as link_mob(conn, location_id, mob_id) -> None;
    condition= is an addition beyond that minimal signature, since §3's
    location_mobs.condition ("latest qualitative reading") has to be set
    somewhere, and this junction row is where it lives."""
    conn.execute(
        "INSERT INTO location_mobs (location_id, mob_id, condition, last_seen_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(location_id, mob_id) DO UPDATE SET "
        "condition = COALESCE(excluded.condition, location_mobs.condition), "
        "last_seen_at = excluded.last_seen_at",
        (location_id, mob_id, condition, _now_iso()),
    )
    conn.commit()


def get_or_create_item(conn, name, *, item_type=None, level=None):
    row = conn.execute("SELECT item_id FROM items WHERE name = ?", (name,)).fetchone()
    if row:
        item_id = row[0]
        sets, vals = [], []
        if item_type is not None:
            sets.append("item_type = COALESCE(item_type, ?)"); vals.append(item_type)
        if level is not None:
            sets.append("level = COALESCE(level, ?)"); vals.append(level)
        if sets:
            vals.append(item_id)
            conn.execute(f"UPDATE items SET {', '.join(sets)} WHERE item_id = ?", vals)
            conn.commit()
        return item_id
    cur = conn.execute(
        "INSERT INTO items (name, item_type, level) VALUES (?, ?, ?)",
        (name, item_type, level),
    )
    conn.commit()
    return cur.lastrowid


def link_item(conn, location_id, item_id, quantity=None):
    """quantity overwrites with the latest observed count (§7 — the one
    junction-table field that's genuinely mutable, per the spec's own gold-
    amount example)."""
    conn.execute(
        "INSERT INTO location_items (location_id, item_id, quantity) VALUES (?, ?, ?) "
        "ON CONFLICT(location_id, item_id) DO UPDATE SET quantity = excluded.quantity",
        (location_id, item_id, quantity),
    )
    conn.commit()


# ---------- features (doors, etc.) -- schema has no UNIQUE key on ----------
# ---------- feature_type (§3), so unlike mobs/items/weapons there's no -----
# ---------- name-identity lookup possible here -- every call inserts a -----
# ---------- new row, matching the schema as specified. ---------------------

def get_or_create_feature(conn, feature_type, *, is_locked=None, is_lockpickable=None, available_actions=None):
    actions_json = json.dumps(available_actions) if available_actions is not None else None
    cur = conn.execute(
        "INSERT INTO features (feature_type, is_locked, is_lockpickable, available_actions) "
        "VALUES (?, ?, ?, ?)",
        (feature_type, is_locked, is_lockpickable, actions_json),
    )
    conn.commit()
    return cur.lastrowid


def link_feature(conn, location_id, feature_id):
    conn.execute(
        "INSERT OR IGNORE INTO location_features (location_id, feature_id) VALUES (?, ?)",
        (location_id, feature_id),
    )
    conn.commit()


# ---------- weapons / pseudo-weapons + combat estimation (§8) --------------
# ---------- "anything that can damage a mob is a weapon or pseudo- ---------
# ---------- weapon" (decision #8) -- a melee weapon, "fists", a skill ------
# ---------- name, or (once grounded) a spell/item name are all just --------
# ---------- rows in this one table, identified by name like mobs/items. ----

def get_or_create_weapon(conn, name):
    row = conn.execute("SELECT weapon_id FROM weapons WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO weapons (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def record_attack(conn, mob_id, weapon_id, *, landed):
    if not landed:
        return
    conn.execute(
        "INSERT INTO mob_weapon_stats (mob_id, weapon_id, hits_landed_total, kills_total) "
        "VALUES (?, ?, 1, 0) "
        "ON CONFLICT(mob_id, weapon_id) DO UPDATE SET hits_landed_total = hits_landed_total + 1",
        (mob_id, weapon_id),
    )
    conn.commit()


def record_kill(conn, mob_id, weapon_id):
    conn.execute(
        "INSERT INTO mob_weapon_stats (mob_id, weapon_id, hits_landed_total, kills_total) "
        "VALUES (?, ?, 0, 1) "
        "ON CONFLICT(mob_id, weapon_id) DO UPDATE SET kills_total = kills_total + 1",
        (mob_id, weapon_id),
    )
    conn.commit()


# Decision #6: don't trust the numeric estimate until kills_total clears
# this threshold for the exact (mob, weapon) pairing -- below it, callers
# should fall back to location_mobs.condition's qualitative reading instead.
KILLS_TOTAL_TRUST_THRESHOLD = 3


def estimate_condition(conn, mob_id, weapon_id, hits_landed_this_fight):
    """Returns estimated fraction of health remaining (0.0-1.0), or None if
    there isn't enough data yet (§8) -- callers fall back to §3's
    qualitative location_mobs.condition in that case."""
    row = conn.execute(
        "SELECT hits_landed_total, kills_total FROM mob_weapon_stats WHERE mob_id = ? AND weapon_id = ?",
        (mob_id, weapon_id),
    ).fetchone()
    if not row or row[1] < KILLS_TOTAL_TRUST_THRESHOLD:
        return None
    hits_landed_total, kills_total = row
    avg_hits_to_kill = hits_landed_total / kills_total
    if avg_hits_to_kill <= 0:
        return None
    percent_remaining = 1 - (hits_landed_this_fight / avg_hits_to_kill)
    return max(0.0, min(1.0, percent_remaining))


# ---------- zone/town identity (goto_tool_plan §5) --------------------------
# zone_name is a derived enrichment, not text-matched per room -- it's
# flood-filled outward from a handful of "seed" rooms whose own text does
# explicitly name a town (parser.detect_seed_zone), through the exits graph.
# Treated as identity-like: fill-once, never overwritten -- same rule as
# mobs.level (§7). A room's town doesn't change out from under it.

# Town cores are compact (confirmed against real Midgaard room samples --
# well under a dozen hops end to end); this caps a flood-fill from leaking
# deep into an unrelated connected maze/sewer that has no distinguishing
# seed of its own to stop at.
ZONE_PROPAGATION_MAX_HOPS = 12


def fill_zone_name(conn, location_id, zone_name):
    """Fill-once: only writes if zone_name is currently unset."""
    conn.execute(
        "UPDATE locations SET zone_name = ? WHERE location_id = ? AND zone_name IS NULL",
        (zone_name, location_id),
    )
    conn.commit()


def get_zone_name(conn, location_id):
    row = conn.execute("SELECT zone_name FROM locations WHERE location_id = ?", (location_id,)).fetchone()
    return row[0] if row else None


def propagate_zone(conn, start_location_id, zone_name, max_hops=ZONE_PROPAGATION_MAX_HOPS):
    """Bounded flood-fill (goto_tool_plan §5): tags every location reachable
    from start_location_id within max_hops with zone_name, stopping
    expansion through any room that already carries a *different*
    zone_name (never crosses into another town's already-claimed
    territory). Exits are treated as undirected for this purpose -- physical
    adjacency doesn't care which direction the game lets you walk it."""
    fill_zone_name(conn, start_location_id, zone_name)
    frontier = {start_location_id}
    visited = {start_location_id}
    for _ in range(max_hops):
        if not frontier:
            break
        next_frontier = set()
        for loc_id in frontier:
            neighbors = conn.execute(
                "SELECT leads_to_location_id FROM exits WHERE location_id = ? "
                "UNION "
                "SELECT location_id FROM exits WHERE leads_to_location_id = ?",
                (loc_id, loc_id),
            ).fetchall()
            for (nid,) in neighbors:
                if nid in visited:
                    continue
                visited.add(nid)
                existing = get_zone_name(conn, nid)
                if existing is None:
                    fill_zone_name(conn, nid, zone_name)
                    next_frontier.add(nid)
                elif existing == zone_name:
                    next_frontier.add(nid)
                # else: a different zone already claims this room -- stop here
        frontier = next_frontier
