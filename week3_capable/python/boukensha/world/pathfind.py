"""goto_tool_plan: turns a free-text destination into a walkable route over
the exits graph already recorded in world.db. Read-only against the DB --
no writes happen here, and nothing here ever invents a path through
unmapped territory (same "don't fabricate" principle as world/__init__.py's
write-back). Callers (tools/mud.py's go_to) are expected to have already
confirmed current_location_id is not None before calling into this module.
"""


def bfs_path(conn, start_location_id, target_location_id):
    """Shortest sequence of directions from start to target, following only
    known `exits` rows. BFS, not Dijkstra -- every hop costs exactly one
    `move` call, so unweighted shortest-path-by-hop-count is the right
    notion of "shortest" here. Directed, matching `exits` itself (a
    `north` exit existing doesn't imply a `south` exit back). Returns None
    if no route is known yet."""
    if start_location_id == target_location_id:
        return []

    frontier = [start_location_id]
    visited = {start_location_id}
    came_from = {}  # location_id -> (prev_location_id, direction)

    while frontier:
        next_frontier = []
        for loc_id in frontier:
            rows = conn.execute(
                "SELECT direction, leads_to_location_id FROM exits WHERE location_id = ?",
                (loc_id,),
            ).fetchall()
            for direction, dest_id in rows:
                if dest_id in visited:
                    continue
                visited.add(dest_id)
                came_from[dest_id] = (loc_id, direction)
                if dest_id == target_location_id:
                    return _reconstruct(came_from, target_location_id)
                next_frontier.append(dest_id)
        frontier = next_frontier

    return None


def _reconstruct(came_from, target_location_id):
    path = []
    node = target_location_id
    while node in came_from:
        prev, direction = came_from[node]
        path.append(direction)
        node = prev
    path.reverse()
    return path


def _distance(conn, start_location_id, target_location_id):
    path = bfs_path(conn, start_location_id, target_location_id)
    return None if path is None else len(path)


def resolve_destination(conn, current_location_id, destination_text):
    """Turns free-text destination into a target location_id (goto_tool_plan
    §4/§5). Returns (target_location_id, note):
    - target is None on outright failure; note explains why.
    - target is set and note is None on an exact, unambiguous match.
    - target is set and note is non-None on a town-anchor fallback (§5) --
      the note is an informational heads-up for the caller to surface, not
      a failure.
    """
    destination_text = (destination_text or "").strip()
    if not destination_text:
        return None, "no destination given"

    lowered = destination_text.lower()
    if " in " in lowered:
        idx = lowered.index(" in ")
        place, town = destination_text[:idx].strip(), destination_text[idx + 4:].strip()
    else:
        place, town = destination_text, None

    rows = conn.execute(
        "SELECT location_id, name, zone_name FROM locations WHERE name LIKE ? ESCAPE '\\'",
        (f"%{_escape_like(place)}%",),
    ).fetchall()

    if town and rows:
        town_rows = [r for r in rows if r[2] and r[2].lower() == town.lower()]
        if town_rows:
            rows = town_rows

    if len(rows) == 1:
        return rows[0][0], None

    if len(rows) > 1:
        return _disambiguate(conn, current_location_id, town, destination_text, rows)

    # Zero direct matches -- town-level fallback (§5): treat the town token
    # (or the whole query, if no " in " was given) as a possible zone_name
    # and route to the nearest known room already tagged with it.
    zone_query = town or destination_text
    return _resolve_town_anchor(conn, current_location_id, zone_query, destination_text)


