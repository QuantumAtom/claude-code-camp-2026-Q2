# Python Port Plan — 06_the_logger

## Goal

Port `week1_baseline/ruby/06_the_logger` to
`week1_baseline/python/06_the_logger`. Same behavior, same on-disk log
format (`.boukensha/sessions/<session-id>.jsonl`), new language. No new
features — this is a straight port of the existing step. **Plan only — no
source files are touched by writing this document.**

**This plan only covers what changed between Ruby 05 and Ruby 06.**
Everything already ported correctly in `05_agent_loop` (the loop itself,
per-backend `parse_response`/`_assistant_message`, task max-iteration
settings, client retry logic) stays exactly as it is. Nothing gets
rewritten from scratch and nothing that already works gets touched or
regenerated.

**Starting point: `week1_baseline/python/06_the_logger` already exists as a
byte-for-byte copy of the finished `week1_baseline/python/05_agent_loop`
tree.** Confirmed via `diff -rq week1_baseline/python/05_agent_loop
week1_baseline/python/06_the_logger` (excluding `__pycache__`) — zero
output. Same shape as every prior port: an **in-place edit of the copied
tree**, not a from-scratch build.

## Source of truth (what changed, Ruby 05 → Ruby 06)

Verified with `diff -rq week1_baseline/ruby/05_agent_loop
week1_baseline/ruby/06_the_logger` plus a full-text diff of every file it
flagged:

| Ruby file | Change vs. 05 | Status |
|---|---|---|
| `lib/boukensha/logger.rb` | **NEW** — the `Logger` class: structured JSONL session logging | New — the core deliverable of this step |
| `lib/boukensha.rb` | Adds module-level `self.config` / `self.quiet!` / `self.loud!` / `self.quiet?` / `self.debug!` / `self.debug?`; adds `require_relative "boukensha/logger"` and (reordered, not new) `require_relative "boukensha/backends/base"` | `__init__.py` needs the module-level functions and the `Logger` export |
| `lib/boukensha/agent.rb` | `initialize` gains `logger: Logger.new` kwarg; `run` logs `limit_reached`/`iteration`/`prompt`/`raw`/`response`/`turn_end` at each relevant point; `handle_tool_calls` now takes the raw `response` too, logs a response event for the reasoning text (or a synthesized placeholder) before dispatching tools, logs `tool_call`/`tool_result` around each dispatch, and **now rescues `StandardError` from `@registry.dispatch`** (previously unguarded — a broken tool would blow up the whole turn) turning a failure into an `"ERROR: Class: message"` result string plus `ok: false`; `wrap_up` logs the wind-down response and `turn_end` on both the success and `rescue ApiError` paths; two new private helpers, `log_response` and `normalized_usage` | `agent.py` needs all of this added |
| `lib/boukensha/config.rb` | **Removes** `mud_host`/`mud_port`/`mud_username`/`mud_password` (dead MUD-connection stubs that were never used by anything in this step) | `config.py` needs the matching four `mud_*` properties **removed** for parity |
| `lib/boukensha/errors.rb` | **Removes** `LoopError` (the Ruby 05 plan already flagged this as unused scaffolding; upstream has now deleted it outright) | `errors.py` needs `LoopError` **removed**; `__init__.py` needs it dropped from imports/`__all__` |
| `lib/boukensha/context.rb` | Whitespace-only realignment of `attr_reader`/ivar assignments | **No behavior change** — `context.py` needs **no change** |
| `lib/boukensha/prompt_builder.rb` | Adds `attr_reader :backend` (plus a trailing-newline fix) | `prompt_builder.py`'s `self.backend` is already a plain public attribute — **no change** |
| `prompts/system.md`, `Gemfile` | Unchanged (confirmed via diff) | No change |
| `examples/example.rb` | Minor reformatting (`config =`/`base_dir =` alignment); adds `logger = Boukensha::Logger.new` and threads `logger: logger` into `Agent.new`; banner text `Step 5: Agent Loop` → `Step 6: The Logger` | `example.py` needs the `Logger` wiring and banner update |
| `README.md` | Full rewrite: session log format, `Logger` method table, task config snippet, debug events, run example. **Ruby's own step-6 README drops the "New/Updated Files" tables entirely** — it's a narrower, logger-focused document than 05's README | See README plan below — the Python port keeps the New/Updated-files tables for consistency with 00–05's Python READMEs (an established Python-port convention, not something Ruby 06 asks for) |
| `week1_baseline/bin/ruby/06_the_logger` | Correct — `cd`s into `ruby/06_the_logger`, runs `examples/example.rb` | No change |
| `week1_baseline/bin/python/06_the_logger` | Sources `$HOME/code/virtualenv/claude/bin/activate` | **Verified NOT broken** — see note below, correcting the 05 plan's assumption |

