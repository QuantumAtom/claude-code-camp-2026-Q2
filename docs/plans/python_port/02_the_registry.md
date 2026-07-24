# Python Port Plan — 02_the_registry

## Goal

Port `week1_baseline/ruby/02_the_registry` to
`week1_baseline/python/02_the_registry`. Same behavior, same on-disk config
format, new language. No new features — this is a straight port of the
existing step.

**Starting point (already done, but stale): `week1_baseline/python/02_the_registry`
already exists as a byte-for-byte copy of `week1_baseline/python/01_struct_skeleton`.**
`README.md` still reads "01 · The Struct Skeleton (Python)" / "Step 1: Struct
Skeleton", and `examples/example.py` is still 01's struct-skeleton demo —
neither has been touched yet. `boukensha/config.py`, `boukensha/tool.py`,
`boukensha/message.py`, `boukensha/context.py`, `boukensha/tasks/base.py`,
`boukensha/tasks/player.py`, and `requirements.txt` are already correct and
need **no changes** for this step (Ruby 02 doesn't touch `Config`, `Tool`,
`Message`, `Context`, or `Tasks` either — same files, same content). So this
port is **an in-place edit of that copied tree**, not a from-scratch build:
add `registry.py` + `errors.py`, then rewrite `__init__.py`, `example.py`, and
`README.md`.

`boukensha/tasks/__init__.py` is currently an empty file (0 bytes) in the
copy — same as it presumably is upstream; leave it empty.

## Source of truth (what to port)

| Ruby file | Purpose | Δ vs `01_struct_skeleton` |
|---|---|---|
| `week1_baseline/ruby/02_the_registry/README.md` | Design spec — Registry's two jobs (store/dispatch), symbol-conversion gotcha, `UnknownToolError` | Rewritten (new topic) |
| `week1_baseline/ruby/02_the_registry/lib/boukensha.rb` | Top-level requires: config, tasks/player, tool, message, context, **errors, registry** | +2 requires |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/config.rb` | `Boukensha::Config` | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/tool.rb` | `Tool` Struct(name, description, parameters, block) + `to_s` | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/message.rb` | `Message` Struct(role, content, tool_use_id) + `to_s` | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/context.rb` | `Context` class: task/system/messages/tools + register/add helpers | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/tasks/base.rb` | Abstract `Tasks::Base` | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/tasks/player.rb` | Concrete `Tasks::Player` | **Identical** to 01 |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/registry.rb` | **NEW** — `Registry` class: `tool(...)` registers, `dispatch(name, args)` looks up + calls | New |
| `week1_baseline/ruby/02_the_registry/lib/boukensha/errors.rb` | **NEW** — `UnknownToolError < StandardError` | New |
| `week1_baseline/ruby/02_the_registry/examples/example.rb` | Rewritten to register tools via `Registry` instead of `ctx.register_tool` directly, then dispatch `"shout"`, `"move"`, and a deliberately unknown `"flee"` | Rewritten |
| `week1_baseline/ruby/02_the_registry/Gemfile` | Only dependency: `dotenv` | Identical |
| `week1_baseline/bin/ruby/02_the_registry` | Bash wrapper that runs the Ruby example | Sibling of 01, already exists |

Also relevant for context (not ported, background only): the already-shipped
Python `week1_baseline/python/01_struct_skeleton/` (the source of the current
copy), `docs/plans/python_port/01_struct_skeleton.md` (the plan template this
doc follows), and `week1_baseline/ITERATIONS.md`.

## Concrete delta (this is the actual work)

Because the target is already a copy of Python 01, the port reduces to the
following edits inside `week1_baseline/python/02_the_registry/`:

**ADD (net-new files):**
- `boukensha/registry.py` — `Registry` class (see below)
- `boukensha/errors.py` — `UnknownToolError` exception (see below)

**CHANGE (already present as 01's copy, must be edited):**
- `boukensha/__init__.py` — currently exports `Config, Player, Tool, Message,
  Context`; expand to also export `Registry, UnknownToolError` (and update
  `__all__`).
- `examples/example.py` — currently 01's "Step 1: Struct Skeleton" demo
  (registers the `move` tool directly on `ctx`). Rewrite as the registry
  demo: build a `Registry(ctx)`, register `move` **and** `shout` through it,
  print `Config`/`Context`/`Tools`, then dispatch `"shout"`, dispatch
  `"move"`, and dispatch the unregistered `"flee"` inside a try/except that
  prints the caught `UnknownToolError`.
- `README.md` — currently titled `# 01 · The Struct Skeleton (Python)`;
  rewrite for the registry topic (two-jobs framing, method table, dispatch
  gotcha, expected output).

