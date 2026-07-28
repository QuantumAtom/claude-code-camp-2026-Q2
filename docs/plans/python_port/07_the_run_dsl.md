# Python Port Plan — 07_the_run_dsl

## Goal

Port `week1_baseline/ruby/07_the_run_dsl` to
`week1_baseline/python/07_the_run_dsl`. Same behavior, new language, one
new top-level entry point (`Boukensha.run` → `boukensha.run(...)`). No new
features beyond what Ruby 07 actually adds. **Plan only — no source files
are touched by writing this document.**

**This plan only covers what changed between Ruby 06 and Ruby 07.**
Everything already ported correctly in `06_the_logger` (the loop, the
`Logger` class, per-backend `parse_response`, task settings, client retry
logic) stays exactly as it is. Nothing gets rewritten from scratch and
nothing that already works gets touched or regenerated.

**Starting point: `week1_baseline/python/07_the_run_dsl` already exists as
a byte-for-byte copy of the finished `week1_baseline/python/06_the_logger`
tree.** Confirmed via `diff -rq week1_baseline/python/06_the_logger
week1_baseline/python/07_the_run_dsl` (excluding `__pycache__`) — zero
output. Same shape as every prior port: an **in-place edit of the copied
tree**, not a from-scratch build.

## The one real design decision in this step

Ruby's `Boukensha.run(task: ...) { |...| ... }` passes a block that gets
`instance_eval`'d against a `RunDSL` instance — inside the block, `self`
*becomes* the `RunDSL`, so bare `tool "name", ...` calls resolve to
`RunDSL#tool`. Python has no `instance_eval` equivalent; a Python closure
can't have its implicit `self` rebound.

**Resolution: the block becomes a required-shape callback that receives
the `RunDSL` instance explicitly**, via a new `configure=` keyword
argument on `boukensha.run(...)`:

```python
def register(dsl):
    dsl.tool(
        "read_file",
        "Read a file",
        {"path": {"type": "string", "description": "File path"}},
        lambda path: open(path).read(),
    )

result = boukensha.run(task="Read lib/boukensha.rb", configure=register)
```