### Correction to a stale assumption from the 05 plan

The `05_agent_loop` plan asserted `bin/python/05_agent_loop` was "confirmed
broken" for sourcing `$HOME/code/virtualenv/claude/bin/activate` instead of
`$ROOT/.venv/bin/activate`, and prescribed a fix. **Re-verified fresh for
this plan: that fix was never applied, and it doesn't need to be.**
`~/code/virtualenv/claude` exists and is a real venv on this machine — every
`bin/python/*` launcher (00 through 06, including the already-present
`06_the_logger`) consistently sources it, and it works. `.venv` at the repo
root also exists (created directly via `python3 -m venv .venv` per the
READMEs' own manual instructions) but the `bin/` launchers were never wired
to it and don't need to be. **No `bin/` changes are in scope for this
step.** Lesson for future plans in this series: verify launcher scripts
against the actual filesystem, not a previous plan document's claim.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/logger.py` — `Logger` class (see below)

**FILL (small gaps/additions to existing files):**
- `boukensha/__init__.py` — add module-level `config()`, `quiet()`,
  `loud()`, `is_quiet()`, `debug()`, `is_debug()` functions; add
  `from .logger import Logger`; drop `LoopError` from the import and
  `__all__`
- `boukensha/agent.py` — add `logger=None` param (see "mutable default
  argument" note below) defaulting to a fresh `Logger()`; wire logging
  calls into `run`, `_wrap_up`, `_handle_tool_calls`; wrap
  `self.registry.dispatch(...)` in `try/except Exception`; add
  `_log_response` and `_normalized_usage` helpers
- `boukensha/errors.py` — remove `LoopError`

**REMOVE (parity with upstream deletions):**
- `boukensha/config.py` — remove `mud_host`, `mud_port`, `mud_username`,
  `mud_password` properties (and the `# ---------- MUD connection
  ---------------------------------------------` section header)

**CHANGE (already present as 05's copy, must be rewritten for this step's
topic):**
- `examples/example.py` — add `logger = Logger()`, thread `logger=logger`
  into `Agent(...)`, banner text update
- `README.md` — rewrite (see below)

**LEAVE AS-IS (confirmed identical to Ruby 05, or a no-op change on the
Ruby side too):**
- `boukensha/context.py` (Ruby's diff here is whitespace-only)
- `boukensha/prompt_builder.py` (`self.backend` is already a public
  attribute; Ruby's `attr_reader` addition is a no-op for Python)
- `boukensha/tool.py`, `boukensha/message.py`, `boukensha/registry.py`
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`
- `boukensha/backends/*.py` (no backend-level changes in Ruby 06)
- `prompts/system.md`, `requirements.txt` (no new dependency — `logger.py`
  is stdlib-only: `json`, `os`, `re`, `secrets`, `datetime`, `pathlib`)

**NO CHANGE outside the step dir:**
- `bin/python/06_the_logger` — already correct, see correction note above

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree

## Target structure

```
week1_baseline/python/06_the_logger/
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
    logger.py           <- NEW
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

Identical shape to `05_agent_loop`, plus `logger.py`. No new top-level
files.

## Python environment setup

Same shared-venv / per-step-manifest model as 00–05.

- Venv path: `<repo root>/.venv` (per the README's manual setup
  instructions) — but see the correction note above: the actual `bin/`
  launchers source `~/code/virtualenv/claude` instead, and that's fine,
  out of scope, not this step's problem to fix.
- `requirements.txt`: unchanged from 05 (`PyYAML`, `python-dotenv`) — no
  new dependency for logging.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add `config`/`quiet`/`loud`/`is_quiet`/`debug`/`is_debug` module functions and `Logger` export; drop `LoopError` |
| `lib/boukensha/logger.rb` | `boukensha/logger.py` | NEW — see below |
| `lib/boukensha/agent.rb` | `boukensha/agent.py` | Add logger wiring, tool-error rescue, response/usage logging helpers |
| `lib/boukensha/config.rb` | `boukensha/config.py` | Remove the four `mud_*` properties |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | Remove `LoopError` |
| `lib/boukensha/context.rb` | `boukensha/context.py` | No change (Ruby diff is whitespace-only) |
| `lib/boukensha/prompt_builder.rb` | `boukensha/prompt_builder.py` | No change (`backend` already public) |
| `lib/boukensha/tool.rb`, `message.rb`, `registry.rb`, `tasks/*.rb`, `backends/*.rb` (all unchanged) | matching `.py` files | No change |
| `examples/example.rb` | `examples/example.py` | Add `Logger`, banner text |
| `Gemfile` (unchanged) | `requirements.txt` (unchanged) | No new dependency either side |
| `README.md` | `README.md` | Rewrite — logger design, session log format, method table |
| `bin/ruby/06_the_logger` (already correct) | `bin/python/06_the_logger` (already correct) | No change either side |

## New class behavior (the actual porting work)

### `boukensha/__init__.py` — module-level state

Ruby's `module Boukensha` gains six singleton-style methods
(`self.config`, `self.quiet!`, `self.loud!`, `self.quiet?`, `self.debug!`,
`self.debug?`) plus three instance variables (`@quiet`, `@debug`,
`@config`) on the module object itself. Ruby bang/question-mark method
names (`quiet!`, `quiet?`) aren't valid Python identifiers, so this maps to
plain verb/predicate names:

```python
_quiet = False
_debug = False
_config = None


def config():
    global _config
    if _config is None:
        _config = Config()
    return _config


def quiet():
    global _quiet
    _quiet = True


def loud():
    global _quiet
    _quiet = False


def is_quiet():
    return _quiet


def debug():
    global _debug
    _debug = True


def is_debug():
    return _debug
```

Placed right after `from .config import Config`, mirroring where Ruby
defines the module block (immediately after `require_relative
"boukensha/config"`), even though — unlike Ruby — Python's import
mechanics don't actually *require* this placement (see the circular-import
note under `logger.py` below: `Logger` never touches these functions at
its own import time, only when a `Logger` is constructed at runtime, long
after `boukensha/__init__.py` has finished executing).

`quiet`/`loud`/`is_quiet` are ported for parity even though nothing in this
step calls them yet — same situation Ruby is in (`@quiet` is set up but
unused so far), same reasoning the 05 plan used for porting the
then-unused `LoopError`: a later step may start using it, and skipping it
now just creates a future gap to notice again. **`debug`/`is_debug` *are*
used** — by `Logger.raw`.

**A Python-specific wrinkle, verified safe:** `from .config import Config`
has a side effect of setting `boukensha.config` (the package attribute) to
the `boukensha.config` *submodule*. Defining `def config():` afterward in
the same file **overwrites that attribute** with the function, so
`boukensha.config` becomes the method (matching the desired
`Boukensha.config` parity) rather than the submodule. Checked this is safe
project-wide: nothing anywhere in the repo does `boukensha.config.Xyz`
attribute access — every call site uses `from boukensha.config import
Config` (or `from .config import Config`), a direct submodule import that
resolves via `sys.modules` independent of whatever the package's `config`
attribute currently points to. No call site breaks.

`Config`, `Player`, `Tool`, etc. stay capitalized-class imports as before;
`LoopError` is dropped from the import line and from `__all__`. `Logger`
is added to both.

### `boukensha/logger.py` — the `Logger` class

```python
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    DEFAULT_SESSION_DIR = "sessions"

    def __init__(self, *, session_id=None, dir=None, log=None, snapshot=None):
        self.session_id = session_id or self._generate_session_id()
        self.path = Path(log) if log else Path(dir or self._default_dir()) / f"{self.session_id}.jsonl"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a")
        event = {"phase": "session_start"}
        if snapshot:
            event.update(snapshot)
        self._write(event)

    def iteration(self, *, n, max):
        self._write({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, *, kind, n, max):
        self._write({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def turn_end(self, *, reason, iterations, tokens=None):
        self._write({"phase": "turn_end", "reason": reason, "iterations": iterations, "tokens": tokens})

    def prompt(self, *, messages, tools):
        self._write({
            "phase": "prompt",
            "message_count": len(messages),
            "messages": [self._serialize_message(m) for m in messages],
            "tool_count": len(tools),
            "tools": list(tools.keys()),
        })

    def tool_call(self, *, name, args):
        self._write({"phase": "tool_call", "name": name, "args": args})

    def tool_result(self, *, name, result, ok=True, error=None):
        self._write({"phase": "tool_result", "name": name, "result": str(result), "ok": ok, "error": error})

    def response(self, *, text, usage=None, stop_reason=None, task=None, backend=None):
        event = {
            "phase": "response",
            "text": str(text).strip(),
            "usage": usage,
            "stop_reason": stop_reason,
        }
        event.update(self._execution_metadata(task=task, backend=backend, usage=usage))
        self._write(event)

    def raw(self, *, data):
        from . import is_debug  # deferred: see circular-import note below
        if not is_debug():
            return
        self._write({"phase": "raw", "data": data})

    def close(self):
        if self._file:
            self._file.close()

    # ---------- internals ----------------------------------------------

    def _default_dir(self):
        from . import config  # deferred: see circular-import note below
        return os.path.join(config().dir, self.DEFAULT_SESSION_DIR)

    def _write(self, event):
        record = {**event, "session_id": self.session_id, "at": self._now_iso()}
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()

    @staticmethod
    def _now_iso():
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _generate_session_id():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _serialize_message(msg):
        return {"role": msg.role, "content": msg.content}

    def _execution_metadata(self, *, task, backend, usage):
        if not (task or backend or usage):
            return {}

        tokens = self._usage_tokens(usage)
        metadata = {
            "task": self._task_name(task),
            "provider": self._provider_name(backend),
            "model": backend.model if backend else None,
            "usage_unit": backend.usage_unit if backend and hasattr(backend, "usage_unit") else None,
            "usage_level": backend.usage_level if backend and hasattr(backend, "usage_level") else None,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": self._estimate_cost(backend, tokens),
        }
        return {k: v for k, v in metadata.items() if v is not None}

    @staticmethod
    def _task_name(task):
        if task is None:
            return None
        if hasattr(task, "task_name"):
            return task.task_name()
        return str(task)

    @staticmethod
    def _provider_name(backend):
        if backend is None:
            return None
        name = type(backend).__name__
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()

    @staticmethod
    def _usage_tokens(usage):
        usage = usage or {}
        return {
            "input": Logger._first_int(usage, "input_tokens", "prompt_tokens", "promptTokenCount", "prompt_eval_count"),
            "output": Logger._first_int(usage, "output_tokens", "completion_tokens", "candidatesTokenCount", "eval_count"),
        }

    @staticmethod
    def _first_int(d, *keys):
        for key in keys:
            value = d.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _estimate_cost(backend, tokens):
        if backend is None or not hasattr(backend, "estimate_cost"):
            return None
        if tokens["input"] is None or tokens["output"] is None:
            return None
        return backend.estimate_cost(input_tokens=tokens["input"], output_tokens=tokens["output"])
```

Line-for-line notes against `logger.rb`:

- **Keyword-only params (`*,`).** Every Ruby method here takes required
  keyword args (`n:`, `name:`, `result:`, ...). Matches this codebase's
  existing precedent of using `*`-keyword-only signatures specifically
  where Ruby uses required keywords (`Agent.__init__` already does this);
  positional-with-defaults elsewhere (e.g. `Context.add_message`) stays
  positional because Ruby's `add_message` isn't keyword-required either.
- **`max` as a parameter name shadows the builtin.** Kept anyway — `n:`
  and `max:` in `iteration`/`limit_reached` mirror Ruby exactly, the
  method bodies never call the builtin `max()`, and renaming would be
  divergence for its own sake. Flagged here so it isn't mistaken for an
  oversight.
- **`Time.now.iso8601` → `datetime.now().astimezone().isoformat(timespec="seconds")`.**
  Ruby's `iso8601` defaults to second precision with a local UTC offset
  (e.g. `2026-07-24T17:31:05-05:00`); `.astimezone()` on a naive
  `datetime.now()` attaches the local offset, and `timespec="seconds"`
  drops microseconds to match. Verified against a real captured log line
  (`"at":"2026-07-24T17:31:07-05:00"`) while researching the existing
  `.boukensha/sessions/*.jsonl` files in this repo.
- **`SecureRandom.hex(4)` → `secrets.token_hex(4)`** — both produce 8 lowercase
  hex characters from a CSPRNG.
- **`result.to_s` → `str(result)`.** Ruby's `Hash#to_s`/`Array#to_s`
  produce a Ruby-syntax string, not JSON — this codebase's tools already
  return plain strings (`list_directory` joins with `", "`), so in
  practice this is always already a string on both sides; `str()` is the
  faithful equivalent for any tool that returns something else.
- **`.compact` → dict comprehension dropping `None` values.** Same
  semantics: only keys with a non-nil/non-`None` value survive into the
  logged `response` event, matching the real sample logs (e.g. no
  `usage_level` key appears when a backend's model table doesn't set
  one).
- **`backend&.respond_to?(:foo)` → `backend and hasattr(backend, "foo")`.**
  Preserved as a defensive check even though every current backend
  (`Base` subclasses) always defines `usage_unit`/`usage_level`/
  `estimate_cost` — same defensive posture Ruby takes.
- **snake_case provider name.** `"OllamaCloud"` → `"ollama_cloud"`,
  `"OpenAI"` → `"open_ai"` (yes, matching Ruby's regex exactly — `OpenAI`
  splits before the trailing `AI` too, since Ruby's
  `/([a-z\d])([A-Z])/` matches the `n`/`A` boundary in `OpenAI` the same
  way it matches the `a`/`C` boundary in `OllamaCloud`). Verified by
  hand-tracing both the Ruby regex and the Python
  `re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)` lookaround equivalent
  against `Anthropic`, `Gemini`, `OpenAI`, `Ollama`, `OllamaCloud` — same
  five outputs both languages.
- **Deferred imports (`from . import config` / `from . import is_debug`
  *inside* the method bodies, not at module top).** This is the one real
  structural difference from Ruby, and it's deliberate, not cosmetic.
  Ruby has no import statements at all — `Boukensha.config` and
  `Boukensha.debug?` are just always reachable once the module is
  defined, regardless of `require` order, because Ruby resolves constant
  and module-method lookups at call time against the live global
  namespace. Python's `from .logger import Logger` runs *during*
  `boukensha/__init__.py`'s own execution (package `__init__.py` files
  execute top-to-bottom, and each `from .X import Y` line runs
  synchronously as it's reached). A **top-level** `from . import config`
  inside `logger.py` would try to pull `config` off the `boukensha`
  package while it's only *partially* initialized — safe only if that
  line in `__init__.py` happens to already be past the `def config():`
  definition, which is a fragile ordering dependency to maintain forever.
  Deferring the import into the method body sidesteps this entirely:
  `_default_dir`/`raw` only run when a `Logger` is actually *used* (at
  runtime, called from `Agent.__init__`/`Agent.run`), by which point
  `boukensha/__init__.py` has long since finished executing top to
  bottom. This is the standard, idiomatic Python fix for a circular
  import between a package's `__init__.py` and one of its own submodules,
  and it means the ordering of `from .logger import Logger` relative to
  the `config()`/`debug()` function definitions in `__init__.py` no
  longer matters at all (see the `__init__.py` section above).

### `agent.py` changes

**1. Constructor — avoid the mutable-default-argument trap.**

Ruby's `logger: Logger.new` default is evaluated *fresh on every call*
that omits the keyword (Ruby evaluates keyword-argument defaults at call
time). Python default argument values are evaluated **once, at function
*definition* time** — `def __init__(self, *, logger=Logger(), ...)` would
construct exactly one `Logger` (opening exactly one session file) at
class-definition time and silently *share* it across every `Agent`
instance that doesn't pass its own logger. That's a real bug class, not a
style nit — it would mean every default-logger `Agent` writes into the
same session log. The correct Python idiom:

```python
def __init__(self, *, context, registry, builder, client, logger=None,
             task_settings=None, max_iterations=None, max_output_tokens=None):
    self.context = context
    self.registry = registry
    self.builder = builder
    self.client = client
    self.logger = logger if logger is not None else Logger()
    self.max_iterations = self._resolve_max_iterations(task_settings, max_iterations)
    self.max_output_tokens = self._resolve_max_output_tokens(task_settings, max_output_tokens)
    self.iteration = 0
```

Needs `from .logger import Logger` added alongside the existing `from
.errors import ApiError` at the top of `agent.py`.

**2. `run` — log at every phase transition:**

```python
def run(self):
    while True:
        if self._iteration_limit_reached():
            self.logger.limit_reached(kind="max_iterations", n=self.iteration, max=self.max_iterations)
            return self._wrap_up("max_iterations")

        self.iteration += 1
        self.logger.iteration(n=self.iteration, max=self.max_iterations)
        self.logger.prompt(messages=self.context.messages, tools=self.context.tools)

        response = self.client.call(**self._call_opts())
        self.logger.raw(data=response)
        parsed = self.builder.parse_response(response)

        if parsed["stop_reason"] == "tool_use":
            self._handle_tool_calls(parsed["content"], response)
        else:
            text = self._extract_text(parsed["content"])
            self._log_response(text=text, response=response)
            self.logger.turn_end(reason="completed", iterations=self.iteration)
            return text
```

The bare `print(f"[iteration {self.iteration}/{self.max_iterations}]")`
from Step 5 is **removed**, matching Ruby (`puts "[iteration ...]"` was
replaced by `@logger.iteration(...)`, not kept alongside it — the logger
is the new source of this information, not an addition to the old print
trace).

**3. `_wrap_up` — log the wind-down response and turn_end on both paths:**

```python
def _wrap_up(self, reason):
    self.context.add_message("user", self.WRAP_UP_DIRECTIVE)
    try:
        response = self.client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
        text = self._extract_text(self.builder.parse_response(response)["content"])
        text = text if text.strip() else self._fallback_message(reason)
        self._log_response(text=text, response=response)
        self.logger.turn_end(reason=reason, iterations=self.iteration)
        return text
    except ApiError:
        msg = self._fallback_message(reason)
        self.logger.turn_end(reason=reason, iterations=self.iteration)
        return msg
```

**4. `_handle_tool_calls` — takes `response` too, logs the reasoning text,
rescues a broken tool instead of propagating:**

```python
def _handle_tool_calls(self, content, response):
    tool_calls = [b for b in content if b.get("type") == "tool_use"]

    reasoning = self._extract_text(content)
    if reasoning.strip():
        reasoning_text = reasoning
    else:
        suffix = "s" if len(tool_calls) != 1 else ""
        reasoning_text = f"(tool use — {len(tool_calls)} call{suffix})"
    self._log_response(text=reasoning_text, response=response)

    self.context.add_message("assistant", content)

    for block in tool_calls:
        name = block["name"]
        args = block["input"]
        use_id = block["id"]

        self.logger.tool_call(name=name, args=args)
        try:
            result = self.registry.dispatch(name, args)
            self.logger.tool_result(name=name, result=result, ok=True)
        except Exception as e:
            result = f"ERROR: {type(e).__name__}: {e}"
            self.logger.tool_result(name=name, result=result, ok=False, error=str(e))

        self.context.add_message("tool_result", str(result), tool_use_id=use_id)
```

Notes:
- **`content.select { |b| b["type"] == "tool_use" }` computed once and
  reused** (for both the reasoning-text placeholder count and the
  dispatch loop) — matches Ruby's `tool_calls` local variable exactly,
  rather than filtering twice or iterating `content` directly as Step 5
  did.
- **`rescue StandardError => e` → `except Exception as e`.** Ruby's
  `StandardError` is "catch ordinary runtime errors, not
  Exception/NoMemoryError/etc."; Python's closest equivalent boundary is
  `Exception` (excludes `SystemExit`/`KeyboardInterrupt`/
  `GeneratorExit`, which subclass `BaseException` directly) — same
  intent, "catch a broken tool, not a process-level signal."
  `e.class`/`e.message` → `type(e).__name__`/`str(e)`.
- **This is new defensive behavior, not present in Step 5's
  `_handle_tool_calls` (Ruby or Python) — a raising tool used to blow up
  the whole turn.** Now it's caught, logged with `ok=False`, and folded
  into the conversation as an `"ERROR: ..."` tool result so the model can
  react to it instead of the process crashing. Porting this is in scope
  because it's part of Ruby 06's actual diff, not scope creep.

**5. New private helpers:**

```python
def _log_response(self, *, text, response):
    self.logger.response(
        text=text,
        usage=self._normalized_usage(response),
        stop_reason=response.get("stop_reason"),
        task=self.context.task,
        backend=self.builder.backend,
    )

@staticmethod
def _normalized_usage(response):
    if response.get("usage"):
        return response["usage"]
    if response.get("usageMetadata"):
        return response["usageMetadata"]

    usage = {k: response[k] for k in ("prompt_eval_count", "eval_count") if k in response}
    return usage or None
```

`response["stop_reason"]` (Ruby, raises `KeyError`-equivalent... actually
Ruby hashes return `nil` for a missing key) → `response.get("stop_reason")`
in Python for the same "missing key is fine, just `None`" behavior (a
plain `response["stop_reason"]` would raise `KeyError` if a backend's raw
response ever lacked the key, which Ruby's hash-index access wouldn't).
Same reasoning for `response.get("usage")` etc. over bracket access.

### `boukensha/errors.py`

```python
class UnknownToolError(Exception):
    pass


class UnsupportedModelError(Exception):
    pass


class ApiError(Exception):
    pass
```

`LoopError` removed (was never raised anywhere in either language; Ruby 06
deletes it outright rather than continuing to carry it as unused
scaffolding).

### `boukensha/config.py`

Remove the four `mud_*` properties (`mud_host`, `mud_port`,
`mud_username`, `mud_password`) and their section comment. Everything else
in `Config` — `dir`, `settings`, `tasks()`, `user_prompts_dir`, `dig()`,
`__str__`, the private `_resolve_dir`/`_load_env`/`_load_settings` — is
untouched, matching Ruby's diff exactly (only the MUD block disappears).

## `examples/example.py`

Small, targeted edit to the existing 05 example — not a rewrite:

1. Add `from boukensha.logger import Logger` to the import block.
2. After `client = Client(builder)`, insert:
   ```python
   # Writes structured JSONL events to .boukensha/sessions/<session-id>.jsonl.
   # Call boukensha.debug() before this to include the full raw API response.
   logger = Logger()
   ```
3. Add `logger=logger` to the `Agent(...)` constructor call.
4. Change the banner from `"=== BOUKENSHA Step 5: Agent Loop ==="` to
   `"=== BOUKENSHA Step 6: The Logger ==="`.

Everything else — `Config`/`system_prompt`/`Context`/`Registry` setup,
provider/backend branch, `base_dir`-anchored tool registration, the
summarization prompt — stays exactly as Step 5 left it (Ruby's
`examples/example.rb` diff for this step is equally small: formatting plus
the same three additions).

## `README.md`

Rewrite following the **Python port's own established structure** (00–05
all share it: Environment setup → New/Updated files tables → How it works
→ class method table → task configuration → run-output sample →
Considerations → Considerations (carried over) → Files table → Run
example), even though Ruby's own Step 6 README abandons the New/Updated
tables in favor of a narrower "just explain the logger" document. Content
to cover, drawn from Ruby's README plus this step's actual Python diff:

- Title `# 06 · The Logger (Python)`, link to
  `../../ruby/06_the_logger/README.md`.
- Environment setup block (unchanged pattern from 05, `pip install -r
  week1_baseline/python/06_the_logger/requirements.txt`).
- **New files:** `boukensha/logger.py`.
- **Updated files:** `boukensha/agent.py` (logger wiring, tool-error
  rescue), `boukensha/__init__.py` (`config`/`quiet`/`loud`/`is_quiet`/
  `debug`/`is_debug` module functions), `boukensha/errors.py` (`LoopError`
  removed), `boukensha/config.py` (`mud_*` properties removed),
  `examples/example.py` (`Logger` wiring).
- Session log format section: `.boukensha/sessions/<session-id>.jsonl`,
  one JSON object per line, `session_id`/`at`/`phase` on every line, two
  example lines (`session_start`, `iteration`) same as Ruby's README.
- A `response`-phase example line showing `task`/`provider`/`model`/
  `input_tokens`/`output_tokens`/`cost_usd`.
- `Logger` method table (mirrors Ruby's, Python names):

  | Method | Phase | Logs |
  |---|---|---|
  | `iteration(n=, max=)` | `iteration` | loop counter |
  | `limit_reached(kind=, n=, max=)` | `limit_reached` | iteration ceiling hit |
  | `prompt(messages=, tools=)` | `prompt` | messages, tool names |
  | `tool_call(name=, args=)` | `tool_call` | tool name and arguments |
  | `tool_result(name=, result=, ok=, error=)` | `tool_result` | tool result, success/failure |
  | `response(text=, usage=, stop_reason=, task=, backend=)` | `response` | response text, token usage, task/provider/model, estimated cost |
  | `raw(data=)` | `raw` | raw provider response, only when `boukensha.debug()` is enabled |
  | `turn_end(reason=, iterations=, tokens=)` | `turn_end` | why/when the turn ended |
  | `close()` | — | closes the underlying file handle |

- Task configuration snippet (unchanged `tasks.player` shape from 05).
- Default usage snippet:
  ```python
  logger = Logger()
  agent = Agent(context=ctx, registry=registry, builder=builder,
                client=client, logger=logger, task_settings=player_settings)
  ```
  plus the `session_id=`/`dir=` override forms.
- Debug events section: `boukensha.debug()` before constructing/running the
  agent to include raw provider responses in the log.
- **New tool-error-handling behavior**, called out explicitly since it's a
  real behavior change bundled into this step: a raising tool no longer
  crashes the turn — it's caught, logged as `tool_result` with `ok=False`,
  and surfaced to the model as an `"ERROR: ..."` result.
- **Considerations (carried over):** keep 05's three items (no persistent
  memory/context compaction, `.yaml`-not-`.yml`), **drop** the
  "`LoopError` exists but is unused" item (no longer true — it's deleted,
  not just unused) and the "no cost/usage logging wired in yet" item (this
  step *is* that wiring — say so, don't carry the gap forward).
- Files table: add `boukensha/logger.py`.
- Run example: `./week1_baseline/bin/python/06_the_logger`.

## Expected output / how to verify parity

Same situation as Step 5 — this makes real HTTP calls (unless
`tasks.player.provider` is `ollama` against a local server), so "expected
output" isn't a fixed transcript. Verify parity by:

1. Running both `bundle exec ruby examples/example.rb` under
   `ruby/06_the_logger` and `python3 examples/example.py` under
   `python/06_the_logger` (or the matching `bin/` launchers), then diffing
   the *shape* (not exact content) of the two newest files under
   `.boukensha/sessions/`.
2. Confirming both produce the same **sequence of `phase` values** for a
   given run: `session_start`, then per iteration `iteration` → `prompt` →
   (`raw` if debug) → `response` → (`tool_call`/`tool_result` pairs, if
   any) → ... → final `response` → `turn_end`.
3. Confirming a `response` line in both carries the same field set:
   `text`, `usage`, `stop_reason`, `task`, `provider`, `model`,
   `usage_unit`, `input_tokens`, `output_tokens`, `cost_usd` (exact
   numbers will differ per live call, but the *keys present* and their
   *types* should match — this repo's existing
   `.boukensha/sessions/*.jsonl` files, captured from real Ruby runs, are
   a good reference for the exact shape).
4. Deliberately registering a tool whose lambda raises, confirming both
   languages log `tool_result` with `ok=false`/`ok=False` and
   `error`/`error` set, and that the turn continues instead of crashing.
5. Setting `boukensha.debug()` / `Boukensha.debug!` before building the
   agent and confirming both emit `raw` lines; confirming neither does
   without it.
6. Confirming `Logger.new`/`Logger()` called twice with no `session_id=`
   override produces two **different** session ids/files in both
   languages (guards specifically against the mutable-default-argument
   bug described above — the single most likely porting mistake for this
   step).

## Carried-over known gaps (not fixed in this port, for parity)

Same items Ruby's own README implicitly leaves alone at this step:
- No persistent memory or context compaction — still a later step.
- Settings file must be exactly `.yaml`, not `.yml` (carried from 00).
- `quiet`/`loud`/`is_quiet` are wired up but **nothing reads them yet** —
  same as Ruby's `@quiet`/`quiet?`/`quiet!`/`loud!`, ported for parity,
  not used until a later step.
- The logger opens its file handle in `__init__` and is never closed
  automatically (no context-manager protocol on either side) — `close()`
  exists but nothing calls it. Matches Ruby exactly; not this step's
  problem to fix.

## Decisions already made (from the 00–05 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories; **no launcher changes
  this step** (see correction note above).
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+ (unchanged; `datetime.astimezone()` on a
  naive `datetime` and `secrets.token_hex` are both available since 3.6).
- Output parity: exact field-for-field match where behavior is
  deterministic (log event shape, field names); model responses and
  tool-call sequences remain non-deterministic.
- `requirements.txt`: unchanged, no new dependency.
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: everything from `05_agent_loop` carries
  over unchanged except the additions/removals listed above.
- README vs. actual Ruby implementation: follow the executable code, not
  aspirational README text (same lesson the 05 plan already learned from
  Ruby 05's stale `context.rb` claim) — directly relevant again here,
  since Ruby 06's own README doesn't mention the `config.rb`/`errors.rb`
  deletions or the tool-error-rescue addition at all; both are only
  visible in the actual diff, not the prose.

## Remaining cosmetic decisions

- **Module-level function names** (`config`, `quiet`, `loud`, `is_quiet`,
  `debug`, `is_debug`) chosen as the closest Pythonic equivalent to
  Ruby's `self.config`/`self.quiet!`/`self.loud!`/`self.quiet?`/
  `self.debug!`/`self.debug?` — verb for the "set/enable" forms
  (`quiet()`, `debug()`), `is_`-prefixed predicate for the boolean-query
  forms (`is_quiet()`, `is_debug()`), since Python has no `?`/`!` method
  suffix convention. `config()` stays bare (matches Ruby's bare
  `self.config`, and there's no boolean-query/setter pair to disambiguate
  it from).
- **Deferred (`from . import ...`) imports inside `Logger._default_dir`
  and `Logger.raw`, rather than a top-level import in `logger.py`.**
  Structural necessity, not style — see the detailed rationale in the
  `logger.py` section above. This is the one place this port's shape
  diverges from a literal transliteration of Ruby's file, because Ruby's
  `require`-based module system doesn't have Python's
  partially-initialized-package problem to begin with.
- **`logger=None` + `self.logger = logger if logger is not None else
  Logger()` instead of a literal `logger=Logger()` default.** Also
  structural, not style — a literal transliteration would silently share
  one `Logger` (and one open file) across every default-logger `Agent`.
  See "mutable default argument" note above.
- **Keeping `max` as a parameter name in `Logger.iteration`/
  `Logger.limit_reached` despite shadowing the builtin.** Matches Ruby's
  `max:` exactly; the method bodies never need the builtin, so the shadow
  is harmless and renaming would be unmotivated divergence.
- **`str(result)` instead of a JSON-aware serialization for
  `Logger.tool_result`.** Matches Ruby's `result.to_s` — this is
  deliberately *not* JSON-safe-guaranteed the way `json.dumps` would be
  (a tool returning a non-JSON-serializable object still logs fine as a
  string repr, same as Ruby), consistent with every tool in this codebase
  already returning plain strings.