**LEAVE AS-IS (identical in Ruby too, already correct from the 01 copy):**
- `boukensha/config.py`, `boukensha/tool.py`, `boukensha/message.py`,
  `boukensha/context.py`
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`,
  `boukensha/tasks/__init__.py`
- `requirements.txt` (`PyYAML`, `python-dotenv` — the registry adds no new
  deps)

**ADD outside the step dir:**
- `bin/python/02_the_registry` (mirror `bin/python/01_struct_skeleton`; see
  below). `bin/ruby/02_the_registry` already exists and is correct.

## Cleanup required first: recursive-copy pollution

Same pollution as the 01 port flagged (and 01 itself is **still** not
cleaned up — it still has a `week1_baseline/python/01_struct_skeleton/
week1_baseline/...` nested tree today). Confirmed present in this step's
target too: `week1_baseline/python/02_the_registry/week1_baseline/` is a
runaway recursive self-copy from whatever copy operation produced these
trees, plus stray `__pycache__/` directories under `boukensha/` and
`boukensha/tasks/`.

Before/while porting, **delete the nested `week1_baseline/` tree** from
`week1_baseline/python/02_the_registry/` (and, opportunistically, from
`01_struct_skeleton/` while touching this area — not required for this step
but cheap to fix), and remove stray `__pycache__/` / `*.pyc`. `.gitignore`
already ignores `.venv/`, `__pycache__/`, and `*.pyc`; the nested
`week1_baseline/` tree itself is **not** ignored, so it must be physically
deleted. Do not commit the nested trees. `git status` currently shows the
whole `week1_baseline/python/02_the_registry/` as one untracked directory, so
nothing is lost by deleting the pollution before the first commit of this
step.

## Hard requirement: on-disk compatibility

Unchanged from the 00/01 ports. The Python `Config` must read the **same**
`~/.boukensha/` directory — same `settings.yaml` schema, same `.env`, same
`BOUKENSHA_DIR` override — as the Ruby version. A user should point both
implementations at one shared config directory and get identical results.

## Target structure

```
week1_baseline/python/02_the_registry/
  README.md
  requirements.txt
  boukensha/
    __init__.py
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    tasks/
      __init__.py
      base.py
      player.py
  examples/
    example.py
```

No `prompts/` directory (carried forward from 01). No `pyproject.toml` (plain
`pip` + `requirements.txt`, per the 00 decision). `examples/example.py`
imports the local `boukensha` package via the same `sys.path` insert trick
already present in the copied file — no change needed there.

## Python environment setup

Same shared-venv / per-step-manifest model as 00/01 — nothing new here.

- Venv path: `<repo root>/.venv` (shared across all weeks/steps).
- `requirements.txt` path:
  `week1_baseline/python/02_the_registry/requirements.txt` (`PyYAML`,
  `python-dotenv` — the registry adds **no** dependencies, it's plain
  classes/exceptions). Installed into the shared venv: `pip install -r
  week1_baseline/python/02_the_registry/requirements.txt`.
- Setup instructions go at the top of the step's `README.md`.
- `bin/python/02_the_registry` sources `<repo root>/.venv/bin/activate`
  itself before running (see below).

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Already copied; edit exports to add `Registry, UnknownToolError` |
| `lib/boukensha/config.rb` | `boukensha/config.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tool.rb` | `boukensha/tool.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/message.rb` | `boukensha/message.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/context.rb` | `boukensha/context.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tasks/player.rb` | `boukensha/tasks/player.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/registry.rb` | `boukensha/registry.py` | NEW — plain class |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | NEW — `class UnknownToolError(Exception)` |
| `examples/example.rb` | `examples/example.py` | Rewrite for the registry demo |
| `Gemfile` (`dotenv`) | `requirements.txt` (`PyYAML`, `python-dotenv`) | Unchanged |
| `README.md` | `README.md` | Port two-jobs framing, method table, gotcha, expected output |
| `bin/ruby/02_the_registry` | `bin/python/02_the_registry` | Mirror `bin/python/01_struct_skeleton` |

## New class behavior (the actual porting work)

### `UnknownToolError` (`errors.rb` → `errors.py`)

Ruby: `class UnknownToolError < StandardError; end` — a bare error class, no
custom fields or message formatting (the message is built by the caller at
raise time).

Python:
```python
class UnknownToolError(Exception):
    pass