This is the smallest faithful translation, not a novel design: it mirrors
the codebase's own existing convention for "blocks" — `Registry.tool(name,
description, parameters=None, block=None)` already takes a plain
`block=`-style callable rather than any DSL magic (see `registry.py:9` and
every call site in the current `examples/example.py`, which already
registers tools with explicit lambdas). `RunDSL.tool` will have the same
shape and just delegate to `Registry.tool`. No context manager, decorator,
or builder-pattern alternative is introduced — those would be new
ergonomics Ruby never asked for.

## Source of truth (what changed, Ruby 06 → Ruby 07)

Verified with `diff -rq week1_baseline/ruby/06_the_logger
week1_baseline/ruby/07_the_run_dsl` plus a full-text diff of every file it
flagged:

| Ruby file | Change vs. 06 | Status |
|---|---|---|
| `lib/boukensha/run_dsl.rb` | **NEW** — `RunDSL`, the tiny `instance_eval` host object exposing only `tool` | New — see design decision above for the Python translation |
| `lib/boukensha.rb` | Adds `self.run(task:, system: nil, model: nil, backend: nil, api_key: nil, ollama_host: "http://localhost:11434", log: nil, max_output_tokens: nil, &block)` — the single top-level entry point that wires `Config` → `Context` → `Registry` → (run the DSL block) → backend → `PromptBuilder` → `Client` → `Logger` → `Agent` → `ctx.add_message` → `agent.run`, with `ensure logger&.close`; adds `require_relative "boukensha/run_dsl"` at the bottom | `__init__.py` needs a matching `run()` function and `RunDSL` export |
| `lib/boukensha/config.rb` | **Re-adds** `mud_host`/`mud_port`/`mud_username`/`mud_password` (the exact four stubs `06_the_logger` had removed) | `config.py` needs the same four properties **re-added** for parity |
| `lib/boukensha/errors.rb` | **Re-adds** `LoopError` (the same class `06_the_logger` had removed) | `errors.py` needs `LoopError` **re-added**; `__init__.py` needs it back in imports/`__all__` |
| `lib/boukensha/logger.rb` | Adds `turn(n:)` (writes a `phase: "turn"` event); adds `subscribe(&block)` (`@subscribers` array) and calls every subscriber from `write_log` after each write | `logger.py` needs a matching `turn(*, n)` and `subscribe(callback)` |
| `lib/boukensha/context.rb` | Ivar-alignment whitespace tweak, plus the file loses its trailing newline | **No behavior change** — `context.py` needs **no change** |
| `lib/boukensha/agent.rb`, `client.rb`, `prompt_builder.rb`, `registry.rb`, `tool.rb`, `message.rb`, `tasks/*.rb`, `backends/*.rb` | Unchanged (not flagged by `diff -rq`) | No change |
| `prompts/system.md`, `Gemfile`, `Gemfile.lock` | Unchanged (confirmed via diff) | No change |
| `examples/example.rb` | Rewritten: drops all manual `Context`/`Registry`/backend-branch/`PromptBuilder`/`Client`/`Logger`/`Agent` wiring in favor of a single `Boukensha.run(task: ...) do ... end` call with two `tool` registrations inline; banner `Step 6: The Logger` → `Step 7: The Boukensha.run DSL` | `example.py` needs the equivalent rewrite using `configure=` |
| `README.md` | Full rewrite: what the step adds, the `RunDSL`/`Boukensha.run` primitives, an options table, a before/after code comparison, run example | See README plan below |
| `week1_baseline/bin/ruby/07_the_run_dsl` | Already exists and is correct (committed in `4ae88d0`) — `cd`s into `ruby/07_the_run_dsl`, runs `examples/example.rb` | No change |
| `week1_baseline/bin/python/07_the_run_dsl` | **Does not exist yet** — verified via `ls week1_baseline/bin/python/`, only `00`–`03` and `06` are present | **New file needed**, matching the `06_the_logger` launcher pattern — in scope for this step, unlike prior steps where the launcher already existed |

### Two things Ruby 07 adds that nothing calls yet (ship for parity anyway)

`logger.turn(n:)` and `logger.subscribe(&block)` are both defined in
`logger.rb` but **never invoked anywhere in `agent.rb` or `run_dsl.rb`** —
confirmed via `grep -n "logger\." lib/boukensha/agent.rb`, which shows only
`limit_reached`/`iteration`/`prompt`/`raw`/`turn_end`/`tool_call`/
`tool_result`/`response`, no `turn`. Same situation as `mud_*` (re-added,
still nothing reads them) and `LoopError` (re-added, still never raised).
This is the same pattern the `06_the_logger` plan already established for
`quiet`/`loud`/`is_quiet` — port unused forward-looking scaffolding for
parity rather than silently dropping it, since a later step will likely
start using it and skipping it now just creates a future gap to notice
again.

### A stale/inaccurate upstream README, noted so it isn't copied verbatim

Ruby 07's own `README.md` has real inaccuracies, worth fixing rather than
transliterating (same lesson the `06_the_logger` plan already drew — follow
the executable code, not aspirational README prose):

- **Title says "Step 6"** (`# Step 6 — The Boukensha.run DSL`) despite
  living in the `07_the_run_dsl` directory — an off-by-one left over from
  copy-pasting the prior step's README. The Python README will correctly
  say `07`, matching every other Python README in this series (`00`–`06`
  are all correctly numbered).
- **The options table only lists `backend: :anthropic` or `:ollama`**, but
  `Boukensha.run`'s actual `case backend` branch handles all five —
  `:anthropic`, `:openai`, `:gemini`, `:ollama`, `:ollama_cloud` (see
  `lib/boukensha.rb` lines ~88–95). The Python README will document all
  five, matching the real `run()` implementation.
- **The table lists `token_budget:` (default `8192`) and `max_tokens:`
  (default `1024`)** — neither keyword exists in the actual `self.run`
  signature, which only has `max_output_tokens:` (no default shown in the
  table at all, it falls back to `task_class.max_output_tokens`). The
  Python README's options table will list only the keywords the real
  function accepts.
- **The run-example command** (`./week1_baseline/bin/07_the_run_dsl`) is
  missing the `ruby/` path segment that every other step's README uses
  (e.g. `06_the_logger`'s README correctly said
  `./week1_baseline/bin/06_the_logger` matching *its* repo layout — but
  this repo's actual `bin/` is split into `bin/ruby/` and `bin/python/`
  subdirectories, confirmed via `ls week1_baseline/bin/`). The Python
  README will use the real, correct path: `./week1_baseline/bin/python/07_the_run_dsl`.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/run_dsl.py` — `RunDSL` class (see below)
- `bin/python/07_the_run_dsl` — launcher script (doesn't exist yet)

**FILL (small gaps/additions to existing files):**
- `boukensha/__init__.py` — add `run(...)` module-level function; add
  `from .run_dsl import RunDSL`; re-add `LoopError` to the import line and
  `__all__`; add `"RunDSL"` and `"run"` to `__all__`
- `boukensha/config.py` — re-add `mud_host`, `mud_port`, `mud_username`,
  `mud_password` properties
- `boukensha/errors.py` — re-add `LoopError`
- `boukensha/logger.py` — add `turn(self, *, n)` and `subscribe(self,
  callback)` (plus a `self._subscribers` list initialized lazily, and a
  call-every-subscriber step in `_write`)

**CHANGE (already present as 06's copy, must be rewritten for this step's
topic):**
- `examples/example.py` — rewrite to call `boukensha.run(task=...,
  configure=...)` instead of manually wiring `Context`/`Registry`/backend/
  `PromptBuilder`/`Client`/`Logger`/`Agent`
- `README.md` — rewrite (see below), correcting the upstream Ruby
  inaccuracies noted above

**LEAVE AS-IS (confirmed identical to Ruby 06, or a no-op change on the
Ruby side too):**
- `boukensha/context.py` (Ruby's diff here is whitespace/trailing-newline
  only)
- `boukensha/agent.py`, `client.py`, `prompt_builder.py`, `registry.py`,
  `tool.py`, `message.py` (no Ruby-side changes)
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`
- `boukensha/backends/*.py` (no backend-level changes in Ruby 07)
- `prompts/system.md`, `requirements.txt` (no new dependency — `run_dsl.py`
  is stdlib-only, no imports beyond what `registry.py` already needs)

**NO CHANGE outside the step dir:**
- `bin/ruby/07_the_run_dsl` — already correct (committed in `4ae88d0`)

**NEW outside the step dir:**
- `bin/python/07_the_run_dsl` — see above, genuinely missing

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree

## Target structure

```
week1_baseline/python/07_the_run_dsl/
  README.md
  requirements.txt
  prompts/
    system.md
  boukensha/
    __init__.py
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    prompt_builder.py
    logger.py
    run_dsl.py           <- NEW
    client.py
    agent.py
    tasks/
      __init__.py
      base.py
      player.py
    backends/
      __init__.py
      base.py
      anthropic.py
      gemini.py
      openai.py
      ollama.py
      ollama_cloud.py
  examples/
    example.py
```

Identical shape to `06_the_logger`, plus `run_dsl.py`. No new top-level
files inside the step dir (the one new file outside it is
`bin/python/07_the_run_dsl`).

## Python environment setup

Same shared-venv / per-step-manifest model as 00–06.

- Venv path: `<repo root>/.venv` per the README's manual instructions;
  actual `bin/` launchers source `~/code/virtualenv/claude` instead (per
  the `06_the_logger` plan's correction note) — same situation here, not
  this step's problem to fix, just replicate the existing pattern in the
  new `bin/python/07_the_run_dsl` launcher.
- `requirements.txt`: unchanged from 06 (`PyYAML`, `python-dotenv`) — no
  new dependency.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add `run()`; re-add `LoopError`; add `RunDSL` export |
| `lib/boukensha/run_dsl.rb` | `boukensha/run_dsl.py` | NEW — `instance_eval` block → explicit `configure=` callback, see design decision above |
| `lib/boukensha/config.rb` | `boukensha/config.py` | Re-add the four `mud_*` properties |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | Re-add `LoopError` |
| `lib/boukensha/logger.rb` | `boukensha/logger.py` | Add `turn(n=)` and `subscribe(callback)` |
| `lib/boukensha/context.rb` | `boukensha/context.py` | No change (Ruby diff is whitespace-only) |
| `lib/boukensha/agent.rb`, `client.rb`, `prompt_builder.rb`, `registry.rb`, `tool.rb`, `message.rb`, `tasks/*.rb`, `backends/*.rb` (all unchanged) | matching `.py` files | No change |
| `examples/example.rb` | `examples/example.py` | Rewrite around `boukensha.run(task=..., configure=...)` |
| `Gemfile`/`Gemfile.lock` (unchanged) | `requirements.txt` (unchanged) | No new dependency either side |
| `README.md` | `README.md` | Rewrite — correcting the stale-title/incomplete-table/wrong-path issues noted above |
| `bin/ruby/07_the_run_dsl` (already correct) | `bin/python/07_the_run_dsl` (**missing, must create**) | Python side is new work; Ruby side is not |

## New class behavior (the actual porting work)

### `boukensha/run_dsl.py` — the `RunDSL` class

```python
class RunDSL:
    def __init__(self, registry):
        self.registry = registry

    def tool(self, name, description, parameters=None, block=None):
        return self.registry.tool(name, description, parameters, block)
```

Direct translation of `Registry.tool`'s own signature
(`registry.py:9` — `def tool(self, name, description, parameters=None,
block=None)`), since `RunDSL.tool` does nothing but forward to it. No
`instance_eval` machinery is needed on the Python side — callers get the
`RunDSL` instance passed to them explicitly via `configure=` (see below),
so `dsl.tool(...)` is just an ordinary method call.

### `boukensha/__init__.py` — the `run()` function

```python
def run(
    *,
    task,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    max_output_tokens=None,
    configure=None,
):
    cfg = config()  # loads .env; populates os.environ
    task_class = Player
    task_settings = cfg.tasks(task_class.task_name())
    if system is None:
        system = task_class.system_prompt(
            task_settings,
            user_prompts_dir=cfg.user_prompts_dir,
            default_prompts_dir=Config.PROMPTS_DIR,
        )
    if model is None:
        model = task_class.model(task_settings)
    if backend is None:
        backend = task_class.provider(task_settings)
    if api_key is None:
        api_key = {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
            "ollama_cloud": os.environ.get("OLLAMA_API_KEY"),
        }.get(backend)

    ctx = Context(task=task_class, system=system)
    registry = Registry(ctx)

    if configure is not None:
        configure(RunDSL(registry))

    if backend == "anthropic":
        be = Anthropic(api_key=api_key, model=model)
    elif backend == "openai":
        be = OpenAI(api_key=api_key, model=model)
    elif backend == "gemini":
        be = Gemini(api_key=api_key, model=model)
    elif backend == "ollama":
        be = Ollama(host=ollama_host, model=model)
    elif backend == "ollama_cloud":
        be = OllamaCloud(api_key=api_key, model=model)
    else:
        raise ValueError(
            f"Unknown backend {backend!r}. Use 'anthropic', 'openai', "
            "'gemini', 'ollama', or 'ollama_cloud'."
        )

    builder = PromptBuilder(ctx, be)
    client = Client(builder)
    effective_max_iterations = task_class.max_iterations(task_settings)
    effective_max_output_tokens = max_output_tokens or task_class.max_output_tokens(task_settings)

    logger = None
    try:
        logger = Logger(log=log, snapshot={
            "task": task_class.task_name(),
            "max_iterations": effective_max_iterations,
            "max_output_tokens": effective_max_output_tokens,
            "model": model,
            "provider": backend,
        })
        agent = Agent(
            context=ctx, registry=registry, builder=builder, client=client,
            logger=logger, task_settings=task_settings,
            max_iterations=effective_max_iterations,
            max_output_tokens=effective_max_output_tokens,
        )
        ctx.add_message("user", task)
        return agent.run()
    finally:
        if logger is not None:
            logger.close()
```

Notes:

- **`backend` is a plain string (`"anthropic"`), not a Ruby symbol
  (`:anthropic`).** Ruby's `task_class.provider(task_settings).to_sym`
  converts the settings-file string into a symbol purely so its `case
  backend when :anthropic` branch reads naturally; Python's
  `Base.provider(settings)` already returns a plain string (verified in
  `tasks/base.py:13`), and every existing call site in this codebase
  (`examples/example.py`'s `if provider == "anthropic": ...` chain)
  already compares against string literals. Keeping `backend` a string is
  the Pythonic choice, not a divergence worth flagging further — it's the
  same value, just without a Ruby-specific `to_sym` step that has no
  Python equivalent.
- **`ensure logger&.close` → `logger = None` + `try/finally`.** Ruby's
  local-variable hoisting means `logger` is nil-safe inside `ensure` even
  if an exception is raised before the `Logger.new(...)` line executes
  (e.g. an unknown-backend `ArgumentError`, raised earlier in the method,
  before `Logger.new` is ever reached). The Python translation needs the
  same nil-safety, hence `logger = None` declared before the `try`, and
  the backend-selection `if/elif/else` (which can raise) placed *before*
  `Logger` construction and the `try` block — matching Ruby's actual
  execution order (the `case backend` block runs before `Logger.new` in
  `lib/boukensha.rb`, so an unknown-backend error already happens with
  `logger` still nil in Ruby too).
- **`RunDSL.new(registry).instance_eval(&block) if block` → `if configure
  is not None: configure(RunDSL(registry))`.** See the design-decision
  section above. The `RunDSL` is constructed and handed to the caller's
  function, then discarded — nothing keeps a reference to it afterward
  (matches Ruby, which also never touches the `RunDSL` instance again
  after `instance_eval` returns).
- **API-key lookup dict vs. Ruby `case`.** Same four-branch mapping
  (`anthropic`/`openai`/`gemini`/`ollama_cloud` → the matching env var;
  `ollama` needs no key, matching Ruby's `case` which has no `when
  :ollama` branch at all in the API-key lookup). Written as a dict lookup
  rather than an `if/elif` chain purely for compactness — behaviorally
  identical to Ruby's `case`.
- **`Player` is already imported directly** (`from .tasks.player import
  Player`, `__init__.py:38`) — no need to reference it as `Tasks.Player`
  the way Ruby uses `Tasks::Player`, since the Python port never
  introduced a `Tasks` namespace object, just a `tasks` subpackage.
- Needs `import os` added to `__init__.py` if not already present (check
  before assuming — `Config` itself already does `import os` in
  `config.py`, but `__init__.py` doesn't currently import `os` directly).

`RunDSL` and `run` both get added to `__all__`. `LoopError` goes back into
the `from .errors import ...` line and `__all__` (re-adding what
`06_the_logger`'s plan removed, since Ruby re-adds it too).

### `boukensha/config.py` — re-add `mud_*`

```python
# ---------- MUD connection --------------------------------------------

@property
def mud_host(self):
    return self.dig("mud", "host") or "localhost"

@property
def mud_port(self):
    return self.dig("mud", "port") or 4000

@property
def mud_username(self):
    return self.dig("mud", "username")

@property
def mud_password(self):
    return self.dig("mud", "password")
```

Exact reinstatement of what the `06_the_logger` port removed — same
properties, same defaults (`"localhost"`, `4000`), same `dig(...)` calls.
Still nothing in this step reads them (confirmed: `grep -rn "mud_"
ruby/07_the_run_dsl/lib ruby/07_the_run_dsl/examples` only matches the
definitions themselves in `config.rb`). Scaffolding for a later
MUD-connection step, ported for parity.

### `boukensha/errors.py` — re-add `LoopError`

```python
class UnknownToolError(Exception):
    pass


class ApiError(Exception):
    pass


class LoopError(Exception):
    pass


class UnsupportedModelError(Exception):
    pass
```

Matches Ruby's declared order in `errors.rb` (`UnknownToolError`,
`ApiError`, `LoopError`, `UnsupportedModelError`). Still never raised
anywhere (confirmed: no `LoopError`/`raise LoopError` hits in
`ruby/07_the_run_dsl` outside the class definition) — re-added for parity
with the upstream re-add, same reasoning as `mud_*`.

### `boukensha/logger.py` — add `turn()` and `subscribe()`

```python
def turn(self, *, n):
    self._write({"phase": "turn", "n": n})

def subscribe(self, callback):
    if not hasattr(self, "_subscribers"):
        self._subscribers = []
    self._subscribers.append(callback)
```

And in `_write`, after the existing flush:

```python
def _write(self, event):
    record = {**event, "session_id": self.session_id, "at": self._now_iso()}
    self._file.write(json.dumps(record) + "\n")
    self._file.flush()
    for subscriber in getattr(self, "_subscribers", []):
        subscriber(event)
```

Notes:
- **`@subscribers ||= []` → `getattr`/lazy-init pattern**, not a plain
  `self._subscribers = []` in `__init__`. Matches Ruby's own laziness
  exactly (`@subscribers` is never initialized in Ruby's `initialize`
  either — only ever created on first `subscribe` call via `||=`); adding
  an eager `self._subscribers = []` to `__init__` would be a harmless but
  unmotivated divergence from the line-for-line source. `getattr(self,
  "_subscribers", [])` in `_write` sidesteps needing the attribute to
  exist at all until `subscribe` is first called.
- **Callback receives the raw `event` dict** (the same dict passed into
  `_write`, i.e. `{"phase": ..., ...}` *before* `session_id`/`at` are
  merged in) — matches Ruby's `s.call(event)`, which is called with the
  pre-merge `event` hash (Ruby builds `event.merge(...)` into a *new*
  hash for `JSON.generate`/`@log_io.puts`, but calls `s.call(event)` with
  the original, unmerged `event` variable). The Python translation
  preserves this: `subscriber(event)` uses the original `event` parameter,
  not `record`.
- Still nothing calls `subscribe` anywhere in this step (confirmed via the
  `grep -n "logger\."` check above) — scaffolding, ported for parity, same
  situation as `turn`.

### `boukensha/context.py`

No change. Ruby's diff here is an ivar-alignment whitespace tweak plus a
dropped trailing newline — neither is a Python concern.

## `examples/example.py`

Full rewrite of the wiring section, following Ruby's `examples/example.rb`
structure exactly (translated per the `configure=` design decision):

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

# Config is loaded automatically inside boukensha.run() — system prompt,
# model, and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by
# default. You can still override any of them as keyword arguments.

print("=== BOUKENSHA Step 7: The boukensha.run DSL ===")
print()
print(f"Config: {boukensha.config()}")
print()

base_dir = Path(__file__).resolve().parents[1]


def register_tools(dsl):
    dsl.tool(
        "read_file",
        "Read the contents of a file from disk",
        {"path": {"type": "string", "description": "The file path to read"}},
        lambda path: (base_dir / path).read_text(),
    )

    dsl.tool(
        "list_directory",
        "List the files in a directory",
        {"path": {"type": "string", "description": "The directory path to list"}},
        lambda path: ", ".join(f for f in os.listdir(base_dir / path) if not f.startswith(".")),
    )


result = boukensha.run(
    task="Read the README.md file and summarise what this MUD player assistant framework can do.",
    configure=register_tools,
)

print()
print("=== FINAL RESPONSE ===")
print(result)
```

Notes:
- **`ENV["BOUKENSHA_DIR"] ||= ...` → `os.environ.setdefault(...)`.** Same
  pattern already used by every prior Python example — carried forward
  unchanged, matching the recent `4ae88d0` commit's fix to the Ruby side
  (the commit message referenced in this repo's recent history: "freshened
  up the RunDSL module and added the proper environment variable for
  BOUKENSHA_DIR").
- **All manual wiring is gone**: no `Context`, `Registry`,
  `PromptBuilder`, `Client`, `Logger`, `Agent` construction, no
  provider/backend `if`/`elif` chain, no `Player.system_prompt(...)` call
  — that's the entire point of this step, and it's a bigger deletion here
  than the equivalent Ruby diff only because the Python example was never
  shortened by an intermediate DSL step the way Ruby's `Boukensha.run`
  now provides.
- **Tool registration moves into a `register_tools(dsl)` function**
  instead of Ruby's inline block — the direct consequence of the
  `configure=` design decision. Two tools, same names/descriptions/
  parameters/behavior as every prior step's example.
- Banner text: `"=== BOUKENSHA Step 6: The Logger ==="` →
  `"=== BOUKENSHA Step 7: The boukensha.run DSL ==="` (lowercase `boukensha.run`
  to match the actual Python call syntax, mirroring how Ruby's banner says
  `Boukensha.run` to match `Boukensha.run(...)`).

## `bin/python/07_the_run_dsl` (new file)

Doesn't exist yet — must be created from scratch, following the exact
pattern of `bin/python/06_the_logger`:

```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$HOME/code/virtualenv/claude/bin/activate"
cd "$(dirname "$0")/../../python/07_the_run_dsl"
python3 examples/example.py
```

Needs `chmod +x` after creation (every existing `bin/python/*` launcher is
executable — `01_struct_skeleton`, `03_prompt_builder`, `06_the_logger` are
all `-rwxrwxr-x`). Note this launcher doesn't `export BOUKENSHA_DIR` the
way `bin/ruby/07_the_run_dsl` now does (post-`4ae88d0`) — matching
`bin/python/06_the_logger`'s existing (unexported) behavior is the right
call here, since `examples/example.py` sets `BOUKENSHA_DIR` itself via
`os.environ.setdefault(...)` before `boukensha.run()` is ever called, same
as every prior Python example. Not a gap to fix in this step; just noting
the asymmetry with the Ruby launcher is intentional/pre-existing.

## `README.md`

Rewrite following the Python port's established structure (00–06 all share
it: title/link → Environment setup → New/Updated files tables → design
explanation → run example → Considerations → Files table). Content to
cover, drawn from Ruby's README **corrected** per the inaccuracies flagged
above:

- Title `# 07 · The boukensha.run DSL (Python)`, link to
  `../../ruby/07_the_run_dsl/README.md` (note: linking to Ruby's README
  despite its own stale "Step 6" title — that's Ruby's file to fix, not
  this port's problem).
- Environment setup block (unchanged pattern, `pip install -r
  week1_baseline/python/07_the_run_dsl/requirements.txt`).
- **New files:** `boukensha/run_dsl.py`.
- **Updated files:** `boukensha/__init__.py` (`run()` function, `RunDSL`
  export, `LoopError` re-added), `boukensha/config.py` (`mud_*`
  re-added), `boukensha/errors.py` (`LoopError` re-added),
  `boukensha/logger.py` (`turn()`/`subscribe()` added), `examples/example.py`
  (rewritten around `boukensha.run`).
- **What this step adds** section, mirroring Ruby's own framing: every
  previous step required manually wiring `Context`/`Registry`/backend/
  `PromptBuilder`/`Client`/`Logger`/`Agent`; this step hides all of that
  behind one function call.
- **The `configure=` callback** section explaining the Python-specific
  translation of Ruby's `instance_eval` block (link back to/restate the
  design-decision reasoning above) — this needs its own clearly-labeled
  subsection since it's the one place this port's public API shape
  genuinely differs from a literal transliteration.
- **`boukensha.run()` options table**, corrected to match the real
  signature (all five backends, no phantom `token_budget`/`max_tokens`
  keys):

  | Option | Default | Description |
  |---|---|---|
  | `task` | *(required)* | The user message handed to the agent |
  | `system` | task's system prompt (`prompts/system.md` or override) | System prompt |
  | `model` | from `tasks.player.model` in `settings.yaml` | Model name |
  | `backend` | from `tasks.player.provider` in `settings.yaml` | `"anthropic"`, `"openai"`, `"gemini"`, `"ollama"`, or `"ollama_cloud"` |
  | `api_key` | matching `*_API_KEY` env var | Not needed for `"ollama"` |
  | `ollama_host` | `"http://localhost:11434"` | Ollama base URL |
  | `log` | `None` | Optional JSONL path override; default is `.boukensha/sessions/<session-id>.jsonl` |
  | `max_output_tokens` | from `tasks.player.max_output_tokens` | Per-reply output cap |
  | `configure` | `None` | Callback receiving a `RunDSL` — call `dsl.tool(...)` inside it to register tools |

- **Before/after code comparison**, Python-flavored version of Ruby's
  README section (manual 06-style wiring vs. the new one-call form) —
  reuse the actual code from `examples/example.py`'s predecessor
  (`06_the_logger`'s `example.py`) for the "before" side and this step's
  `register_tools`/`boukensha.run` call for "after".
- `Logger` method table: same as `06_the_logger`'s README, plus the two
  new rows:

  | Method | Phase | Logs |
  |---|---|---|
  | `turn(n=)` | `turn` | *(new, unused by anything in this step — scaffolding)* |
  | `subscribe(callback)` | — | registers a callback invoked with every logged event dict |

- Note explicitly, in a Considerations-style callout, that `turn()` and
  `subscribe()` are ported for parity but nothing in this step calls them
  yet — same phrasing pattern as `06_the_logger`'s README used for
  `quiet`/`loud`/`is_quiet`.
- Note the re-added `LoopError` and `mud_*` config properties the same way
  — present, unused, scaffolding.
- Run example: `./week1_baseline/bin/python/07_the_run_dsl` (the corrected
  path, see the stale-README section above).
- Files table: add `boukensha/run_dsl.py`.

## Expected output / how to verify parity

Same situation as every prior networked step — this makes real HTTP calls
(unless `tasks.player.provider` is `ollama` against a local server), so
"expected output" isn't a fixed transcript. Verify parity by:

1. Running both `bundle exec ruby examples/example.rb` under
   `ruby/07_the_run_dsl` and `python3 examples/example.py` under
   `python/07_the_run_dsl` (or the matching `bin/` launchers — note the
   Python one is newly created by this step), then diffing the *shape* of
   the two newest session log files.
2. Confirming the `session_start` log line in both carries the new
   snapshot fields: `task`, `max_iterations`, `max_output_tokens`,
   `model`, `provider` — this is new behavior versus `06_the_logger`
   (previously `Logger.new` was called with no `snapshot:`/`snapshot=` at
   all in the examples).
3. Confirming both `read_file`/`list_directory` tools still work
   end-to-end through the new entry point (same tool names/params/
   behavior as `06_the_logger`, just registered via `configure=`/the block
   instead of a bare `registry.tool(...)` call).
4. Confirming an unknown `backend=`/`backend:` value raises in both
   (`ArgumentError` in Ruby, `ValueError` in Python) with the logger never
   constructed (i.e. no stray session file created) — exercises the
   `logger = None` / `ensure logger&.close` nil-safety path specifically.
5. Confirming `configure=None` (no tools registered) still runs
   successfully — the agent just has zero tools available, same as Ruby's
   `&block` being optional (`if block`).
6. Registering a `subscribe` callback via a follow-up smoke test (not part
   of `examples/example.py` itself, since nothing there calls it) and
   confirming it receives every logged event dict in both languages, in
   the same order.

## Carried-over known gaps (not fixed in this port, for parity)

Same items `06_the_logger`'s README implicitly leaves alone, still true at
this step:
- No persistent memory or context compaction — still a later step.
- Settings file must be exactly `.yaml`, not `.yml` (carried from 00).
- `quiet`/`loud`/`is_quiet` still wired up, still nothing reads them.
- **New this step:** `turn()`/`subscribe()` on `Logger`, `LoopError`, and
  `mud_*` on `Config` are all present but unused — ported for parity, not
  exercised until a later step.
- The logger's file handle still has no context-manager protocol; `run()`
  closes it in a `finally`, but a caller building an `Agent` by hand
  (bypassing `boukensha.run()`) still owns closing it themselves, same as
  every prior step.

## Decisions already made (from the 00–06 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories; this step **does** add a
  new launcher (`bin/python/07_the_run_dsl`), unlike 06 which found the
  launcher already correct — first step in this series where the Python
  launcher is genuinely new work.
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+ (unchanged).
- Output parity: exact field-for-field match where behavior is
  deterministic; model responses and tool-call sequences remain
  non-deterministic.
- `requirements.txt`: unchanged, no new dependency.
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: everything from `06_the_logger` carries
  over unchanged except the additions listed above.
- README vs. actual implementation: follow the executable code, not
  aspirational/stale README prose — directly relevant again here, given
  the three concrete inaccuracies in Ruby 07's own README documented
  above.

## Remaining cosmetic/design decisions

- **`instance_eval` block → `configure=` callback receiving an explicit
  `RunDSL` instance.** The central, load-bearing decision of this port —
  see "The one real design decision in this step" above. Chosen because
  it's the smallest faithful translation and matches this codebase's
  existing block-as-explicit-callable convention (`Registry.tool`'s own
  `block=` parameter), not because of any Python-idiom preference for
  context managers or decorators that Ruby never asked for.
- **`backend` stays a plain string, never a Python `Enum` or symbol
  stand-in.** Matches `Base.provider(settings)`'s existing return type and
  every existing string-comparison call site in this codebase; Ruby's
  `.to_sym` has no motivating Python equivalent.
- **API-key resolution as a dict lookup rather than an `if/elif` chain.**
  Purely a compactness choice for a four-branch, no-side-effect mapping;
  behaviorally identical to Ruby's `case`.
- **`logger = None` + `try/finally` instead of a context manager.**
  Matches Ruby's `ensure` scoping exactly (including the nil-safety for an
  exception raised before `Logger.new` runs); a `with`-based approach
  would be more idiomatic in isolation but isn't what `Boukensha.run`
  actually does, and this series' convention (established across 00–06)
  is fidelity to the source over introducing idioms Ruby doesn't have.
- **`Logger.subscribe`'s lazy `getattr(self, "_subscribers", [])` instead
  of eager `self._subscribers = []` in `__init__`.** Matches Ruby's own
  `@subscribers ||= []` laziness (never initialized until first
  `subscribe` call) rather than "helpfully" initializing it earlier.
- **README title, options table, and run-example path all corrected
  rather than copied from Ruby 07's README verbatim.** Three concrete,
  independently-verified inaccuracies (stale step number, incomplete
  backend list, wrong/nonexistent options) — documented in detail above so
  the correction is traceable back to a specific diff, not an
  unsubstantiated claim.
