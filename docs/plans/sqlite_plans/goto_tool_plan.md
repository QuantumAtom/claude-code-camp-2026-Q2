# `go_to` Navigation Tool — Design Plan (week3_capable)

Status: **IMPLEMENTED — live and verified.** `go_to` is built and registered
in both `week3_capable/python/boukensha/tools/mud.py` and
`week3_capable/ruby/lib/boukensha/tools/mud.rb`, backed by
`world/pathfind.{py,rb}` in both languages. It has been played against the
real MUD (see `.boukensha/sessions/*.jsonl`), and both languages' parser
fixture suites pass (`python3 week3_capable/fixtures/check_parser_fixtures.py`,
`ruby week3_capable/fixtures/check_parser_fixtures.rb` — 13/13 each). See §11
below for how each §7 open question was actually resolved. Nothing here is
committed to git yet.

## 0. Dependency on the world-state plan

`go_to` is the "specific tool using the primitives to use the database for
decision-making" the Week 3 journal says comes right after the world DB
(`docs/journal/3_week3.md`, entry 00: *"Afterwards, I will start doing
specific tools using the primitives to use the database for
decision-making."*). It can't be built before that DB is, because it needs
two things the world-state plan is what produces:

- **A populated `exits` graph.** `go_to` only ever replays routes that have
  already been discovered by walking them — it does not invent a path
  through unmapped territory (same "don't fabricate" principle as the rest
  of this DB's design). No exits recorded yet between two rooms means no
  route yet, full stop, regardless of whether one exists in the actual game.
- **`current_location_id` session state**, per world_state_db_plan §5's
  graph-pointer tracking. `go_to` needs to know where it's starting from
  without asking the model, or the whole point (zero added LLM round-trips)
  is lost.

So the sequencing is: world_state_db_plan §2a → §3 → §6 lands first
(package bootstrap, schema, write-back module + registry hook), *then* this
plan. Nothing here changes anything already decided in that document.

## 1. Motivation

Same Week 2 telemetry this whole DB effort is chasing
(world_state_db_plan §1): 68,289 tokens burned backtracking through the
sewer with no memory of where it had already been. The world-state DB fixes
the *memory* half of that (§5's exits graph). It does not, by itself, fix
the *execution* half — even with a perfect map in SQLite, walking from room
A to room Z today still means the model calling `move` once per hop,
reading each hop's room text, and deciding the next direction itself. For a
10-hop walk that's 10 LLM round-trips and 10 room descriptions in context,
even though the *decision* ("how do I get from A to Z") was already fully
answered by a graph query the instant both endpoints were known.

`go_to(destination)` collapses that: one tool call in, the whole walk
happens inside Python/Ruby using the same `move` primitive the model would
have called by hand, one tool result out. The pathfinding and the hop-by-hop
`move` sends cost zero LLM tokens — they're a BFS over rows already in
SQLite plus repeated calls to the same `send_cmd(p.move(direction))` that
`tools/mud.py`'s existing `move` tool already uses
(`week1_baseline/python/12_context/boukensha/tools/mud.py:103-108`). The
only irreducible LLM cost is the one call to invoke `go_to` and the one
summary result it returns.

## 2. Scope for v1 — and what's deliberately out

**In scope:**
- Walking a route made entirely of plain directional hops (`north`, `south`,
  `east`, `west`, `up`, `down`) through the `move` primitive, exactly the
  set `mud_manager.primitives.move()` already validates against.
- Resolving a destination that's an exact/near-exact match on a known
  `locations.name`.
- Falling back to "get me to the town, even if I don't know the exact shop
  yet" when the specific place isn't in the DB but a town it's in is.
- Failing loudly and handing back to the model — never guessing, never
  walking through an untested exit — when it can't reach a real answer.

**Out of scope, explicitly, for v1:**
- Doors/locks along the route (`open_door`/`unlock` primitives). An exit
  that requires a feature interaction isn't distinguishable from a plain
  exit in the current `exits` schema (features attach to `locations`, not
  to a specific `(location_id, direction)` row) — see §7's open question.
- Fighting or fleeing past a mob blocking the path. If a hop fails because
  something's in the way, `go_to` stops and reports back; it does not
  attempt combat on the model's behalf.
- Cross-zone teleport/recall magic. Only literal, previously-walked `exits`
  rows count as a route.
- Exact-shop-finding inside a town it's never mapped before. See §5 — this
  gets you to the town, not through a maze it hasn't seen.

## 3. Tool surface

One new tool, registered the same way as every other tool in
`tools/mud.py` (`registry.tool("go_to", ..., go_to)`):

```python
go_to(destination: str) -> str
```

Free-text `destination`, same style as how a player would phrase it —
`"weapon shop"`, `"weapon shop in midgaard"`, `"the temple"`. No structured
args, no enum, because the model shouldn't have to know the DB's schema to
call this; resolution (§4) is where that text gets turned into a
`location_id` (or an honest failure).

Return value is a single string covering the whole walk, not one string per
hop — e.g.:

```
Walked 7 rooms (n, n, e, e, n, n, w) from "The Newbie Training Grounds" to
"Midgaard, City Square" — nearest known point to "weapon shop in midgaard";
exact shop location isn't mapped yet, explore from here.

[full `look` text of the arrival room follows, unchanged from what `look`
would have returned]
```

Appending the arrival room's real `look` output matters: skipping the
intermediate hops shouldn't mean skipping the *information* the model would
have gotten by arriving there manually. It gets the same situational
awareness at the destination it always would have, just none of the
in-between noise.

## 4. Destination resolution

Deterministic string matching against `locations.name` — no LLM parsing of
the destination string, keeping with this DB's whole "explicit over
inferred" premise (world_state_db_plan §1).

1. Split on `" in "` if present: `"weapon shop in midgaard"` →
   place=`"weapon shop"`, town=`"midgaard"`. No `" in "` → the whole string
   is the place query, town unset.
2. Query `locations` for rows where `name` (case-insensitive) contains the
   place query. If a town was given, prefer rows also matching town-name
   text (§5) among that result set.
3. **Zero matches** → fall through to §5 (town-only fallback), or fail
   outright if no town was parseable either.
4. **One match** → that's the target `location_id`.
5. **Multiple matches** (expected — world_state_db_plan §5 notes room names
   aren't unique on purpose, e.g. sewer mazes) → disambiguate by BFS
   distance from `current_location_id` (§6) and take the nearest reachable
   one. If two or more tie at the same distance, don't guess — return the
   list to the model and let it pick (the one place in this design where a
   real ambiguity gets punted back, because guessing here risks walking
   into the wrong maze room silently).

## 5. Town-level fallback — the "newbie zone → Midgaard" case

This is the case from your prompt: the exact destination isn't in
`locations` yet, but the town it's in is already partially mapped from
having passed through or near it before.

- No schema change needed for v1: CircleMUD room names for town areas
  routinely embed the town's proper name (e.g. `"Midgaard, City Square"`,
  `"Midgaard, Temple Row"`), so "is this room in Midgaard" is a plain `name
  LIKE '%midgaard%'` (or `description LIKE`) check against rows where
  `area_type = 'town'`.
- If that query finds one or more known rooms belonging to the named town:
  pick the one nearest `current_location_id` by BFS distance (§6) as the
  **anchor**, path to it via the normal execution loop (§6), and return a
  response that's explicit about the partial result — arrived at the town,
  not at the specific unmapped place — so the model knows to keep exploring
  locally instead of assuming it's standing in the shop.
- If the town query finds *nothing* — the town has never been visited at
  all — `go_to` fails outright with "no known route toward Midgaard; nothing
  there has been discovered yet." No blind walking in a guessed direction.
- **Flagging honestly:** `LIKE '%midgaard%'` is a heuristic, not a real
  "town" concept — the schema doesn't have one (§3 of the world-state plan
  only has the coarse `area_type` enum: town/sewer/castle/dungeon, not a
  proper place name). It'll work for CircleMUD's actual naming convention
  once sampled, but if you'd rather have a real column for this
  (e.g. parsing `"Midgaard, City Square"` into `zone_name="Midgaard"` at
  write-back time and storing it), that's a small addition to
  `locations` and `world/parser.{py,rb}` — flagging as an open question in
  §7 rather than assuming it. Yes, add that coumn. 

## 6. Pathfinding & execution

**Pathfinding:** plain BFS over the `exits` table from `current_location_id`
to the resolved target `location_id`. BFS, not Dijkstra — every hop costs
the same (one `move` call), so unweighted shortest-path-by-hop-count is
exactly the right notion of "shortest route" here. Directed, per
world_state_db_plan §10's note that exits aren't guaranteed symmetric (a
`north` exit existing doesn't imply a `south` exit back) — BFS already
respects `exits.direction`/`leads_to_location_id` as directed edges, so
that's free.

If `current_location_id` is unset (session hasn't looked around yet this
run), `go_to` fails immediately with the same style of guard the existing
`move`/`look` tools use for "not connected" — `"error: current location
unknown — call look first"`.

**Execution loop**, entirely inside the tool, no model involvement per hop:

```python
def go_to(destination):
    target_id, note = resolve_destination(destination)   # §4/§5
    if target_id is None:
        return note   # honest failure message, no walk attempted
    path = bfs_path(current_location_id, target_id)        # list[direction]
    if path is None:
        return f"'{destination}' is known but no discovered route reaches it yet."
    if len(path) > MAX_HOPS:
        return f"route to '{destination}' is {len(path)} hops — too long to auto-walk (cap {MAX_HOPS}); needs manual travel or a shorter waypoint."

    taken = []
    for direction in path:
        result_text = send_cmd(p.move(direction))
        world.observe("move", {"direction": direction}, result_text)   # same write-back hook as manual move calls
        if not moved_successfully(result_text):                        # §4-style phrase check, e.g. "Alas, you cannot go that way."
            return (f"stopped after {len(taken)}/{len(path)} hops "
                     f"({', '.join(taken)}) — {direction} failed: {result_text.strip()}")
        taken.append(direction)

    return f"Walked {len(taken)} rooms ({', '.join(taken)}) to \"{destination}\".\n\n{result_text}"
```

Key points:
- Every hop still goes through `world.observe(...)`, the same registry hook
  world_state_db_plan §6a wires up — so a `go_to` walk keeps the DB exactly
  as up to date as a manual walk would have. `go_to` is a *scheduler* for
  the existing `move` primitive, not a bypass of the write-back path.
- Each hop's result text is checked before continuing. The DB is a cache of
  what's been seen, not ground truth of what's true *right now* — a
  previously-open exit can be blocked by a mob, a door someone else closed,
  etc. `moved_successfully()` is a small set of known CircleMUD failure
  phrases (grounded the same way world_state_db_plan §4 grounded its
  parser — pull real "you can't go that way" / combat-interrupt text from
  `.boukensha/sessions/*.jsonl` before writing the check, not guessed).
  On failure, stop immediately and report exactly how far it got — never
  push through blind.
- `MAX_HOPS` (config constant, something like 40-60) exists purely as a
  circuit breaker against an unexpectedly long BFS result dumping a huge
  hop list into one tool call — BFS itself can't loop forever (it's a
  finite graph, visited-set guarantees termination), this is just about
  keeping any single result reasonably sized.
- Only the **final** hop's `result_text` (the arrival room) goes back to the
  model, per §3 — intermediate rooms are consumed internally by
  `world.observe` (so they're still recorded) but never surfaced in the
  tool result.

## 7. Open questions for you

Same spirit as world_state_db_plan §11 — flagging rather than silently
picking, since these are judgment calls. **Resolved — see §10 for the
decisions record.**

1. **Doors along a route** (§2's scope cut): leave genuinely out of scope
   for v1 (fail the hop, report back), or worth a small extension where a
   failed hop due to a locked door triggers one automatic `open_door`/
   `unlock` retry before giving up? Leaning "out of scope" — auto-unlocking
   assumes a key requirement that isn't tracked anywhere yet. Do not autounlock. Ask the user first.
2. **Real `zone_name` column vs. `LIKE` heuristic** (§5): start with the
   heuristic (zero schema change, ships faster) and revisit only if it
   misfires in practice, or add the column now while §6 of the world-state
   plan is fresh? Leaning "start with the heuristic." Add the column
3. **`MAX_HOPS` value**: no strong opinion — 40? 60? Depends on how large
   the mapped world gets; easy to tune later, not worth guessing precisely
   now. Claude's decision
4. **Ambiguous-match behavior** (§4 step 5, tied-distance case): confirmed
   as "return the list, let the model pick" rather than picking arbitrarily
   — please confirm that's the right call, since it's the one place this
   design deliberately spends tokens on a judgment call instead of avoiding
   them. It's the right call. Thank you.

## 8. Where the code lives

Mirrors world_state_db_plan §2's layout — one new module per language, same
registry hook pattern as every existing tool:

```
week3_capable/
  python/boukensha/
    world/
      pathfind.py          # bfs_path(), resolve_destination() — reads world.db, no writes
    tools/
      mud.py                # add go_to registration here, alongside move/look/etc.
  ruby/lib/boukensha/
    world/
      pathfind.rb           # mirrors pathfind.py
    registry.rb              # add go_to registration here
```

`pathfind.{py,rb}` is read-only against `world.db` (BFS query + name
matching) — it doesn't need its own store functions beyond what
`world/store.{py,rb}` (world_state_db_plan §6) already provides for reading
`current_location_id`. `go_to` itself lives next to `move` in `tools/mud.py`
since it's still fundamentally a movement tool, just a multi-hop one, and
it needs `send_cmd`/`p.move` from the same closure `move` already uses.

## 9. Next step

Once world_state_db_plan's §2a/§3/§6 land (package bootstrap, schema in
place, write-back module + `current_location_id` tracking working end to
end), this plan is ready to implement in this order: `pathfind.{py,rb}`
(BFS + resolution, testable standalone against a hand-seeded `world.db`),
then the `go_to` tool registration wiring it to `send_cmd`, then real-play
verification of §6's failure-phrase detection (same "ground it in real
output" pass world_state_db_plan §4 and §8 both did).

## 10. Decisions

Answers recorded directly against §7 by you; restated here as a decisions
record, same reasoning as world_state_db_plan §11:

1. **Doors: out of scope, no auto-unlock retry.** A failed hop due to a
   locked door stops `go_to` and reports back, same as any other blocked
   hop — no automatic `open_door`/`unlock` attempt. Your call: "Do not
   autounlock. Ask the user first," since a door can gate something
   dangerous on the other side. Matches the implementation — the execution
   loop in both `tools/mud.py`/`tools/mud.rb` never retries a failed hop.
2. **Real `zone_name` column added**, superseding the `LIKE '%midgaard%'`
   heuristic originally proposed in §5. `schema.sql` has
   `locations.zone_name TEXT`; `world/parser.{py,rb}`'s
   `detect_seed_zone()` seeds it from room name/description, and
   `store.propagate_zone()` flood-fills it outward through the exits graph
   so rooms without their own name-embedded town string still inherit it.
   `pathfind.{py,rb}`'s town-anchor fallback (§5) queries this column
   directly instead of a `LIKE` scan.
3. **`MAX_HOPS = 50`**, left to Claude's judgment per your note — a plain
   constant (`GO_TO_MAX_HOPS` in `tools/mud.py`, mirrored in `tools/mud.rb`),
   trivial to retune later if the mapped world's diameter ends up needing
   more or fewer hops than that in practice.
4. **Ambiguous-match behavior confirmed as designed** — tied-distance
   matches are returned to the model to pick from rather than guessed at,
   exactly as §4 step 5 specifies. Your response: "It's the right call."

No changes to §3–§6/§8's design were needed to act on any of these — all
four are reflected as-is in the current `pathfind.{py,rb}`/`tools/mud.{py,rb}`
implementation, confirmed by reading the code directly (not just this plan)
before writing this section.

### 10a. Live-testing finding & fix: disambiguation stranded on duplicate rows

Found by driving `go_to` directly against the real MUD server (not just
fixtures): `go_to("weapon shop in midgaard")` failed outright with "matches
2 known locations, none reachable by a discovered route", even while
standing in an already zone-tagged Midgaard room. Root cause: separate play
sessions each text-match a fresh start into their own `locations` row
(world_state_db_plan §5's accepted duplicate-row tradeoff), so both
existing "The Weapon Shop" rows ended up on unreachable islands relative to
the current position — but the zero-match case already knew how to fall
back to the town anchor (§5), and the multiple-match case simply didn't
reuse that fallback. Fixed in both `pathfind.py` and `pathfind.rb`:
`_disambiguate`/`disambiguate` now falls through to the town-anchor lookup
when a town was given and none of the exact name matches are reachable,
instead of failing outright. Re-verified live after the fix — the same
call now correctly returns the nearest known Midgaard anchor. Both
languages' parser fixture suites still pass 13/13 (no dedicated
pathfind/BFS fixtures exist yet — that logic has only ever been verified
live, not by a fixture suite).
