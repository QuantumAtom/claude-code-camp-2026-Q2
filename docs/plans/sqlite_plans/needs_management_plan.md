# Hunger/Thirst Automation — Design Plan (week3_capable)

Status: **IMPLEMENTED — live and verified**, in both `week3_capable/python/`
and `week3_capable/ruby/`, including the `return_to_start` follow-up (§9a).
One correction from the original draft (§4a) was found before any code was
written, by testing the plan's own regex against real transcripts first.
Two more real bugs were found and fixed via live round-trip testing of
`return_to_start` (§9b): a missing move-failure phrase that let `go_to`
silently believe a resting-blocked move had succeeded, and a duplicate-room
edge case that stranded the exact remembered return point. Both languages'
parser fixture suites pass (17/17, up from 13 — see
`fixtures/parser_cases.yaml`'s `shop_stock_*`/`classify_consumable_cases`/
`inventory_carrying` cases).

## 0. Clearing up a misconception first

You said "I thought we already kept track of items in a shop" — worth
correcting before anything else, since it changes what this plan actually
has to build: **we don't, yet.** `world/__init__.py`'s `observe()` dispatch
table only has a case for `get_item` (picking something up off the ground
or a corpse) — that's `_observe_pickup()`, which writes into
`items`/`location_items`. There is no case for the `shop` tool at all, for
either `action: "list"` or `action: "buy"`. I checked by reading the
dispatch table directly, not by assuming. Concretely: I pulled real
`shop("buy", "local speciality")` transcripts from `.boukensha/sessions/`
and confirmed the purchase succeeds ("You now have a bottle.") but nothing
about it reaches `world.db` — the DB would come up empty for "where can I
buy bread" even in a town you've already shopped in five times. §4 below
covers the fix.

## 1. Motivation

The same Week 2 incident that kicked off the whole DB effort
(`world_state_db_plan.md` §1): *"the Honeycomb traces showed the agent
burning 65,450 tokens checking each empty water bottle before walking to
the fountain."* `world_state_db_plan` and `goto_tool_plan` fixed the
*memory* and *movement-execution* halves of the overall token problem. This
plan closes the loop on the specific incident that started it: detecting
hunger/thirst, checking what's already on hand, and — only when nothing's
on hand — using the world DB to find a known source, instead of the model
guessing/flailing turn by turn.

## 2. Grounding in real MUD output

Pulled directly from `.boukensha/sessions/*.jsonl`, not guessed:

```
check("score")   → "...\r\nYou are hungry.\r\nYou are thirsty.\r\n...\r\n72H 100M 93V (motd) > "
check("inventory") → "You are carrying:\r\na bottle\r\na bottle\r\nthe smelly hide of the Minotaur\r\n...\r\n62H 100M 90V (motd) > "
consume_item(fountain, drink) → "You drink the clear water.\r\nYou are hungry.\r\n\r\n62H 100M 72V (motd) > "
shop("list") → " ##   Available   Item                                               Cost\r\n"
                "----------------------------------------------------------------------------\r\n"
                "  1)  Unlimited   A bottle of local speciality                         22\r\n"
                "  2)  Unlimited   A bottle of firebreather                             56\r\n"
                "  3)  Unlimited   A bottle of ale                                      11\r\n"
                "  4)  Unlimited   A bottle of beer                                     22\r\n"
                "  5)  Unlimited   A barrel of beer                                    339\r\n"
shop("list") [different shop] → "  1)  Unlimited   A danish pastry                                       7\r\n"
                                  "  2)  Unlimited   A bread                                              14\r\n"
                                  "  3)  Unlimited   A waybread                                           72\r\n"
shop("list") [general store]  → "  1)  Unlimited   A cashcard                                         1542\r\n"
                                  "  2)  Unlimited   A box                                                77\r\n"
                                  "  3)  Unlimited   A bag                                                30\r\n"
                                  "  4)  Unlimited   A lantern                                            77\r\n"
                                  "  5)  Unlimited   A torch                                              15\r\n"
shop("buy", "local speciality") → "The bartender tells you, 'That'll be - say 22 coins.'\r\nYou now have a bottle.\r\n\r\n62H 100M 85V (motd) > "
```

Takeaways that shape the design:

- **Hunger/thirst are plain, always-present lines** in `check("score")` —
  `"You are hungry."` / `"You are thirsty."` appear verbatim whenever true,
  absent when false. No inference needed, same reliability class as §4 of
  `world_state_db_plan.md`'s status-bar parsing.
- **A fountain can be drunk from directly by name**, with no need to have
  detected one in advance — `consume_item(item="fountain", mode="drink")`
  either succeeds ("You drink the clear water.") or the MUD itself says it
  doesn't see one. That's a free, zero-guessing first move whenever
  thirsty, in the same "let the server's own response be the source of
  truth" spirit as `check_door`.
- **`shop("list")` is a free, tabular, and complete signal** — costs no
  gold, no inventory change, and reveals the whole stock in one call.
  **§4a: `shop("buy", ...)` turned out not to be usable for item identity
  at all** — see below, this plan's write-back hook only fires on `list`.
- **Real stock samples split cleanly into food / drink / neither**: "A
  danish pastry" / "A bread" / "A waybread" → food; "A bottle of X" / "A
  barrel of X" → drink; "A cashcard" / "A box" / "A bag" / "A lantern" / "A
  torch" → neither. A small keyword classifier (§5) handles this — same
  "best-effort, flagged as provisional" caveat `world_state_db_plan.md` §4
  already applies to combat-text parsing, extend the keyword list as more
  shops get sampled.
- The shop listing's line format is fixed-width and mechanical:
  `  N)  <stock>   <Item name>                    <cost>` — reliably
  regex-extractable without ambiguity.

## 3. Scope for v1 — and what's deliberately out

**In scope:**
- Detecting hunger/thirst from `check("score")`, and skipping all further
  work entirely when neither is true (no wasted calls).
- Attempting a direct fountain drink as a free first move when thirsty.
- Checking current inventory for something already consumable, and
  **reporting it back for the model to decide** whether to consume it —
  per your original ask, this tool recommends, it does not auto-eat/drink
  on the model's behalf (the one exception is the fountain attempt above,
  since that costs nothing and risks nothing — see §7 open question 1).
