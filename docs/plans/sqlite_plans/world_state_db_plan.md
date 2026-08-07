# World-State SQLite DB — Design Plan (week3_capable)

Status: **APPROVED — ready to implement.** No code has been written yet. This
document covers schema, write-back design, migration approach, and
visualization approach per your request. All open questions from §11 are
now resolved (see "Decisions" at the end of that section); the recommended
option was taken in every case.

## 1. Motivation (from Week 2 telemetry)

From `docs/journal/2_week2.md`: the Honeycomb traces showed the agent burning
65,450 tokens checking each empty water bottle before walking to the fountain,
68,289 tokens backtracking through the sewer because it had no memory of
where it had already been, and leaving gold sitting untouched because it
never revisited the trace where it was found. The stated next step was
exactly this: an SQLite DB of locations, mobs (friend/enemy), items, area
type, and exits, so the agent can *check* state instead of *re-discovering*
it by trial and error.

That journal also draws a conclusion I'm treating as a hard constraint on
this design: **explicit, deterministic bookkeeping beats asking the model to
infer/remember things**, because inference costs tokens and is unreliable.
Concretely, that means the write-back path should not depend on the LLM
remembering to call a "please record what I just saw" tool on every turn —
it should happen automatically, as a side effect of tools it's already
calling (`look`, `move`, `check`, `get_item`, ...), with zero added LLM
round-trips.

## 2. Where this lives — both languages, one DB

You want both Ruby and Python playing against this world state, not just
Python. That's workable because SQLite's file format is language-agnostic —
Ruby's `sqlite3` gem and Python's stdlib `sqlite3` are both just bindings
around the same C library, so the exact same `.db` file and the exact same
`schema.sql` serve both. What can't be shared directly is the *logic*
(regex parsing, get-or-create calls) — Ruby can't call a Python function or
vice versa without standing up an IPC/service layer, which is disproportionate
here. So the design is: **one shared schema + one shared DB file, two
parallel implementations of the write-back module**, mirroring how the rest
of the repo already keeps a `ruby/` and `python/` port of every module:

```
week3_capable/
  schema.sql                    # single shared DDL — both languages load this file, neither embeds its own copy
  data/
    world.db                    # gitignored runtime state, shared by both languages
  fixtures/
    parser_cases.yaml           # shared raw-text -> expected-parsed-output cases, loaded by both test suites (see §6b)
  python/
    boukensha/
      world/
        __init__.py
        db.py                    # connection + PRAGMA setup, loads ../../../schema.sql
        store.py                 # get_or_create_* data-access module
        parser.py                # raw MUD text -> structured signals
      tools/
        mud.py                   # existing tool wrappers; dispatch hook added here
  ruby/
    lib/
      boukensha/
        world/
          db.rb                  # connection + PRAGMA setup, loads ../../../../schema.sql
          store.rb                # get_or_create_* data-access module (mirrors store.py)
          parser.rb               # raw MUD text -> structured signals (mirrors parser.py)
        registry.rb               # existing dispatch; hook added here (see §6a)
  scripts/
    visualize_world.py           # standalone map renderer (graphviz) — Python only, reads the DB read-only
```

Why `schema.sql` sits at the `week3_capable/` root rather than inside either
language's tree: it's the one artifact that must never drift between the two
implementations, so it isn't "owned" by either language — both `db.py` and
`db.rb` read the same file at startup and run it with `CREATE TABLE IF NOT
EXISTS`, so whichever agent runs first bootstraps it and the other just
finds it already there.

`week3_capable/data/world.db` (and `*.db-journal`/`*.db-wal`/`*.db-shm`) get
added to a `week3_capable/.gitignore` — still runtime state, not source, so
still excluded from git regardless of which language wrote to it last.

### 2a. Bootstrapping the package roots

Resolves open question #3. `week3_capable/python/boukensha/` and
`week3_capable/ruby/lib/boukensha/` start as a **full one-time copy** of
`week1_baseline/python/12_context/boukensha/` and
`week1_baseline/ruby/12_context/lib/boukensha/` respectively — not just the
`world/` subpackage, the entire framework (`agent.py`/`.rb`, `client.py`/`.rb`,
every backend, `registry.py`/`.rb`, `tools/`, `mcp_client.py`,
`mcp_servers/`, `logger.py`/`.rb`, `telemetry.py`/`conversation_span_processor.rb`,
`tui.py`/`.rb`, `repl.py`/`.rb` — everything currently in `12_context`), since
that's what `12_context` already is: a complete, working agent, not a
step-specific diff.

After that copy, the two trees are **fully independent** — no shared imports,
no path back into `week1_baseline`, no automatic sync in either direction.
Two things carry over as file references rather than copies, since they're
already shared, language-agnostic assets outside any step's `boukensha/`
tree:
- `week0_explore/mud_manager/` — same `sys.path` insert pattern
  (`tools/mud.py`) that every step from 10 onward already uses; Ruby's
  Gemfile `path:` dependency needs its relative depth adjusted for the new
  location (`week1_baseline/ruby/12_context/Gemfile` uses
  `"../../../week0_explore/mud_manager"`; `week3_capable/ruby/Gemfile` is one
  level shallower, so `"../../week0_explore/mud_manager"`).
- `.boukensha/settings.yaml`/`.env` at the repo root — unchanged, both copies
  read the same config the same way `12_context` already does.