```

### `Registry` (`registry.rb` → `registry.py`)

Ruby API:
- `initialize(context)` — stores `@context`
- `tool(name, description:, parameters: {}, &block)` — builds
  `Tool.new(name.to_s, description, parameters, block)`, calls
  `@context.register_tool(tool)`, returns the tool
- `dispatch(name, args = {})` — looks up `@context.tools[name.to_s]`, raises
  `UnknownToolError, "No tool registered as '#{name}'"` if absent, otherwise
  calls `tool.block.call(**args.transform_keys(&:to_sym))` — i.e. **converts
  string-keyed args to symbol-keyed kwargs** before invoking the block. This
  string→symbol translation is the "real gotcha" the Ruby README calls out
  explicitly (agents send string-keyed JSON; Ruby blocks expect symbol
  kwargs).

Python has no symbol/string keyword split — `**kwargs` already accepts
string keys directly — so the translation step has **no Python equivalent to
perform**, but the README should still explain why Ruby needs it and note
that Python's dict-based `**kwargs` sidesteps the problem entirely (an
idiom-level divergence worth documenting, not a bug to "fix").

```python
from .tool import Tool
from .errors import UnknownToolError


class Registry:
    def __init__(self, context):
        self.context = context

    def tool(self, name, description, parameters=None, block=None):
        tool = Tool(str(name), description, parameters or {}, block)
        self.context.register_tool(tool)
        return tool

    def dispatch(self, name, args=None):
        args = args or {}
        tool = self.context.tools.get(str(name))
        if tool is None:
            raise UnknownToolError(f"No tool registered as '{name}'")
        return tool.block(**args)
```

Signature note: Ruby's `tool(name, description:, parameters: {}, &block)`
uses required keyword args for `description` plus a trailing block. Python
has no block-argument syntax, so `block` becomes a plain trailing
positional/keyword parameter passed explicitly (a `lambda` or `def`), matching
how `Tool.block` is already constructed in `example.py` for steps 00/01. Keep
`description` and `parameters` as plain params (not keyword-only) unless
matching Ruby's keyword-only call sites is judged worth the extra ceremony —
Python callers in `example.py` will call `registry.tool("move", "...",
{...}, lambda direction: ...)` positionally either way.

## Idiom translations

Config/Tool/Message/Context/Tasks idioms are inherited unchanged from the
00/01 ports. New for step 02:

- Ruby `class Foo < StandardError; end` → Python
  `class Foo(Exception): pass`.
- Ruby `@context.tools[name.to_s]` + explicit `raise ... unless tool` →
  Python `self.context.tools.get(str(name))` + `if tool is None: raise ...`.
- Ruby `args.transform_keys(&:to_sym)` (string→symbol kwarg conversion) →
  **no-op in Python**; `**args` already unpacks a string-keyed dict into
  keyword arguments. Document this as a language-level simplification in the
  README rather than silently dropping the concept — it's the whole point of
  the Ruby README's "Considerations" section.
- Ruby optional block (`&block`) captured via `def tool(...) ... &block ...
  end` → Python plain callable parameter (`block=None`), called as
  `tool.block(**args)` (no `.call`; Python callables are invoked directly).
- `require_relative "errors"` at the top of `registry.rb` → Python
  `from .errors import UnknownToolError` inside `registry.py`.

## `examples/example.py`

Mirror the currently-copied `example.py`'s structure (`sys.path` insert,
`BOUKENSHA_DIR` setdefault, `Config()`, `Player.system_prompt(...)`), then:

1. `ctx = Context(task=Player, system=system_prompt)`
2. `registry = Registry(ctx)`
3. Register `"move"` through the registry (same description/parameters/block
   as steps 00/01's `move` tool — dropped the extra `"description": "The
   direction to move"` nested key inside `parameters["direction"]` to match
   Ruby 02's leaner `{ direction: { type: "string" } }`, since Ruby 02's
   `example.rb` uses the shorter schema, not 01's version).
4. Register `"shout"` through the registry:
   `parameters={"message": {"type": "string"}}`,
   `block=lambda message: message.upper()`.
5. Print header `=== Boukensha Step 2: Tool Registry ===`, then `Config:`,
   `Context:`, `Tools:` (iterate `ctx.tools.values()`).