- When nothing's available locally, querying `world.db` for the nearest
  **already-discovered** source (a shop known to sell it, or a location
  it's been picked up at before) and reporting how far away it is —
  never fabricating a source that hasn't actually been observed, same
  "don't invent a path through unmapped territory" rule `goto_tool_plan.md`
  §0 uses for routes.
- New write-back hook: `shop("list")` results parsed and recorded into
  the existing `items`/`location_items` tables, tagged with `item_type`
  where the name classifies cleanly as food or drink (§4a: `buy` dropped
  from this hook after testing showed why it can't safely share it).

**Out of scope, explicitly, for v1:**
- Auto-consuming inventory items without the model's go-ahead (your
  explicit requirement).
- Auto-buying anything — spending gold is still the model's call; this
  tool only reports where something's known to be sold. Actually walking
  there and buying is left to the model calling `go_to` + `shop("buy", ...)`
  itself.
- Tracking live player inventory in `world.db` — inventory stays a
  live-only check (`check("inventory")`) each time this tool runs, same as
  today. Only *shop stock* (what a location sells) gets persisted, not what
  the player is currently carrying.
- Modeling affordability (whether the player has enough gold) — the report
  can mention gold-on-hand and cost if easy, but deciding whether it's
  worth the price stays with the model.

## 4. New write-back hook: `shop`

`world/__init__.py`'s `observe()` dispatch table gets one more case,
alongside the existing `get_item`/`equip_item`/`attack` etc. entries:

```python
elif name == "shop" and args.get("action") == "list":
    _observe_shop(text)
```

```python
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
```

`parser.parse_shop_stock(text)` extracts every item name from a `shop("list")`
result — the whole table in one call, multiple names per round-trip, the
best signal-per-round-trip ratio in this whole plan. Regex matches the
fixed-width table row shape from §2's real samples:

```python
_SHOP_LINE_RE = re.compile(r"^\s*\d+\)\s+\S+\s+(.+?)\s+\d+\s*$", re.MULTILINE)
```

### 4a. Correction found before writing any code: `buy` can't share this hook

The original draft above assumed `shop("buy", ...)` transcripts matched
the same tabular line shape and could feed the same parser as `list`.
Testing that regex against real `shop("buy", ...)` transcripts *before*
writing `_observe_shop` (same discipline as this whole DB effort's "ground
it in real output, don't guess" rule) showed it matches nothing — a buy
confirmation isn't tabular at all, it's `"You now have a bottle."` /
`"You now have a danish pastry."`. Worse than just a different shape: it's
**strictly less specific** than the listing. A bar's `list` distinguishes
"A bottle of local speciality" from "A bottle of firebreather" from "A
bottle of ale" — but buying any of them produces the identical generic
confirmation, `"You now have a bottle."` Parsing identity from `buy` would
have silently collapsed three distinct drinks into one row keyed on the
word "bottle" alone. Decision: drop `buy` from the write-back hook
entirely rather than build something that writes bad data. `list` is free
(no gold, no inventory change) and strictly more specific, so nothing is
lost by relying on it exclusively — a model that only ever buys without
ever listing first simply won't seed that shop's stock into the DB, same
"no exits scanned yet, no route yet" tradeoff `go_to` already accepts
elsewhere.

`parser.classify_consumable(name)` — small keyword table, same "best-effort,
flagged provisional" spirit as the combat-phrase and condition-ladder
tables already in `parser.py`:

```python
_FOOD_KEYWORDS = ("bread", "pastry", "cake", "pie", "meat", "fruit", "cheese")
_DRINK_KEYWORDS = ("bottle", "barrel", "water", "ale", "beer", "wine", "juice")

def classify_consumable(name):
    lowered = name.lower()
    if any(k in lowered for k in _FOOD_KEYWORDS):
        return "food"
    if any(k in lowered for k in _DRINK_KEYWORDS):
        return "drink"
    return None  # e.g. "a cashcard", "a box", "a lantern" -- correctly unclassified, not guessed
```

This reuses `items`/`location_items` exactly as they already exist —
**no schema change**, unlike `zone_name`'s addition in `goto_tool_plan.md`
§5. A shop's stock is just another `location_items` row, no different in
shape from an item seen on the ground.

## 5. Distance-to-source lookup

Reuses `pathfind.py`'s existing BFS/reachability machinery rather than
inventing new plumbing — same pattern as `goto_tool_plan.md` §5's
town-anchor fallback:

```python
def find_nearest_supply(conn, current_location_id, item_type):
    """Nearest reachable location known to carry an item of item_type
    (goto_tool_plan-style BFS distance, not guessed). Returns
    (location_id, location_name, item_name, hops), or None if nothing's
    been discovered yet."""
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
```

Verified live against the real shared `world.db`, in both languages:
walking to and listing the stock at "The Bakery" (38 hops from the Temple
of Midgaard) seeded `danish pastry`/`bread`/`waybread` as `food`-typed
`location_items` rows there; `find_nearest_supply(conn, <temple_id>,
"food")` then correctly returned `(<bakery_id>, "The Bakery", "danish
pastry", 38)` — matching the real walk distance exactly — while
`find_nearest_supply(conn, <temple_id>, "drink")` correctly returned `None`
(no drink source had been listed/discovered yet in that session).

Same "never fabricate a route" discipline as `go_to`: if nothing's
reachable (or nothing's been discovered at all), the tool says so plainly
rather than guessing a direction.

## 6. Tool surface

One new tool, no arguments — it reads score/inventory/position itself,
the same way `go_to` reads `current_location_id` itself rather than making
the model supply it:

```python
check_needs() -> str
```

```python
def check_needs():
    err = guard()
    if err:
        return err

    score_text = send_cmd(p.info_self("score"))
    hungry = "you are hungry" in score_text.lower()
    thirsty = "you are thirsty" in score_text.lower()
    if not hungry and not thirsty:
        return "Not hungry or thirsty -- no action needed."

    notes = []

    if thirsty:
        fountain_result = send_cmd(p.consume("drink", "fountain"))
        if "you drink" in fountain_result.lower():
            thirsty = False
            notes.append(f"Drank from a fountain here. {fountain_result.strip()}")

    if hungry or thirsty:
        inv_lines = parser.parse_inventory(send_cmd(p.info_self("inventory")))
        have_food, have_drink = _match_inventory_to_needs(inv_lines)
        conn = world.connection()

        if hungry and have_food:
            notes.append(f"You are hungry and already have {have_food} -- consume it?")
        elif hungry:
            notes.append(_supply_note(conn, "food", "hungry"))

        if thirsty and have_drink:
            notes.append(f"You are thirsty and already have {have_drink} -- consume it?")
        elif thirsty:
            notes.append(_supply_note(conn, "drink", "thirsty"))

    return "\n".join(notes)


def _supply_note(conn, item_type, need_word):
    current_id = world.current_location_id()
    if current_id is None:
        return f"You are {need_word} and have nothing on hand; current location unknown -- call look first."
    found = pathfind.find_nearest_supply(conn, current_id, item_type)
    if found is None:
        return f"You are {need_word}, have nothing on hand, and no known {item_type} source has been discovered yet."
    loc_id, loc_name, item_name, hops = found
    return (f'You are {need_word} and have nothing on hand. Nearest known {item_type} source: '
            f'"{loc_name}" ({hops} hop{"s" if hops != 1 else ""} away, sells "{item_name}").')
```

`_match_inventory_to_needs` matches inventory line text against
`classify_consumable()` the same way, so an already-owned "a bread" or "a
bottle" is recognized without needing a DB lookup — the DB is only
consulted once nothing's on hand, same "check locally before falling back
to a lookup" ordering `go_to`'s resolver already uses.

Worst case this is 3 MUD round-trips (score, fountain attempt, inventory)
behind **one** LLM tool call — same value proposition as `go_to`: collapse
many mechanical MUD interactions into a single model decision point,
instead of the model spending a turn per check.

## 7. Open questions — resolved with the plan's own leanings

You said "let's implement it" without weighing in on each item
individually, so these shipped with the recommended default from the
original draft, same as `goto_tool_plan.md`'s items left to discretion:

1. **Auto-drinking the fountain without asking** (§3/§6): shipped as the
   one exception to "always ask before consuming" — free, reversible,
   directly fixes the flagship Week 2 incident. Verified live: on a
   successful drink it's silently resolved and removed from `notes`;
   nothing is asked about it.
2. **`shop("list")` write-back on every listing**: superseded by §4a —
   the question of restricting write-back to `buy` instead turned out to
   be moot, since `buy`'s confirmation text can't safely identify items at
   all (§4a). `list` is the only source, always written back when
   observed.
3. **Keyword classifier coverage** (§4/§5): shipped grounded only against
   the shops actually sampled (a bar, a bakery, a general store) —
   `_FOOD_KEYWORDS`/`_DRINK_KEYWORDS` in `parser.py` (mirrored in
   `parser.rb`). Extend opportunistically as more shops get visited, same
   as the combat-phrase and condition-ladder tables.
4. **Tool name**: shipped as `check_needs()`.

## 8. Where the code lives

Mirrors the existing layout, no new files needed beyond what
`goto_tool_plan.md` §8 already established:

```
week3_capable/
  python/boukensha/
    world/
      __init__.py     # add _observe_shop() + "shop" case in observe()'s dispatch table
      parser.py        # add parse_shop_stock(), classify_consumable()
      pathfind.py       # add find_nearest_supply()
    tools/
      mud.py             # add check_needs() + registration, alongside go_to
  ruby/lib/boukensha/
    world/               # mirror all four changes above
    tools/
      mud.rb
  fixtures/
    parser_cases.yaml    # add shop-listing + classify_consumable fixture cases (§6b's shared-fixture discipline)
```

## 9a. Follow-up: `return_to_start`

Your question: after `go_to`-ing to a shop/fountain to resolve hunger or
thirst, can it head back afterward? Yes, and it needed almost no new
machinery — it reuses `go_to`'s BFS/hop-execution pattern directly.

- **Session state**: a small mutable box (`_return_point` in Python,
  `return_point` in Ruby) remembering the location right before the most
  recent `go_to` actually started walking. Deliberately just "last go_to's
  origin," not a full history stack — covers the single-errand case
  ("go get food, come back") without building breadcrumb-trail navigation
  nobody's asked for.
- **Recorded only once a real walk is about to happen** — after all of
  `go_to`'s own failure/no-op checks pass, right before its hop loop
  starts. A failed or already-there `go_to` call never clobbers a good
  return point.
- **New tool, no args**: `return_to_start()` — walks the BFS route back to
  that remembered point using the exact same move/observe/failure-check
  loop `go_to` already uses, just targeting a known id instead of
  resolving one from text.
- **Why two tool calls, not one automatic round trip**: buying/eating
  happen *between* arrival and return, and those are model decisions —
  `go_to` there, do the errand, then separately call `return_to_start()`.
  Can't be collapsed into one call without removing the model's say over
  the middle part.
- **Known simplification**: `return_to_start`'s hop loop is its own
  separate copy of `go_to`'s loop rather than a shared helper — a
  same-day addition deliberately avoided refactoring the already
  live-verified `go_to` code. Worth factoring out if a third caller ever
  needs the same loop.
- **`pathfind.find_reachable_duplicate(conn, current_location_id, location_id)`**
  (added during live testing, §9b) — when the exact remembered
  `location_id` isn't BFS-reachable, looks for another `locations` row
  with the same name that IS reachable and routes there instead, same
  duplicate-row tradeoff `go_to`'s own disambiguation already handles,
  just reached from a raw id instead of a name query.

### 9b. Two real bugs found and fixed via live round-trip testing

The first round-trip attempt surfaced two genuine issues, neither of them
hypothetical — both confirmed against the real server, both fixed, both
re-verified clean afterward:

1. **`move_failed()` missed a real failure phrase.** The test character was
   still resting when `go_to` tried to walk it; CircleMUD refused with
   `"Nah... You feel too relaxed to do that.."` — text the existing
   `_MOVE_FAILURE_RE`/`MOVE_FAILURE_RE` (grounded only in `"alas, you
   cannot go that way"` and similar, from `goto_tool_plan.md`) didn't
   recognize. Result: `go_to` reported a successful 1-hop walk and
   advanced its internal position pointer, while the character had not
   actually moved at all — confirmed by a follow-up `look` showing the
   original room. Fixed by adding `"too relaxed to do that"` to the
   regex alternation in both `world/__init__.py` and `observer.rb`, with
   the real sampled phrase as the grounding text (same discipline as
   every other phrase table in this codebase). This bug predates
   `return_to_start` entirely — it affects plain `go_to` too — it just
   happened to surface here first.
2. **`return_to_start` had no fallback for a stranded exact-id target.**
   After standing back up and re-walking for real, the return route failed
   outright (`"no discovered route back..."`) even though the character
   was one real hop from a room with the exact right name — because the
   specific `location_id` remembered as "start" was a duplicate row
   (`world_state_db_plan.md` §5's accepted tradeoff: separate sessions
   each mint their own row for what's physically the same "Grubby Inn"),
   and the actually-recorded `south` edge from the nearby room pointed at
   a *different* duplicate than the one remembered. Fixed with
   `find_reachable_duplicate()` (§9a) — same fallback shape as `go_to`'s
   existing disambiguation, just working from an id instead of a name.
   A follow-up idempotence check (`return_to_start` again while already
   there) then exposed a small message bug in the fix itself — an empty
   path from the duplicate fallback fell through to the hop loop instead
   of the `"Already back at the starting point."` short-circuit, producing
   `"Walked 0 rooms () back to the starting point."` — fixed by checking
   for an empty path after the fallback resolves, same as the exact-id
   check already does.

Final state, verified live end-to-end in one process (Python): `go_to`
walked 2 real hops to "Wall Road", `return_to_start` walked the correct 2
hops back (room text and mob state matching the original room exactly),
and calling `return_to_start` again immediately produced the clean
`"Already back at the starting point."` message. Ruby re-checked
independently against the same live server/DB for `_observe_shop`,
`check_needs`, and `find_nearest_supply` earlier in this session;
`return_to_start` itself is implemented identically and syntax-checked but
its specific round-trip wasn't independently re-run in Ruby this session.

## 9. Implemented

Built in this order, matching the original plan exactly: `parser.parse_shop_stock()`
+ `classify_consumable()` + `parse_inventory()` first (fixture cases added
to `parser_cases.yaml`, 17/17 passing in both languages), then
`_observe_shop()`'s dispatch hook (`list` only, per §4a), then
`pathfind.find_nearest_supply()`, then `check_needs()` wired to `send_cmd`
in both `tools/mud.py` and `tools/mud.rb`. Verified live per the standing
rule for MUD-touching features: `check_needs()` correctly detected real
hunger/thirst and matched real inventory items in both languages against
the same live server; `find_nearest_supply()` correctly resolved a
real shop location seeded moments earlier via a live `shop("list")` call,
at the exact hop count a real `go_to` walk to that location produced.