**Why a separate directory instead of extending `12_context` in place** (the
way `week2`'s OpenTelemetry work was added directly into `12_context` — see
`docs/journal/2_week2.md`): this addition is substantially larger (schema,
dual-language write-back, parser, migrations, a visualization script) than
telemetry hooks were, and `week1_baseline` is meant to represent a
checkpoint. Forking to `week3_capable` keeps `12_context` intact as a known-
working revert point if anything about the world-state design needs to be
rolled back, at the cost of the two `boukensha/` trees diverging from this
point forward with no shared maintenance.

## 3. Schema DDL

Single file, single `.db`, shared by both languages (per §2). `PRAGMA
foreign_keys = ON` is set on every connection, in both `db.py` and `db.rb`
(SQLite defaults this off per-connection, so it has to be set at connect
time in *each* language's connection helper, not just once at creation time
— one language setting it doesn't set it for the other's connections).

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS locations (
    location_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,                 -- NULL until the placeholder is filled in
    area_type       TEXT,                 -- town | sewer | castle | dungeon | ...
    description     TEXT,
    visited         INTEGER NOT NULL DEFAULT 0 CHECK (visited IN (0,1)),
    first_seen_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS exits (
    location_id         INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    direction            TEXT NOT NULL,   -- normalized: north|south|east|west|up|down|...
    leads_to_location_id INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, direction)
);

CREATE TABLE IF NOT EXISTS mobs (
    mob_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL UNIQUE,   -- see §5 on why name is the identity key
    disposition          TEXT CHECK (disposition IN ('friendly','enemy','neutral') OR disposition IS NULL),
    hp                   INTEGER,
    level                INTEGER,
    is_dialogue_enabled  INTEGER CHECK (is_dialogue_enabled IN (0,1) OR is_dialogue_enabled IS NULL)
);

CREATE TABLE IF NOT EXISTS location_mobs (
    location_id   INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    mob_id        INTEGER NOT NULL REFERENCES mobs(mob_id) ON DELETE CASCADE,
    condition     TEXT CHECK (condition IN (
                      'excellent', 'scratches', 'small_wounds', 'quite_a_few_wounds',
                      'big_wounds', 'pretty_hurt', 'awful'
                  ) OR condition IS NULL),   -- latest qualitative reading; see §8's cold-start fallback
    last_seen_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (location_id, mob_id)
);

CREATE TABLE IF NOT EXISTS items (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    item_type  TEXT CHECK (item_type IN ('gold','armor','weapon','food','drink','misc') OR item_type IS NULL),
    level      INTEGER
);

CREATE TABLE IF NOT EXISTS location_items (
    location_id  INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    item_id      INTEGER NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
    quantity     INTEGER,
    PRIMARY KEY (location_id, item_id)
);

CREATE TABLE IF NOT EXISTS weapons (
    weapon_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE   -- any damage source: a melee weapon ("short sword"), a
                                       -- bare-handed row ("fists"), a skill ("kick"), or a spell/
                                       -- magic item name — see §8
);

CREATE TABLE IF NOT EXISTS mob_weapon_stats (
    mob_id             INTEGER NOT NULL REFERENCES mobs(mob_id) ON DELETE CASCADE,
    weapon_id          INTEGER NOT NULL REFERENCES weapons(weapon_id) ON DELETE CASCADE,
    hits_landed_total  INTEGER NOT NULL DEFAULT 0,   -- running count across every fight with this pairing
    kills_total        INTEGER NOT NULL DEFAULT 0,   -- how many of those fights ended in a kill
    PRIMARY KEY (mob_id, weapon_id)
);

CREATE TABLE IF NOT EXISTS features (
    feature_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_type         TEXT NOT NULL,   -- door | chair | lever | ...
    is_locked             INTEGER CHECK (is_locked IN (0,1) OR is_locked IS NULL),
    is_lockpickable        INTEGER CHECK (is_lockpickable IN (0,1) OR is_lockpickable IS NULL),
    available_actions      TEXT           -- JSON array, e.g. '["open","sit","pull"]'
);

CREATE TABLE IF NOT EXISTS location_features (
    location_id  INTEGER NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
    feature_id   INTEGER NOT NULL REFERENCES features(feature_id) ON DELETE CASCADE,
    PRIMARY KEY (location_id, feature_id)
);