6. `result = registry.dispatch("shout", {"message": "dragon spotted"})`;
   print `Dispatching 'shout' with message='dragon spotted'...` then
   `Result: {result}`.
7. `result = registry.dispatch("move", {"direction": "north"})`; same
   print pattern.
8. `try: registry.dispatch("flee") except UnknownToolError as e: print(f"UnknownToolError caught: {e}")`.

## `bin/python/02_the_registry`

Mirror `bin/python/01_struct_skeleton` exactly (activates the shared root
venv itself):
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/02_the_registry"
python3 examples/example.py
```
Assumes the venv exists and this step's `requirements.txt` is installed (per
the README). The Ruby `bin/ruby/02_the_registry` already exists with the
correct path — no change needed there.

## Expected output

Run via `./week1_baseline/bin/python/02_the_registry`. Byte-for-byte match
with the Ruby example (`bundle exec ruby examples/example.rb` under
`week1_baseline/ruby/02_the_registry`), with only Python-native spelling
divergences carried forward from 01 (`params=['direction']` vs Ruby's
`params=[:direction]`):
```
=== Boukensha Step 2: Tool Registry ===

Config:  #<Boukensha::Config dir=/home/you/.boukensha tasks=player>
Context: #<Context task=player turns=0 tools=2>
Tools:
  #<Tool name=move description=Move the player in a direction (north, so params=['direction']>
  #<Tool name=shout description=Shout a message so everyone in the zone can  params=['message']>

Dispatching 'shout' with message='dragon spotted'...
Result: DRAGON SPOTTED

Dispatching 'move' with direction='north'...
Result: You move north into a torch-lit corridor.

UnknownToolError caught: No tool registered as 'flee'
```

Note the Ruby README's own "Expected Output" section is aspirational and
does **not** match what `context.rb`/`example.rb` actually produce: it shows
`#<Context turns=0 tools=2 budget=8192>` (a `budget` field that doesn't exist
anywhere in `context.rb`) and quoted descriptions/symbol keys that don't
match `tool.rb`'s real `to_s`. Same carried-over discrepancy the 01 plan
flagged for that step's README vs `context.rb` — **follow the executable
Ruby implementation**, not the README's aspirational text, for both the Ruby
baseline and this Python port.

## Carried-over known gaps (not fixed in this port, for parity)

Same items the Ruby READMEs already flag as deliberately unfixed:
- Default prompt is hardcoded rather than scoped per task
  (`prompts/<task>/system.md`) — carried from 01, `Context`/`Config` are
  unchanged in this step.
- Settings file must be exactly `.yaml`, not `.yml`.
- No actual LLM/agent loop yet — `dispatch` is called by hand in
  `example.py` to simulate what an agent would eventually decide to do; this
  step still doesn't wire up a real decision loop (that's a later step).

## Decisions already made (from the 00/01 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories: `bin/ruby/02_the_registry`
  (exists) and `bin/python/02_the_registry` (new).
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+.
- Output parity: exact field-for-field match with the Ruby example where
  possible.
- `requirements.txt`: per-step, unpinned (`PyYAML`, `python-dotenv`).
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: the target is already copied from Python 01;
  leave `config.py`, `tool.py`, `message.py`, `context.py`,
  `tasks/base.py`, `tasks/player.py`, `tasks/__init__.py`, and
  `requirements.txt` unchanged; only add `registry.py`/`errors.py` and edit
  `__init__.py`, `examples/example.py`, `README.md`.
- README vs actual Ruby implementation: follow the executable code
  (`context.rb`, `tool.rb`), not the Ruby README's aspirational "Expected
  Output" block — same call made for the 01 port.
- Struct representation: `@dataclass` for `Tool`/`Message` (unchanged, not
  touched by this step); `Registry` and `UnknownToolError` are plain
  classes, matching their Ruby counterparts (a `Registry` isn't a data
  Struct, it's a service object; an error class is never a Struct).

## Remaining cosmetic decisions

- **`params=[:direction]` vs `params=['direction']`.** Unchanged call from
  01: default to Python-native `['direction']`.
- **`registry.tool(...)` signature shape.** Ruby uses required keyword args
  (`description:`) plus a block. Python's port uses plain positional/keyword
  params ending in `block=None` (see "New class behavior" above) rather than
  trying to emulate Ruby's keyword-only + block call syntax — simpler and
  matches how `Tool(...)` is already constructed positionally in
  `example.py`. Revisit only if a later step's calling convention makes
  keyword-only args clearly worth it.