def _disambiguate(conn, current_location_id, town, destination_text, rows):
    """§4 step 5: room names aren't unique on purpose (sewers/mazes). Prefer
    the reachable match nearest the current position; a genuine tie is
    handed back to the caller rather than guessed at.

    Confirmed live: separate play sessions each text-match a fresh start
    into their own location row (world_state_db_plan §5's accepted
    duplicate-row tradeoff), which can leave every name-matched row
    stranded on an unreachable island even though the town itself is
    well-mapped. If a town was given and none of the exact matches are
    reachable, fall back to routing toward the town anchor (§5) instead of
    failing outright -- same behavior the zero-match case already gets."""
    scored = [(r[0], r[1], _distance(conn, current_location_id, r[0])) for r in rows]
    reachable = [s for s in scored if s[2] is not None]
    if not reachable:
        if town:
            return _resolve_town_anchor(conn, current_location_id, town, destination_text)
        return None, f"'{destination_text}' matches {len(rows)} known locations, none reachable by a discovered route"
    reachable.sort(key=lambda s: s[2])
    best_dist = reachable[0][2]
    tied = [s for s in reachable if s[2] == best_dist]
    if len(tied) == 1:
        return tied[0][0], None
    names = ", ".join(f'"{t[1]}" (location_id={t[0]})' for t in tied)
    return None, f"'{destination_text}' is ambiguous -- {len(tied)} equally-close matches: {names}. Pick one and retry with a more specific name."


def _resolve_town_anchor(conn, current_location_id, zone_query, original_text):
    rows = conn.execute(
        "SELECT location_id, name FROM locations WHERE zone_name = ? COLLATE NOCASE",
        (zone_query,),
    ).fetchall()
    if not rows:
        return None, f"no known route toward '{zone_query}' -- nothing there has been discovered yet"

    scored = [(r[0], r[1], _distance(conn, current_location_id, r[0])) for r in rows]
    reachable = [s for s in scored if s[2] is not None]
    if not reachable:
        return None, f"'{zone_query}' is known but no discovered route reaches any of it yet"
    reachable.sort(key=lambda s: s[2])
    anchor_id, anchor_name, _ = reachable[0]
    return anchor_id, (
        f'nearest known point in "{zone_query}" to "{original_text}" is "{anchor_name}"; '
        f"exact location isn't mapped yet -- explore from here"
    )


def _escape_like(text):
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def find_nearest_supply(conn, current_location_id, item_type):
    """needs_management_plan §5: nearest reachable location known to carry
    an item of item_type (BFS reachability, goto_tool_plan-style). Returns
    (location_id, location_name, item_name, hops), or None if nothing's
    been discovered yet -- never fabricates a source."""
    rows = conn.execute(
        "SELECT li.location_id, l.name, i.name FROM location_items li "
        "JOIN items i ON i.item_id = li.item_id "
        "JOIN locations l ON l.location_id = li.location_id "
        "WHERE i.item_type = ?",
        (item_type,),
    ).fetchall()
    if not rows:
        return None

    best = None
    for loc_id, loc_name, item_name in rows:
        path = bfs_path(conn, current_location_id, loc_id)
        if path is None:
            continue
        if best is None or len(path) < best[3]:
            best = (loc_id, loc_name, item_name, len(path))
    return best


def find_reachable_duplicate(conn, current_location_id, location_id):
    """needs_management_plan §9a follow-up, confirmed live: when
    location_id itself isn't BFS-reachable, another location row can still
    exist for what's physically the same room -- world_state_db_plan §5's
    accepted duplicate-row tradeoff (separate sessions each text-match a
    fresh start into their own row, and an edge recorded from one session
    can point at a different duplicate than the one a caller remembers).
    Returns (other_location_id, path) for the nearest *other* row sharing
    the same name that IS reachable, or None."""
    row = conn.execute("SELECT name FROM locations WHERE location_id = ?", (location_id,)).fetchone()
    if row is None or row[0] is None:
        return None
    name = row[0]
    candidates = conn.execute(
        "SELECT location_id FROM locations WHERE name = ? AND location_id != ?",
        (name, location_id),
    ).fetchall()
    best = None
    for (cand_id,) in candidates:
        path = bfs_path(conn, current_location_id, cand_id)
        if path is None:
            continue
        if best is None or len(path) < len(best[1]):
            best = (cand_id, path)
    return best