CREATE INDEX IF NOT EXISTS idx_exits_leads_to ON exits(leads_to_location_id);
```

Notes on deviations from the literal spec, both flagged for your sign-off:

- `mobs.name`, `items.name`, and `weapons.name` are declared `UNIQUE` —
  required for the get-or-create lookup to be a single indexed query instead
  of a scan, and matches "look up by name" in your write-back spec. This is
  also what makes "no duplicate rat rows" work for mobs: every sighting of a
  "sewer rat" resolves to the same one `mobs` row via this lookup, and
  `location_mobs` is just the join between that one row and each place it's
  been seen — see §8 for why the same identity model applies to weapons.
- `mob_weapon_stats` uses a composite `(mob_id, weapon_id)` primary key for
  the same reason `location_items`/`location_mobs` do — the pairing itself
  is the natural key, and it makes "add to this pairing's running total"
  a plain upsert instead of a lookup-then-decide.
- `locations.name` is **not** unique — see §5, this is the one place the
  spec's "if location_id/name not in locations" needs a real identity
  strategy, because MUD room names are not unique (mazes/sewers often reuse
  room names on purpose).
- Junction tables use composite primary keys `(location_id, X_id)` instead of
  a separate surrogate id — that composite *is* the natural key ("linked or
  not"), and it makes "insert if not already linked" a plain `INSERT OR
  IGNORE`.

## 4. Grounding the parser in real MUD output

I pulled actual tool-call results from `.boukensha/sessions/*.jsonl` to check
what the raw text actually looks like, rather than guessing. This matters
because it changes what's reliably parseable vs. what would be guessing:

```
look  → "\x1b[0;33mThe Small Passage\x1b[0m\r\n   You are standing in a small
          passage leading north and south.  There\r\nis also an exit to the
          west...\r\n\x1b[0;36m[ Exits: n s w ]\x1b[0m\r\n\x1b[0;33mPeter, the
          Captain of the Royal Guard, walks around inspecting.\r\n\x1b[0m\r\n
          72H 100M 92V (motd) > "

check("exits") → "Obvious exits:\r\nsouth - The Training Room\r\n\r\n
                   72H 100M 93V (motd) > "

get_item → "You get a little pile of gold coins from the corpse of the sewer
             rat.\r\nThere were 50 coins.\r\n\r\n62H 100M 73V (motd) > "

consider → "You would need some luck!\r\n\r\n62H 100M 68V (motd) > "

attack (landed) → "You barely pierce the sewer rat.\r\n\x1b[0;31mThe sewer
                    rat tries to hit you but you easily avoid the blow.\r\n
                    \x1b[0m\r\n62H 100M 88V (motd) > "

attack (missed)  → "\x1b[0;33mYou try to pierce the sewer rat but pierce the
                     air instead!\r\n\x1b[0mThe sewer rat tickles you as it
                     hits you.\r\n\x1b[0m\r\n61H 100M 83V (motd) > "

attack (kill)    → "\x1b[0mThe small bat is dead!  R.I.P.\r\nYou receive 34
                     experience points.\r\nYour blood... \r\n\r\n72H 100M
                     92V (motd) > "

consider (condition) → "This creature is fairly large for a rat... The
                         sewer rat has some small wounds and bruises.\r\n
                         \r\n61H 100M 83V (motd) > "

wield → "You wield a short sword in your right hand.\r\n\r\n72H 100M 92V
          (motd) > "
```

The last four of these ground §8's weapon-aware hit tracking: a landed hit,
a miss, a kill, a qualitative condition reading, and a weapon-change are all
distinguishable by fixed phrasing, same as everything else in this section.

Takeaways that shape the design:

- **ANSI color codes wrap every semantically-colored line** (`\x1b[0;33m...
  \x1b[0m` for title/mob lines, `\x1b[0;36m...` for the exits line). Stripping
  `\x1b\[[0-9;]*m` is the first, unconditional step.
- Every response ends in a stable status-bar prompt, `\d+H \d+M \d+V \([^)]*\)
  > `. That's a reliable delimiter for "end of this response" and also a free,
  always-available read of **the player's own** HP/mana/movement — not a
  mob's.
- `look`'s exits line (`[ Exits: n s w ]`) gives **direction letters only, no
  destination names**. `check("exits")` gives **full direction words with the
  destination room's name** (`south - The Training Room`). These need
  different regexes and produce different confidence levels — `check("exits")`
  is strictly more useful and should be preferred whenever the agent calls it,
  but `look`'s compact exits line is what's available on every single room
  entry, so both need handling.
- Mob-presence lines during `look` are free-form sentences ("Peter, the
  Captain of the Royal Guard, walks around inspecting.", "Jochem the Royal
  Guard sits here, off duty.") in the *same* color code as the room title.
  There's no delimiter distinguishing "this is a mob line" from "this is more
  room description" other than position (after the exits line) and a
  loose "proper-noun + descriptive-verb" shape. This will be **best-effort
  regex/heuristic, not a reliable parse** — see §6.
- Numeric mob HP does not appear to be exposed by CircleMUD to the client at
  all in normal play (`examine`/`consider` return prose like "is in excellent
  condition" or "You would need some luck!", never a number). This directly
  informs the HP question you asked about — see §7.
- Gold pickups *do* give an exact, reliably-parseable quantity ("There were 50
  coins.") — this is a case where `location_items.quantity` can be populated
  with real confidence.

## 5. Location identity & the "am I somewhere new" problem

The spec says: *"if location_id/name not in locations, insert it... if
already known, just update visited/last_seen."* The problem: CircleMUD gives
the client no stable room ID, and room **names are not unique** — sewers and
mazes routinely reuse "A Dark Tunnel" for multiple distinct rooms specifically
so mapping is hard. Matching purely on `name` (or even `name` + description)
will silently merge distinct rooms that happen to share text, which is worse
than the token-waste problem this whole feature exists to fix (the agent
would now confidently believe it already knows a room it's never seen).

**Recommended approach: track current location as a graph pointer, and only
fall back to text-matching when the pointer is unknown.**

- The write-back module keeps an in-memory `current_location_id` for the
  session (not new schema — just module state, since it's transient and
  reconstructable from the exits graph).
- On `check("exits")` or the `look` exits line at the **current** location:
  for each direction seen, `INSERT OR IGNORE` an `exits` row. If the
  direction is new, first create a **placeholder** `locations` row
  (`name=NULL, area_type=NULL, visited=0`) as the destination, per the spec.
  If `check("exits")` gave a destination name, we can actually fill that
  placeholder's `name` immediately — no need to wait for a visit — that's
  strictly more informative than the letter-only `look` exits line.
- On `move(direction)` succeeding: look up `exits(current_location_id,
  direction)`. If a row exists, the destination is **known by graph position,
  full stop** — no text matching needed. Set `current_location_id` to
  `leads_to_location_id`, mark it `visited=1`, and fill in `name`/
  `description`/`area_type` from the room text that just came back (whether
  it was a placeholder or already fully known). If no row exists yet (an
  exit not previously scanned), fall through to the text-matching path below,
  create the destination, and backfill the `exits` row.
- **Text-matching fallback** — used only when `current_location_id` is
  unknown or stale (session start, after `recall`/teleport, after death and
  respawn, or an unscanned exit as above): match the incoming `(name,
  description)` against existing `locations` rows. Exact match on both →
  treat as a revisit. No match → insert a new row. I'm deliberately **not**
  trying to be clever about fuzzy/partial matches here — an occasional
  duplicate row for a genuinely-revisited room is a much cheaper mistake than
  silently merging two different rooms into one.
- Detecting "the pointer just went stale" (death/recall/teleport) is itself
  text-pattern matching against known CircleMUD phrases (e.g. "You have been
  killed", "You suddenly feel a wrenching sensation..."). I'd build this
  list incrementally from what actually shows up in play rather than trying
  to enumerate it upfront.

This resolves the ambiguity in the spec's "if location_id/name not in
locations" instruction — the identity check is graph-position-first,
name-matching-second, not name-matching-only.

## 6. Write-back module design — implemented twice, to one shared contract

Since Ruby and Python can't call into each other, `parser.{py,rb}` and
`store.{py,rb}` are each implemented natively per language, both against the
*same contract*: this document (§4, §5, §7) is that contract. Concretely:

**`world/parser.{py,rb}`** — pure functions, no DB access in either. Take
raw tool-result strings + the tool name/args that produced them, return
plain data (a dataclass/dict in Python, a `Struct`/Hash in Ruby):
`ParsedRoom(name, description, exit_directions, mob_lines, item_lines)`,
`ParsedExits(direction -> destination_name)`, `ParsedPickup(item_name,
quantity)`, etc. Returns `None`/empty on anything it can't confidently parse
in both — neither guesses. Since both languages are parsing byte-identical
text from the same CircleMUD server (§4's fixture strings apply equally to
both), the regex patterns translate almost mechanically between Python `re`
and Ruby `Regexp` — the risk isn't that the syntax is hard to port, it's that
the two copies quietly diverge over time as one gets a heuristic tweak the
other doesn't. §6b below is the guard against that.

**`world/store.{py,rb}`** — the get-or-create data-access module, one
function family per entity, matching your spec exactly. Python:

```python
def get_or_create_location(conn, *, name=None, area_type=None, description=None, visited=False) -> int: ...
def touch_location(conn, location_id, **updates) -> None:            # update name/description/area_type/visited/last_seen_at, only overwriting non-None fields
def get_or_create_exit(conn, location_id, direction, leads_to_location_id) -> None:  # INSERT OR IGNORE
def get_or_create_mob(conn, name, *, disposition=None, hp=None, level=None, is_dialogue_enabled=None) -> int: ...
def link_mob(conn, location_id, mob_id) -> None:                     # INSERT OR IGNORE + last_seen_at bump
def get_or_create_item(conn, name, *, item_type=None, level=None) -> int: ...
def link_item(conn, location_id, item_id, quantity=None) -> None: ...
def get_or_create_feature(conn, feature_type, *, is_locked=None, is_lockpickable=None, available_actions=None) -> int: ...
def link_feature(conn, location_id, feature_id) -> None: ...
```

Ruby, same signatures in Ruby idiom (keyword args, `nil` instead of `None`):

```ruby
def get_or_create_location(conn, name: nil, area_type: nil, description: nil, visited: false) -> Integer
def touch_location(conn, location_id, **updates) -> nil
def get_or_create_exit(conn, location_id, direction, leads_to_location_id) -> nil   # INSERT OR IGNORE
def get_or_create_mob(conn, name, disposition: nil, hp: nil, level: nil, is_dialogue_enabled: nil) -> Integer
def link_mob(conn, location_id, mob_id) -> nil
def get_or_create_item(conn, name, item_type: nil, level: nil) -> Integer
def link_item(conn, location_id, item_id, quantity: nil) -> nil
def get_or_create_feature(conn, feature_type, is_locked: nil, is_lockpickable: nil, available_actions: nil) -> Integer
def link_feature(conn, location_id, feature_id) -> nil
```

Every "create" function in both does `SELECT ... WHERE name = ?` first (or,
for locations, the graph-pointer logic from §5), and only falls through to
`INSERT` on a miss — no inline SQL scattered in either language's agent/tool
code, per your requirement. This half of the port is low-risk: it's 1-2 SQL
statements per function, mechanical to keep in sync.

### 6a. Hook point in each language

**Python** — `Registry.dispatch()` in
`week1_baseline/python/12_context/boukensha/registry.py`, which already sits
between "tool ran" and "result went back to the model" for *every* tool call:

```python
def dispatch(self, name, args=None):
    args = args or {}
    tool = self.context.tools.get(str(name))
    if tool is None:
        raise UnknownToolError(f"No tool registered as '{name}'")
    result = tool.block(**args)
    world.observe(name, args, result)   # <-- new: no-op for tools it doesn't recognize
    return result
```

**Ruby** — I checked `week1_baseline/ruby/12_context/lib/boukensha/registry.rb`,
and it's the structurally identical seam: `Registry#dispatch` also computes
`result = tool.block.call(...)` and returns it, inside an OpenTelemetry span.
Same hook, same spot:

```ruby
def dispatch(name, args = {}, tool_call_id: nil)
  Boukensha.tracer.in_span('tool.dispatch') do |span|
    # ...existing span attribute setup...
    tool = @context.tools[name.to_s]
    raise UnknownToolError, "No tool registered as '#{name}'" unless tool

    result = tool.block.call(**args.transform_keys(&:to_sym))
    World.observe(name, args, result)   # <-- new: no-op for tools it doesn't recognize
    # ...existing span attribute setup for result...
    result
  end
end
```

In both, `observe`/`World.observe` pattern-matches on tool name (`look`,
`check`, `move`, `get_item`, `examine`, `check_door`/`open_door`, ...), calls
the matching parser function, then calls the matching store function(s).
Zero new tools exposed to the model in either language, zero extra LLM
round-trips, write-back fires automatically on every real observation
regardless of which language is playing — directly in line with the
"explicit over inferred" conclusion from the Week 2 journal.

### 6b. Keeping the two implementations from drifting

Duplicated logic is the honest cost of "both languages, one DB" — there's no
way around maintaining two copies of the parsing heuristics without adding a
shared service neither language's design philosophy wants (per
`week1_baseline/ITERATIONS.md`: avoid framework/harness shortcuts, prefer
directly-owned code). To keep the two copies honest without a shared runtime:

- `week3_capable/fixtures/parser_cases.yaml` holds raw-text → expected-parsed
  -output pairs (the §4 examples, plus more collected from play). Both the
  Python and Ruby test suites load this *same* file and assert their parser
  produces the same structured result from the same input. A behavior change
  in one language's parser that isn't matched in the other shows up as a
  failing fixture case, not a silent divergence discovered days later from
  bad data in `world.db`.
- Any change to the update rules in §7 (fill-once vs. overwrite-latest) is a
  change to this document first — treat this plan as the spec both
  implementations are ported from, not something either one invents locally.
- **Concurrent access**: with two independent processes potentially writing
  to the same file (even just "played in Ruby yesterday, Python today," not
  necessarily literally simultaneous), I'd set `PRAGMA journal_mode=WAL` in
  both `db.py` and `db.rb` — it lets readers and a writer coexist without
  blocking, which is the safer default here regardless of whether the two
  agents ever truly run at the same instant.

## 7. Your question: updating an existing mob/item row with new info

My recommendation, split by field, based on what's actually observable (§4):

- **`disposition`**: **always overwrite** with the latest observation.
  Disposition is the one field that genuinely changes mid-session (a neutral
  mob becomes hostile once attacked) and a stale "friendly" flag is exactly
  the kind of wrong-belief this feature is meant to prevent. Latest wins.
- **`level`**: **fill only if currently NULL; never overwrite a known
  value.** Level is template-level metadata for a mob name in this MUD, not
  something that fluctuates. If a differing value ever does show up against
  an already-known level, that's a signal of a parsing bug or two
  same-named-but-different mobs, not a real level change — I'd rather log a
  warning than silently overwrite.
- **`hp`**: **leave NULL in practice, and don't try to synthesize a number
  from qualitative text.** As noted in §4, CircleMUD doesn't appear to expose
  numeric mob HP to the client in ordinary play — `consider`/`examine` give
  prose, not numbers. I don't think it's safe to map "is in excellent
  condition" to a fabricated HP integer; that invents precision that isn't
  there. If a numeric HP ever does appear in text (e.g. certain spell/skill
  output), take it as the latest-observed value and overwrite, same
  reasoning as disposition — but expect this column to stay NULL for the
  overwhelming majority of mobs given what the game actually shows.
  `mobs.hp` staying NULL doesn't mean "no health signal at all" though —
  §8 below covers a real, non-fabricated way to estimate how hurt a mob is
  from actual combat outcomes, without inventing a number from prose.
- **`is_dialogue_enabled`**: fill-if-null; this is a capability of the mob
  template (can you `tell`/talk to it), not something that changes turn to
  turn.
- **Items** (`item_type`, `level`): same as mob `level` — fill-if-null,
  don't overwrite. Item identity/type is static.
- **`location_items.quantity`**: **overwrite with the latest observed
  count** when re-observed at the same location (e.g. a gold pile's amount
  is only meaningful at pickup time; stacks can also change if the world
  regenerates loot). This is the one junction-table field that's genuinely
  mutable per your spec's own example ("gold amount").

Net rule of thumb: **fields that are properties of the mob/item's identity
→ fill-once, never overwrite. Fields that describe transient state →
overwrite with latest, and bump `last_seen_at`.** Please confirm this before
I implement it, especially the HP-stays-NULL call — that's the one place
I'm inferring MUD behavior from a handful of session-log samples rather than
exhaustive testing, and if you've seen numeric mob HP appear somewhere I
haven't sampled, that changes this.

## 8. Weapon-aware combat estimation (mob condition, take two)

The condition ladder in `location_mobs.condition` (§3) is a fine cheap
signal, but it's coarse — seven buckets, no sense of "how close to done is
this fight." Per your follow-up: rather than only reading qualitative text,
track real combat outcomes and turn *those* into a number, without ever
fabricating an HP integer out of prose (same principle as §7's HP call).

**The core idea:** every damage-capable action's result is parseable as
either a landed hit or a miss (§4's grounded examples for melee), and a
kill is its own unambiguous message (`"The small bat is dead!  R.I.P."`).
So instead of guessing at a mob's current HP, count how many landed hits it
actually took to kill mobs of this type in the past, average that, and
compare the current fight's landed-hit count against the average. That's a
real, empirically-grounded estimate, not an inference from adjectives.

**Why this has to be weapon-aware — and why "weapon" means more than
melee weapons:** a short sword and a dagger do different damage, so "sewer
rats take ~6 hits" is only true for whatever dealt that damage. Per your
follow-up: **anything that can damage a mob is a weapon or pseudo-weapon,
tracked as its own identity** — the same `weapons` table and
`mob_weapon_stats` junction (§3) that hold "short sword" also hold every
other distinct damage source, each with its own running average:

| Action | Weapon/pseudo-weapon identity | Where the name comes from |
|---|---|---|
| `attack`, weapon wielded | the wielded weapon (e.g. `"short sword"`) | `current_weapon_id`, session state set by the last successful `wield`/`equip_item` result (§4: `"You wield a short sword..."`) |
| `attack`, nothing wielded | a fixed `"fists"` row | no per-call arg — bare-handed `attack` doesn't name a technique, so this is the one fixed pseudo-weapon name in the design |
| `skill_strike` | the skill's own name (e.g. `"kick"`) | **directly from the tool call's `args`** (e.g. `args["skill"]`) — no session state and no prose-parsing needed for identity, only the result text needs parsing, for landed/missed/kill (§4-style). Kicks and punches (the `"fists"` row above) are therefore always separate rows, never merged — and any future skill (a different kick-like or grapple-like skill) gets its own row automatically the same way, with no extra code per skill. |
| `cast_spell` | the spell's own name (e.g. `"magic missile"`) | directly from `args["spell"]` (or equivalent), same as `skill_strike` — **only** recorded when the result indicates the spell dealt damage to a mob; non-offensive spells (heal, bless, buffs, etc.) are not attacks and don't touch `mob_weapon_stats` at all |
| `use_magic_item` | the item's own name (e.g. a damaging wand) | directly from `args["item"]` (or equivalent), same gating as `cast_spell` — only damage-dealing uses count |

This falls directly out of §3's identity-by-name model (`get_or_create_weapon(conn, name)` already works for any of these — a melee weapon, `"fists"`, `"kick"`, or a spell name are all just rows in the same table, no schema change needed) and is a strict generalization of the original "unarmed" design: instead of one shared `"unarmed"` catch-all, **every distinct technique/spell/item gets its own name-identified row**, so a kick's stats can never bleed into a punch's, a sword's, or a spell's, and vice versa.

**Grounding gap, flagged honestly, and why it splits in two:** unlike melee
`attack` (§4 has real sampled hit/miss/kill text), no `skill_strike`,
`cast_spell`, or `use_magic_item` result text has actually been pulled from
`.boukensha/sessions/*.jsonl` yet — §4's samples only cover melee. That gap
isn't the same size for all three, discussed and settled as follows:

- **`skill_strike` (kick):** no blocker. The existing `dummy` character
  (Soldier class, per the live `10_standard_tool_library` run) already has
  kick available — real `skill_strike` output can be sampled from ordinary
  play with the account that already exists, the same way §4's melee
  samples were pulled. This should happen before/during implementation, not
  deferred.
- **`cast_spell` / `use_magic_item` (damage-dealing):** genuinely blocked
  right now — **there is no mage (or other spellcasting-class) account set
  up on this MUD yet**, so no real `cast_spell` output exists anywhere to
  sample. Decision: implement the *identity* resolution and schema/store
  support for spells now regardless (§8's table, `get_or_create_weapon`) —
  it's structured data from `args`, no prose-parsing risk, and costs nothing
  to have ready. The landed/missed/kill *text parser* for `cast_spell`/
  `use_magic_item` is explicitly **deferred** until a mage-class account
  exists and real output can be sampled — not a redesign later, just adding
  one more parser function against the same store functions once the data
  exists. Creating that account is an operational step outside this plan's
  scope, not a design question; nothing here blocks on it.

Same "ground it in real output, don't guess" rule this whole document
follows elsewhere — the difference between the two cases above is purely
*whether the account needed to generate that real output currently exists*.

**Session state** (mirrors §5's `current_location_id` — transient module
state, not schema, since it's reconstructable from the next `wield`/attack):
- `current_weapon_id` — set on every successfully-parsed `wield`/`equip_item`
  result; only consulted for plain `attack` calls (see table above).
  `skill_strike`/`cast_spell`/`use_magic_item` never read or write this —
  their identity comes from their own call's `args`, independent of
  whatever's currently wielded.
- `current_fight_mob_id` / `current_fight_hits_landed` — reset to
  none/zero whenever a fight starts against a not-currently-tracked mob,
  and cleared when that mob dies, the player flees, or the player leaves
  the room (moves away without a kill). Unchanged by which action type is
  landing the hits — a fight can mix a kick, two sword swings, and a spell
  against the same mob, and each contributes to its own `(mob, weapon)`
  pair while `current_fight_hits_landed` keeps counting total hits landed
  in the fight for the mid-fight estimate below.

**Write-back on every `attack`/`skill_strike`/`cast_spell`/`use_magic_item`
result** (the last two gated to damage-dealing uses only, per the table
above):
1. Resolve weapon/pseudo-weapon identity per the table above.
2. Parse landed vs. missed (§4 for melee; a grounding pass needed for the
   other three, per the gap noted above).
3. If landed: increment `mob_weapon_stats.hits_landed_total` for
   `(current_fight_mob_id, weapon_id)`, and increment the in-session
   `current_fight_hits_landed` counter.
4. If the same result also contains the death message: increment
   `mob_weapon_stats.kills_total` for that same pair, then clear the
   session's current-fight state.

**Estimating "how hurt is this mob" mid-fight:**
```
avg_hits_to_kill = hits_landed_total / kills_total   -- for this (mob, weapon) pair
percent_remaining ≈ clamp(1 - current_fight_hits_landed / avg_hits_to_kill, 0, 1)
```
This is only meaningful once `kills_total >= 1` for that exact pairing —
**cold start** (first-ever fight against a mob with a given weapon, or
early on when the sample size is 1-2 and noisy) falls back to
`location_mobs.condition`'s qualitative reading from §3, which needs no
history to be useful. I'd lean toward not fully trusting the numeric
estimate until `kills_total` clears a small threshold (e.g. 3) and using
the phrase field until then, but the exact cutoff is a judgment call, not
something derivable from the data itself — flagged as an open question
below.

**Store functions** (same shape as §6's, added to `world/store.{py,rb}`):

```python
def get_or_create_weapon(conn, name) -> int: ...
def record_attack(conn, mob_id, weapon_id, *, landed: bool) -> None: ...   # bumps hits_landed_total if landed
def record_kill(conn, mob_id, weapon_id) -> None: ...                      # bumps kills_total
def estimate_condition(conn, mob_id, weapon_id, hits_landed_this_fight) -> float | None: ...  # None if kills_total == 0
```

Caveats, all flagged rather than silently assumed:
- Assumes stock CircleMUD mobs of the same name are stat-identical across
  spawns (no per-instance level/HP variance) — reasonable for this server
  based on what's been observed, but not confirmed against server source,
  so pooling every "sewer rat + short sword" fight into one running average
  rests on that assumption holding.
- Assumes one player fighting one mob at a time, matching every fight seen
  in the sampled logs — multi-mob pulls would need the hit-attribution
  logic extended (which mob did this landed hit go to), not needed now.
- This estimate only exists at all after enough real fights have happened;
  it's not a substitute for §3's `location_mobs.condition`, it's a sharper
  number that kicks in once there's data to back it.

## 9. Migration approach

- Start empty: the shared `schema.sql` is applied with `CREATE TABLE IF NOT
  EXISTS` on every startup, from *both* `db.py` and `db.rb` — idempotent, no
  separate "first run" step, no import from `week1_baseline`. Whichever
  language's agent runs first bootstraps the file; the other just opens it.
- Single `.db` file at `week3_capable/data/world.db`, no `ATTACH DATABASE`.
- `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode=WAL` are per-connection
  pragmas in SQLite, so both are set in *each* language's connection helper
  (`world/db.py:connect()` and `world/db.rb`'s equivalent) — one language
  setting them doesn't set them for the other's connections, and a future
  connection (e.g. from the visualization script) that skips this would
  silently run with FK enforcement off.
- For actual future schema changes (new columns/tables), I'd track
  `PRAGMA user_version` and run any pending numbered migration scripts from
  `week3_capable/migrations/NNN_description.sql` (shared, same reasoning as
  `schema.sql`) before either language's app proceeds — not needed yet with
  an empty DB, but worth having the convention in place so "week4" doesn't
  have to invent it under pressure.

## 10. Visualization script

`scripts/visualize_world.py` — standalone, no dependency on the agent loop
or live DB connection beyond a read-only `sqlite3.connect(..., mode=ro)`
(or just opened normally with FKs off, since it's read-only).

- Query: `SELECT * FROM locations`, `SELECT * FROM exits`, plus a `GROUP BY`
  count of mobs/items per location for optional annotation.
- Library: **Graphviz** (via the `graphviz` Python package, calling out to
  the `dot` binary) rather than networkx/matplotlib — `dot`'s layout engine
  is built specifically for readable directed graphs with edge labels, which
  is exactly this problem (nodes = rooms, directed labeled edges = exits),
  whereas matplotlib/networkx layouts (spring/force-directed) tend to
  produce messier results for anything past a few dozen nodes.
- Nodes: label = location name (or `"? (unvisited)"` for placeholders),
  fill color by `area_type` (a small fixed palette), dashed border for
  `visited = 0` so unexplored frontier is visually obvious at a glance —
  that's the actual point of this script per your goal statement.
- Edges: label = direction, one edge per `exits` row. (Note: exits aren't
  guaranteed to be symmetric in a MUD — "north" from A to B doesn't imply a
  "south" exit exists from B — so this stays a directed graph, no attempt to
  collapse reciprocal pairs into one undirected edge.)
- Output: render to JPEG (`graph.render(..., format="jpg")`), default path
  `docs/maps/world.jpg` or similar — happy to take a preferred output path.
- Run as `python scripts/visualize_world.py [--db path] [--out path]` —
  entirely separate invocation from the agent, per your requirement.

The visualizer stays Python-only and reads whichever data is in
`world.db` at the time — it has no way to know (or need to know) whether a
given row was written by the Ruby or Python agent, which is exactly the
point of sharing one file instead of two.

New dependencies to add:
- **Python**: `graphviz` (the pip package) plus the system `graphviz`/`dot`
  binary — neither is currently in any `requirements.txt` in the repo, so
  I'd add it to `week3_capable/python`'s requirements file and note the
  system-package dependency in its README.
- **Ruby**: the `sqlite3` gem — not currently in any Gemfile in the repo
  (checked all of them), so it needs adding to `week3_capable/ruby`'s
  Gemfile alongside the existing `dotenv`/`mud_manager`/`opentelemetry-*`
  gems.

## 11. Decisions

**Review record:** every item below was reviewed with you directly, in a
live back-and-forth conversation about this plan — none were silently
auto-approved or skipped. Two different, and equally deliberate, things
happened depending on the item:

- **Items 2, 3, 7, 8** were decided by you directly, through explicit
  back-and-forth: you picked Graphviz over networkx/matplotlib yourself
  (§10), confirmed the `week3_capable` package-root approach and its
  rationale yourself (§2a), then asked follow-up questions of your own
  ("will it delineate kick", "will it consider magic attacks") that led to
  you explicitly requesting the kick/punch split and the spell/magic-item
  generalization (§8) — both of which changed the design from what was
  originally proposed.
- **Items 1, 4, 5, 6** were explicitly and knowingly delegated to my
  discretion — your own words were "the rest of the questions, I leave to
  your discretion, since I don't quite understand." That's still a real,
  considered choice about each one (weighing whether to dig into the
  tradeoffs yourself vs. trust the recommended default), not an oversight —
  the recommended option was taken in every case, with the reasoning for
  each spelled out below so it's checkable after the fact.

No changes to the design in §3–§10 were needed to act on any of these
beyond what's already reflected there.

1. **§7's mob/item update rules — confirmed as written**, including
   `hp` staying `NULL` absent a real numeric value in the text (no inference
   from qualitative phrases like "in excellent condition").
2. **Graphviz, not networkx/matplotlib** — `dot` binary +
   `graphviz` pip package, per §10. Install commands:
   ```bash
   sudo apt-get update && sudo apt-get install -y graphviz   # system `dot` binary
   pip install graphviz                                       # into the shared repo-root .venv
   ```
   `graphviz` goes into `week3_capable/python/requirements.txt` once that
   file exists (a new file, not an addition to any `week1_baseline`
   requirements file — `week3_capable` maintains its own dependency set from
   here on, per §2a).
3. **Package roots confirmed** — see new §2a above: a one-time full copy of
   `week1_baseline/{python/12_context/boukensha, ruby/12_context/lib/boukensha}`
   into `week3_capable/{python/boukensha, ruby/lib/boukensha}`, fully
   independent afterward.
4. **Shared-fixture approach confirmed** — `fixtures/parser_cases.yaml`,
   loaded by both language's test suites, as designed in §6b.
5. **Weapon-aware hits-to-kill estimate confirmed** as the "real" condition
   signal, with §3's qualitative `location_mobs.condition` as the cold-start
   fallback, per §8.
6. **Threshold set at `kills_total >= 3`** before trusting the numeric
   estimate over the qualitative fallback (the plan's own recommended
   default in §8, over the looser "any data beats no data" /
   `kills_total >= 1` alternative) — a 1-2 sample average is noisy enough
   (variance from crits/misses) that trusting it early risks telling the
   agent a mob is "almost dead" off a single lucky/unlucky fight, which
   fabricates the same false precision §7 explicitly avoids for HP. This is
   a plain constant in `estimate_condition()` (§8) — trivial to tune later
   if 3 turns out too conservative or too loose in practice.
7. **Unarmed attacks split by technique, not pooled into one `"unarmed"`
   row** — superseded from the original design during follow-up review.
   Bare-handed `attack` gets a fixed `"fists"` row; every `skill_strike`
   (kick, and any future skill) gets its own row named after that skill,
   read directly from the tool call's `args`, per §8's table. Kicks and
   punches are never merged.
8. **"Anything that can damage a mob is a weapon or pseudo-weapon"
   confirmed as the general principle** (follow-up refinement, added after
   initial approval) — `cast_spell` and `use_magic_item` now feed
   `mob_weapon_stats` the same way melee and skills do, identified by
   spell/item name from `args`, gated to damage-dealing uses only (no
   entry for heals/buffs/utility casts). Discussed and settled that the
   grounding gap here splits in two (§8): `skill_strike`/kick has no
   blocker (the existing `dummy` Soldier account can generate real samples
   any time), but `cast_spell`/`use_magic_item` text parsing is genuinely
   blocked — **no mage/spellcasting-class account exists on this MUD yet**,
   so there's no real `cast_spell` output anywhere to sample. Resolution:
   build the identity/schema/store side for spells now (no risk, structured
   `args`), defer only the spell-text parser until a mage account exists
   and real output can be pulled — creating that account is an operational
   step outside this plan, not a design blocker.

Next step: implement per §2a (bootstrap the package copy), §3 (apply
`schema.sql`), then §6 (parser/store modules and the registry/dispatch
hook), in that order — each step is runnable/testable on its own before the
next begins.
