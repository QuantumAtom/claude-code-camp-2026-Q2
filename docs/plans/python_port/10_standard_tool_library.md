# Python Port Plan — 10_standard_tool_library

## Goal

Port `week1_baseline/ruby/10_standard_tool_library` to
`week1_baseline/python/10_standard_tool_library`. Same behavior, new
language, three new tool modules (`FileSystem`, `Shell`, `Mud`) plus the
small set of wiring changes they depend on. No new features beyond what
Ruby 10 actually adds. **Plan only — no source files are touched by
writing this document.**

**This plan only covers what changed between the Python baseline and
Ruby 10.** Everything already ported correctly through `08_the_repl_loop`
(`run()`, `repl()`, `Agent`, the logger, per-backend `parse_response`,
task settings, client retry/401 handling, the 3-step config dir lookup)
stays exactly as it is. Nothing gets rewritten from scratch and nothing
that already works gets touched or regenerated.

**Starting point:** `week1_baseline/python/10_standard_tool_library`
already exists as a byte-for-byte copy of the finished
`week1_baseline/python/08_the_repl_loop` tree (confirmed via
`diff -rq python/08_the_repl_loop/boukensha python/10_standard_tool_library/boukensha`,
excluding `__pycache__` — zero output; same for the top-level files).
**There is no Python `09_global_executable` step** — Ruby has one, Python
does not, so this port has to fold in whatever functional (non-packaging)
changes Ruby made between its steps 08 and 10 in a single pass, same as
every prior step's "in-place edit of the copied tree," not a from-scratch
build.

## Source of truth (what changed, Ruby 08 → Ruby 10)

Verified with `diff -rq ruby/08_the_repl_loop/lib ruby/10_standard_tool_library/lib`,
`diff -rq ruby/08_the_repl_loop ruby/10_standard_tool_library` (top level),
plus a full-text diff of every file it flagged, and cross-checked against
the intermediate `ruby/09_global_executable` snapshot to see which changes
belong to which step:

| Ruby file | Change vs. 08 | Status |
|---|---|---|
| `lib/boukensha/tools/file_system.rb` | **NEW** — `FileSystem.register`: `pwd`, `list_directory`, `read_file`, `write_file`, `delete_file`, `search_files` (all sandboxed to `working_dir`) | New — see design section below |
| `lib/boukensha/tools/shell.rb` | **NEW** — `Shell.register`: `run_command`, with a timeout and an optional allow-list | New — see design section below |
| `lib/boukensha/tools/mud.rb` | **NEW** — `Mud.register`: 27 MUD-gameplay tools built on a `MudManager::Session`/`MudManager::Primitives` connection | New — see design section below. **Depends on the `mud_manager` gem**, a separate ~690-line library at `week0_explore/mud_manager/` with no Python port anywhere in the repo yet (see scope decision below) |
| `lib/boukensha/context.rb` | Adds `working_dir:` to `Context.new`, stored as `attr_reader :working_dir` (expanded via `File.expand_path`) | `context.py` needs a matching `working_dir` param/attribute |
| `lib/boukensha/version.rb` | `VERSION` bumped `0.8.0` → `0.9.0` (in Ruby 09) → `0.10.0` (in Ruby 10) | `version.py` needs to become `"0.10.0"` — see version-numbering note below |
| `lib/boukensha/repl.rb` | `Repl#initialize` gains a `mud:` keyword, stored as `@mud`; `#banner` gains a `mud:` status line built by a new private `mud_status_string`/`probe_mud` (TCP-reachability-only check, to avoid double-login) | `repl.py` needs the same `mud=` param and banner line |
| `lib/boukensha.rb` | `self.run`/`self.repl` both gain `working_dir:`, `allowed_commands:`, `shell_timeout:`, `mud:` keywords; auto-register `Tools::FileSystem`/`Tools::Shell` when `working_dir` is set, auto-register `Tools::Mud` when `mud` is set or resolvable from config; new private `mud_opts_from_config` helper; `require_relative` for the three new tool files | `__init__.py` needs matching `run()`/`repl()` signatures and wiring |
| `lib/boukensha/client.rb` | **Ruby 09 removed** the 401-specific `ApiError` check added in Ruby 08; **Ruby 10 does not restore it** | **Do not port this regression** — see note below |
| `lib/boukensha/config.rb` | **Ruby 09 reverted** `resolve_dir` from the 3-step lookup (env var → cwd `.boukensha/` → `~/.boukensha`) back to a 2-step lookup; **Ruby 10 does not restore the 3-step version** | **Do not port this regression** — see note below |
| `lib/boukensha/config.rb` | `mud_host`/`mud_port`/`mud_username`/`mud_password`/`dig` — already present in Ruby **08** (unchanged since), so not part of this step's delta at all | `config.py` already has matching methods (confirmed — see below) |
| `lib/boukensha/registry.rb`, `tool.rb`, `errors.rb`, `message.rb`, `prompt_builder.rb`, `agent.rb`, `run_dsl.rb`, `backends/*.rb`, `tasks/*.rb` | Unchanged (confirmed via `diff -q`, file by file) | No change |
| `prompts/system.md` | Unchanged | No change |
| `lib/boukensha_loader.rb`, `bin/boukensha` | **NEW in Ruby 09** (`BOUKENSHA_PATH`/`~/.boukensharc` resolution for the installed gem's global executable) | **Out of scope** — see below |
| `Gemfile`, `Gemfile.lock`, `boukensha.gemspec`, `boukensha-0.10.0.gem`, `bin/` (gem bindir) | Ruby packaging artifacts (the `mud_manager` gem path dependency, gem build) | **Out of scope** — see below |
| `examples/example.rb` | Rewritten around `Boukensha.run(task: "Connect to the MUD...", working_dir: false)` instead of the step 08 REPL/file-reading demo | `example.py` needs the equivalent rewrite |
| `README.md` | Full rewrite: FileSystem/Shell tables, new `run`/`repl` keyword args, direct-registration examples, a "Technical Consideration" note about hardcoding the `mud_manager` gem path | See README plan below |
| `week1_baseline/bin/ruby/10_standard_tool_library` | Already exists and is correct | No change |
| `week1_baseline/bin/python/10_standard_tool_library` | **Does not exist yet** | **New file needed**, matching the `08_the_repl_loop` launcher pattern |

### Two regressions in Ruby's own history — deliberately not carried forward

Diffing `ruby/08_the_repl_loop` → `ruby/09_global_executable` → `ruby/10_standard_tool_library`
file-by-file (not just 08→10) surfaced something worth flagging explicitly: Ruby step 09
(`global_executable`, which has no Python counterpart) **reverted two things Ruby 08 had
already fixed**, and step 10 never restored them:

1. `client.rb` lost the `response.code.to_i == 401` → `"authentication failed (401)..."`
   check (present in 08, gone in 09 and 10).
2. `config.rb`'s `resolve_dir` reverted from the 3-step lookup (env var → cwd
   `.boukensha/` if it's a directory → `~/.boukensha`) back to a 2-step lookup
   (env var → `~/.boukensha` only).

Python's `client.py` and `config.py` already have both fixes (ported correctly
in the `08_the_repl_loop` step, per that step's own plan). **This port does
not regress them to match Ruby 10's state.** Porting a bug that Ruby itself
introduced by accident between unrelated steps — and that has nothing to do
with this step's actual topic (a standard tool library) — would make Python
strictly worse for no reason and contradicts the instruction to build on the
existing, already-working Python code. `client.py` and `config.py` need **no
changes** in this step.

### Scope decision: `mud_manager` gets a full Python port

Ruby's `tools/mud.rb` is the largest single addition in this step, and it
only works because of a separate local gem, `mud_manager`
(`week0_explore/mud_manager/`, ~690 lines: `Session` — a threaded telnet
connection with IAC-stripping and prompt-detection — and `Primitives` — a
stateless library of ~40 typed CircleMUD command builders). No Python
equivalent exists anywhere in the repo. Rather than stub `tools/mud.py` out
or skip it, **this plan includes a full translation of `mud_manager` into
Python**, living alongside the Ruby gem at `week0_explore/mud_manager/python/`
(mirroring the Ruby gem's location, the same way `week1_baseline/ruby/*` and
`week1_baseline/python/*` mirror each other), so `boukensha/tools/mud.py` is
actually functional, not aspirational. This was confirmed as the intended
scope before writing this plan (the alternative would have been a stub with
a follow-up plan, or dropping MUD tooling from this step entirely).

## Concrete delta (the actual work)

**ADD (net-new files):**
- `week0_explore/mud_manager/python/mud_manager/__init__.py`
- `week0_explore/mud_manager/python/mud_manager/session.py`
- `week0_explore/mud_manager/python/mud_manager/primitives.py`
- `boukensha/tools/__init__.py` (empty — a plain namespace package)
- `boukensha/tools/file_system.py`
- `boukensha/tools/shell.py`
- `boukensha/tools/mud.py`
- `bin/python/10_standard_tool_library` — launcher script (doesn't exist yet)

**FILL (small additions to existing files, currently identical to 08):**
- `boukensha/context.py` — add `working_dir` param/attribute
- `boukensha/version.py` — bump to `"0.10.0"`
- `boukensha/repl.py` — add `mud=` param, banner MUD status line
- `boukensha/__init__.py` — add `working_dir`/`allowed_commands`/
  `shell_timeout`/`mud` kwargs to `run()` and `repl()`, tool
  auto-registration, `_mud_opts_from_config` helper

**CHANGE (rewrite for this step's topic):**
- `examples/example.py` — rewrite around `boukensha.run(task=..., working_dir=False)`
  with a MUD task, matching Ruby's new `example.rb`
- `README.md` — rewrite

**LEAVE AS-IS (confirmed identical Ruby 08→10, or a deliberately-not-ported
Ruby regression):**
- `boukensha/client.py` — **no change** (see regression note above)
- `boukensha/config.py` — **no change** (see regression note above; `mud_host`
  etc. already present since 08, confirmed via `grep -n "mud_" config.py`)
- `boukensha/agent.py`, `message.py`, `errors.py`, `prompt_builder.py`,
  `logger.py`, `run_dsl.py`, `registry.py`, `tool.py`
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`
- `boukensha/backends/*.py`
- `prompts/system.md`
- `requirements.txt` — unchanged; the `mud_manager` Python port needs zero
  third-party dependencies (only `socket`/`threading`/`time`/`re`, same as
  Ruby's own gemspec: "No external dependencies — socket and thread are
  stdlib")

**OUT OF SCOPE (Ruby packaging, no Python equivalent needed):**
- `lib/boukensha_loader.rb`, `bin/boukensha` — the installed gem's
  `BOUKENSHA_PATH`/`~/.boukensharc` resolution logic, added in Ruby 09
  (`global_executable`), which has no Python step and no Python packaging
  equivalent in this course (Python steps are run via `bin/python/<step>`
  launcher scripts, not an installed CLI)
- `Gemfile`, `Gemfile.lock`, `boukensha.gemspec`, `boukensha-0.10.0.gem` —
  Ruby's gem manifest/build artifacts, including the `mud_manager` gem path
  dependency (`gem "mud_manager", path: "../../../week0_explore/mud_manager"`)
  that the Ruby README's "Technical Consideration" complains about having to
  hardcode — Python's equivalent (a `sys.path` insert pointing at the sibling
  `week0_explore/mud_manager/python/` directory) is covered below, not a gem
  dependency

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree

## Target structure

```
week0_explore/mud_manager/python/
  mud_manager/
    __init__.py
    session.py
    primitives.py

week1_baseline/python/10_standard_tool_library/
  README.md
  requirements.txt
  prompts/
    system.md
  boukensha/
    __init__.py
    version.py
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    prompt_builder.py
    logger.py
    run_dsl.py
    client.py
    agent.py
    repl.py
    tools/                 <- NEW
      __init__.py
      file_system.py
      shell.py
      mud.py
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

week1_baseline/bin/python/10_standard_tool_library   <- NEW
```

## Python environment setup

Same shared-venv / per-step `requirements.txt` model as 00–08.
`requirements.txt` unchanged (`PyYAML`, `python-dotenv`) — no new
dependency. The `mud_manager` Python package is imported via a `sys.path`
insert from `boukensha/tools/mud.py` (see below), not installed as a
package — matching this project's established "no `uv`/`pyproject.toml`"
decision and Ruby's own "socket/thread are stdlib, no dependencies" note.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `week0_explore/mud_manager/lib/mud_manager.rb` | `week0_explore/mud_manager/python/mud_manager/__init__.py` | Re-exports `Session` and `primitives` |
| `week0_explore/mud_manager/lib/mud_manager/session.rb` | `week0_explore/mud_manager/python/mud_manager/session.py` | Threaded socket session, IAC stripping, login dance |
| `week0_explore/mud_manager/lib/mud_manager/primitives.rb` | `week0_explore/mud_manager/python/mud_manager/primitives.py` | ~40 stateless command builders |
| `lib/boukensha/tools/file_system.rb` | `boukensha/tools/file_system.py` | NEW |
| `lib/boukensha/tools/shell.rb` | `boukensha/tools/shell.py` | NEW |
| `lib/boukensha/tools/mud.rb` | `boukensha/tools/mud.py` | NEW — depends on the new `mud_manager` package |
| `lib/boukensha/context.rb` | `boukensha/context.py` | Add `working_dir` |
| `lib/boukensha/version.rb` | `boukensha/version.py` | `VERSION = "0.10.0"` |
| `lib/boukensha/repl.rb` | `boukensha/repl.py` | Add `mud=`, banner MUD status |
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add tool auto-registration to `run()`/`repl()` |
| `lib/boukensha/client.rb` | `boukensha/client.py` | **No change** (regression not ported) |
| `lib/boukensha/config.rb` | `boukensha/config.py` | **No change** (regression not ported; mud accessors already present) |
| `lib/boukensha/registry.rb`, `tool.rb`, `errors.rb`, `message.rb`, `prompt_builder.rb`, `agent.rb`, `run_dsl.rb`, `tasks/*.rb`, `backends/*.rb` | matching `.py` files | No change |
| `examples/example.rb` | `examples/example.py` | Rewrite around `boukensha.run(..., working_dir=False)` MUD demo |
| `Gemfile`/`Gemfile.lock`/gemspec (out of scope) | `requirements.txt` (unchanged) | No new dependency |
| `README.md` | `README.md` | Rewrite |
| `lib/boukensha_loader.rb`, `bin/boukensha` (out of scope) | — | No Python equivalent this step |
| `bin/ruby/10_standard_tool_library` (already correct) | `bin/python/10_standard_tool_library` (**missing, must create**) | |

## New/changed class behavior (the actual porting work)

### `week0_explore/mud_manager/python/mud_manager/session.py` (new)

Direct translation of `MudManager::Session`. Concurrency-primitive mapping:
Ruby `Mutex` + `ConditionVariable` → Python `threading.Lock` +
`threading.Condition(lock)`; `Thread.new { ... }` → a daemon
`threading.Thread`; `Process.clock_gettime(Process::CLOCK_MONOTONIC)` →
`time.monotonic()`; `@socket.readpartial(4096)` → `socket.recv(4096)`
(same "block for some data, `b""`/`nil` at EOF" semantics).

```python
import re
import socket
import sys
import threading
import time


class Session:
    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 4000
    DEFAULT_TIMEOUT = 10.0

    IAC, DONT, DO, WONT, WILL, SB, SE = 0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0xF0

    class Error(Exception):
        pass

    class ConnectionError(Error):
        pass

    class LoginError(Error):
        pass

    class Timeout(Error):
        pass

    PROMPT_SENTINEL = "> "

    # Sentinels for send_command meaning "just press return" — Ruby uses the
    # symbols :return/:enter, which have no Python equivalent; unique sentinel
    # objects are the direct, unambiguous stand-in (a raw string like "return"
    # would collide with someone actually wanting to send that word).
    RETURN = object()
    ENTER = object()

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self._timeout = timeout
        self._socket = None
        self._reader = None
        self._buffer = ""
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._closed = False
        self._last_recv_at = None

    def open(self):
        if self._socket is not None:
            raise Session.Error("already open")
        try:
            self._socket = socket.create_connection((self.host, self.port))
        except OSError as e:
            raise Session.ConnectionError(f"connect {self.host}:{self.port} failed: {e}") from e
        self._closed = False
        self._start_reader()
        return self

    def is_open(self):
        return self._socket is not None and not self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._socket is not None:
                self._socket.close()
        except OSError:
            pass  # already closed / broken — fine
        if self._reader is not None:
            self._reader.join(1)
        self._socket = None
        self._reader = None

    # Send a command. Accepts a str, a primitives.Command (anything with a
    # .raw attribute), or Session.RETURN/Session.ENTER for a bare keypress.
    def send_command(self, command):
        if not self.is_open():
            raise Session.Error("session not open")
        if command is Session.RETURN or command is Session.ENTER:
            line = ""
        elif hasattr(command, "raw"):
            line = command.raw
        else:
            line = str(command)
        self._socket.sendall((line + "\r\n").encode("utf-8"))
        return line

    send = send_command

    def drain(self):
        with self._lock:
            out, self._buffer = self._buffer, ""
            return out

    def read_until_quiet(self, quiet_seconds=1.0, timeout=None):
        if not self.is_open():
            raise Session.Error("session not open")
        deadline = time.monotonic() + (timeout or self._timeout)
        with self._lock:
            while True:
                remaining_total = deadline - time.monotonic()
                if remaining_total <= 0:
                    break
                if (self._last_recv_at is not None
                        and (time.monotonic() - self._last_recv_at) >= quiet_seconds
                        and self._buffer):
                    break
                if self._last_recv_at is not None and self._buffer:
                    wait_for = quiet_seconds - (time.monotonic() - self._last_recv_at)
                else:
                    wait_for = remaining_total
                wait_for = min(wait_for, remaining_total)
                if wait_for <= 0:
                    break
                self._cv.wait(wait_for)
            out, self._buffer = self._buffer, ""
            return out

    def read_until(self, pattern, timeout=None):
        if not self.is_open():
            raise Session.Error("session not open")
        regex = pattern if isinstance(pattern, re.Pattern) else re.compile(re.escape(pattern))
        deadline = time.monotonic() + (timeout or self._timeout)
        with self._lock:
            while True:
                m = regex.search(self._buffer)
                if m:
                    cut = m.end()
                    out, self._buffer = self._buffer[:cut], self._buffer[cut:]
                    return out
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Session.Timeout(f"read_until {pattern!r} after {timeout}s")
                if self._closed:
                    raise Session.ConnectionError("socket closed while waiting")
                self._cv.wait(remaining)

    def read_until_prompt(self, timeout=None):
        try:
            return self.read_until(Session.PROMPT_SENTINEL, timeout=timeout)
        except Session.Timeout:
            print("[mud_manager.Session] prompt not detected within timeout; "
                  "returning buffered content", file=sys.stderr)
            return self.drain()

    def login(self, username, password):
        self.read_until(re.compile(r"By what name do you wish to be known.*\?", re.IGNORECASE))
        self.send_command(username)
        self.read_until(re.compile(r"Password", re.IGNORECASE))
        self.send_command(password)
        output = self.read_until(re.compile(r"Welcome|Reconnecting|Wrong password", re.IGNORECASE))
        if re.search(r"Reconnecting", output, re.IGNORECASE):
            return None  # already in-world, skip menu
        elif re.search(r"Welcome", output, re.IGNORECASE):
            self.send_command(Session.RETURN)  # enter for main menu
            self.send_command(1)               # enter the game
            return self.read_until_quiet()
        elif re.search(r"Wrong password", output, re.IGNORECASE):
            raise Session.LoginError("wrong password")

    # ----- internals -----

    def _start_reader(self):
        def run():
            try:
                while True:
                    chunk = self._socket.recv(4096)
                    if not chunk:
                        break
                    text = self._strip_iac(chunk)
                    if text:
                        with self._lock:
                            self._buffer += text
                            self._last_recv_at = time.monotonic()
                            self._cv.notify_all()
            except OSError:
                pass  # remote closed — fall through
            except Exception as e:
                print(f"[mud_manager.Session] reader error: {type(e).__name__}: {e}", file=sys.stderr)
            finally:
                with self._lock:
                    self._closed = True
                    self._cv.notify_all()

        self._reader = threading.Thread(target=run, daemon=True)
        self._reader.start()

    # Telnet IAC stripper — discards WILL/WONT/DO/DONT negotiation and SB..SE
    # subnegotiation blocks; keeps literal 0xFF via the IAC-IAC escape.
    def _strip_iac(self, data):
        out = bytearray()
        i, n = 0, len(data)
        while i < n:
            b = data[i]
            if b == Session.IAC:
                nxt = data[i + 1] if i + 1 < n else None
                if nxt is None:
                    break
                if nxt == Session.IAC:
                    out.append(0xFF)
                    i += 2
                elif nxt in (Session.WILL, Session.WONT, Session.DO, Session.DONT):
                    i += 3
                elif nxt == Session.SB:
                    j = i + 2
                    while j < n and not (data[j] == Session.IAC and j + 1 < n and data[j + 1] == Session.SE):
                        j += 1
                    i = j + 2
                else:
                    i += 2
            else:
                out.append(b)
                i += 1
        # Ruby force_encodes without validating; Python needs an explicit
        # error mode to avoid crashing on a stray non-UTF-8 byte from the
        # MUD (color codes, latin-1 leftovers) — "replace" is the closest
        # practical equivalent to Ruby's "accept whatever bytes arrive."
        return bytes(out).decode("utf-8", errors="replace")
```

Notes:
- **`Session.Error`/`ConnectionError`/`LoginError`/`Timeout` nested inside
  the class**, not module-level — Python supports nested classes, so this
  preserves Ruby's `Session::Error` / `Session::ConnectionError` etc.
  namespacing exactly (`mud.py` will catch `mud_manager.Session.Error`).
  `Timeout` is deliberately **not** named `TimeoutError` to avoid shadowing
  the Python builtin of that name at the module/class level in a confusing
  way — `Session.Timeout` is unambiguous and mirrors Ruby's own name.
- **`_strip_iac`'s SB-skip loop bounds-checks `data[j + 1]`** before comparing
  it to `SE`, unlike the Ruby version's bare `bs[j + 1]` — Ruby arrays return
  `nil` for an out-of-range index (safe to compare), Python `bytes` raises
  `IndexError` instead, so the Python translation needs the explicit
  `j + 1 < n` guard to stay safe at the end of a chunk.
- **`quiet_seconds`/`timeout` defaults and the whole wait-loop structure are
  line-for-line the same shape as Ruby** — same deadline math, same
  "recompute `wait_for` each iteration, `min` against remaining total" logic,
  same lock-held-for-the-whole-loop pattern (`with self._lock:` wrapping the
  `while True`, mirroring `@buffer_mu.synchronize do ... end`).
- `Session.login`'s return value matters: `None` for the "Reconnecting"
  branch, the drained welcome text for the "Welcome"/fresh-login branch —
  `mud.py`'s `mud_connect` tool interpolates it into its response message,
  so the three-way branch's return values are preserved exactly, not
  collapsed to `None`/truthy.

### `week0_explore/mud_manager/python/mud_manager/primitives.py` (new)

Direct translation of `MudManager::Primitives`. Ruby's `module_function`
(every method callable as `Primitives.foo(...)`) is just... a Python module
with plain top-level functions — the direct equivalent, no wrapper needed.
`Struct.new(..., keyword_init: true)` → a `@dataclass`, matching the
precedent already set by `tool.py`'s `Tool` dataclass in this codebase.

```python
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
    # Ruby's keyword is `from:` — a reserved word in Python, so the parameter
    # is `from_`, but the Command's args dict keeps the literal key "from"
    # to preserve exact field naming for anything inspecting `.args`.
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
```

Notes:
- **`Command` is a `@dataclass`, not a Ruby `Struct`** — same precedent as
  `Tool` in `tool.py`; `__str__` returns `self.raw`, matching `to_s = raw`.
- **`_check_enum`/`_require_str` raise `ValueError`**, the direct Python
  equivalent of Ruby's `ArgumentError` (both are the "caller passed a bad
  argument" exception in their respective languages) — `mud.py` catches
  `ValueError` everywhere Ruby's `mud.rb` catches `ArgumentError`.
- **`transfer_liquid`'s `from` parameter is renamed `from_`** because `from`
  is a Python reserved word; the `Command.args` dict still uses the literal
  key `"from"` via `**{"from": from_, "to": to}` so anything reading
  `.args["from"]` sees the same shape as Ruby's `args[:from]`.
- Only `move`, `attack`, `skill_strike`, `say_local`, `say_targeted`,
  `say_channel`, `get`, `drop`, `put`, `equip`, `consume`, `set_position`,
  `track`, `flee`, `info_self`, `look`, `examine`, `consider`, `cast`,
  `use_magic_item`, `shop`, `practice`, `save_char` are actually called by
  `tools/mud.py`'s 27 registered tools (mirroring which primitives Ruby's
  `mud.rb` uses) — the rest (`give`, `steal`, `bank`, `mail`, `rent`,
  `house_admin`, social commands, etc.) exist in Ruby's `Primitives` today
  without a corresponding tool wrapper either; porting the full primitives
  module for parity while only wiring the same subset of tools Ruby wires
  matches upstream exactly.

### `week0_explore/mud_manager/python/mud_manager/__init__.py` (new)

```python
from .session import Session
from . import primitives

__all__ = ["Session", "primitives"]
```

Direct translation of `mud_manager.rb`'s two `require_relative` lines.

### `boukensha/tools/__init__.py` (new)

Empty — makes `tools` a regular package so `from .tools import file_system,
shell, mud` works from `__init__.py`. Ruby's `Tools` module has no body of
its own either (just a namespace for the three files).

### `boukensha/tools/file_system.py` (new)

```python
import glob as _glob
import os
import re


def register(registry, *, working_dir):
    root = os.path.abspath(working_dir)

    def resolve(path):
        path = str(path)
        joined = path if os.path.isabs(path) else os.path.join(root, path)
        absolute = os.path.normpath(joined)
        if absolute == root or absolute.startswith(root + os.sep):
            return absolute
        return f"error: path '{path}' escapes the working directory"

    def oops(msg):
        return f"error: {msg}"

    def pwd():
        return root

    def list_directory(path="."):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isdir(target):
            return oops(f"'{path}' is not a directory")
        entries = sorted(os.listdir(target))
        entries = [e + "/" if os.path.isdir(os.path.join(target, e)) else e for e in entries]
        return "\n".join(entries) if entries else "(empty)"

    def read_file(path):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isfile(target):
            return oops(f"'{path}' is not a file")
        try:
            with open(target, "r") as f:
                return f.read()
        except OSError as e:
            return oops(str(e))

    def write_file(path, content):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w") as f:
                f.write(content)
            rel = os.path.relpath(target, root)
            return f"ok: wrote {len(content.encode('utf-8'))} bytes to {rel}"
        except OSError as e:
            return oops(str(e))

    def delete_file(path):
        target = resolve(path)
        if target.startswith("error:"):
            return target
        if not os.path.isfile(target):
            return oops(f"'{path}' is not a file")
        try:
            os.remove(target)
            return f"ok: deleted {path}"
        except OSError as e:
            return oops(str(e))

    def search_files(pattern, path=".", glob="*"):
        target = resolve(path)
        if target.startswith("error:"):
            return target

        search_is_file = os.path.isfile(target)
        file_glob = target if search_is_file else os.path.join(target, "**", glob)

        try:
            regex = re.compile(pattern)
        except re.error as e:
            return oops(f"invalid pattern: {e}")

        matches = []
        for file in sorted(_glob.glob(file_glob, recursive=True)):
            if not os.path.isfile(file):
                continue
            rel = os.path.relpath(file, root)
            try:
                with open(file, "r", errors="replace") as f:
                    for lineno, line in enumerate(f, start=1):
                        if regex.search(line):
                            matches.append(f"{rel}:{lineno}:{line.rstrip(chr(10))}")
            except OSError as e:
                matches.append(f"{rel}: error reading file: {e}")

        return "\n".join(matches) if matches else "no matches"

    registry.tool(
        "pwd",
        "Return the working directory — the root that all file paths are relative to.",
        {},
        pwd,
    )
    registry.tool(
        "list_directory",
        "List files and subdirectories at a path relative to the working directory. "
        "Defaults to the working directory itself.",
        {"path": {"type": "string", "description": "Relative path to list (default '.')"}},
        list_directory,
    )
    registry.tool(
        "read_file",
        "Read and return the full contents of a file. Path is relative to the working directory.",
        {"path": {"type": "string", "description": "Relative path to the file"}},
        read_file,
    )
    registry.tool(
        "write_file",
        "Write content to a file, creating it (and any missing parent directories) if needed, "
        "overwriting if it exists. Path is relative to the working directory.",
        {
            "path": {"type": "string", "description": "Relative path to the file"},
            "content": {"type": "string", "description": "Text content to write"},
        },
        write_file,
    )
    registry.tool(
        "delete_file",
        "Delete a file. Directories are not deleted. Path is relative to the working directory.",
        {"path": {"type": "string", "description": "Relative path to the file to delete"}},
        delete_file,
    )
    registry.tool(
        "search_files",
        "Search for a text pattern (literal string or Python regex) across all files in the "
        "working directory tree. Returns matching lines in 'path:line_number:content' format.",
        {
            "pattern": {"type": "string", "description": "The text or regex pattern to search for"},
            "path": {"type": "string", "description": "Subdirectory or file to search within (default '.' = entire working directory)"},
            "glob": {"type": "string", "description": "File glob to restrict which files are searched, e.g. '*.py' (default '*')"},
        },
        search_files,
    )
```

Notes:
- **`resolve` uses `os.path.normpath(os.path.join(root, path))`, not
  `Path(...).resolve()`** — Ruby's `File.expand_path(path, root)` is purely
  lexical (collapses `.`/`..`, makes absolute) and does **not** resolve
  symlinks; `pathlib.Path.resolve()` *does* resolve symlinks, which would be
  a behavior change (a symlink inside the working dir pointing outside it
  would newly be allowed through). `os.path.normpath`/`os.path.isabs` is the
  faithful lexical-only equivalent.
- **`glob` is both the tool's parameter name (matching the Ruby `glob:`
  kwarg and the tool schema key) and a stdlib module name** — imported as
  `import glob as _glob` specifically so the parameter can keep the name
  `glob` without shadowing the module inside `search_files`.
- `registry.tool(name, description, parameters, block)` — positional,
  matching `registry.py`'s existing signature (`def tool(self, name,
  description, parameters=None, block=None)`), same call shape already used
  by `examples/example.py`'s existing `dsl.tool(...)` calls.

### `boukensha/tools/shell.py` (new)

```python
import os
import subprocess


def register(registry, *, working_dir, timeout=30, allowed_commands=None):
    root = os.path.abspath(working_dir)

    def oops(msg):
        return f"error: {msg}"

    allowed_note = f" Allowed executables: {', '.join(allowed_commands)}." if allowed_commands else ""

    def run_command(command):
        if allowed_commands is not None:
            tokens = str(command).strip().split()
            executable = tokens[0] if tokens else ""
            if executable not in [str(c) for c in allowed_commands]:
                return oops(f"'{executable}' is not in the allowed-commands list ({', '.join(allowed_commands)})")

        try:
            result = subprocess.run(
                command, shell=True, cwd=root,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return oops(f"command timed out after {timeout}s: {command}")
        except OSError as e:
            return oops(f"command not found: {e}")

        output = result.stdout.decode("utf-8", errors="replace").strip()
        exit_note = "" if result.returncode == 0 else f"\n[exit {result.returncode}]"
        return f"(no output){exit_note}" if not output else f"{output}{exit_note}"

    registry.tool(
        "run_command",
        "Run a shell command inside the working directory and return its combined stdout+stderr "
        f"output. Commands run with a {timeout}-second timeout.{allowed_note}",
        {"command": {"type": "string", "description": "The shell command to execute (e.g. 'python3 script.py', 'ls -la', 'git status')"}},
        run_command,
    )
```

Notes:
- **`subprocess.run(command, shell=True, ...)` is the direct equivalent of
  Ruby's `Open3.capture2e(command, chdir: root)`** — both run the given
  string through a shell (`/bin/sh -c`), not `exec` it directly, which is
  what lets `command` contain pipes/redirects like a real shell command.
  This is an intentional, documented design in the Ruby source (a tool
  that runs arbitrary shell commands, mitigated only by the
  `allowed_commands` allow-list) — the Python translation carries the same
  design and the same mitigation, not a new vulnerability.
- **The `except OSError` branch (Ruby's `Errno::ENOENT`) is effectively
  unreachable in practice** in both languages once a shell is involved: the
  shell itself is what's spawned, and it always exists, so a genuinely
  missing executable surfaces as text in the captured output (`"sh: cmd:
  command not found"`), not as a raised exception. Kept for the same
  defensive-but-rarely-hit reason Ruby keeps its `rescue Errno::ENOENT`.
- `timeout`/`allowed_commands` are captured in the `run_command` closure at
  `register()` time, matching Ruby's block-closure capture of the same
  local variables.

### `boukensha/tools/mud.py` (new)

```python
import socket
import sys
from pathlib import Path

# mud_manager isn't a pip-installed package — it's a sibling local library
# at week0_explore/mud_manager/python/, mirroring how the Ruby gem lives at
# week0_explore/mud_manager/ and is pulled in via a Gemfile path dependency.
_MUD_MANAGER_DIR = Path(__file__).resolve().parents[5] / "week0_explore" / "mud_manager" / "python"
if str(_MUD_MANAGER_DIR) not in sys.path:
    sys.path.insert(0, str(_MUD_MANAGER_DIR))

from mud_manager.session import Session
from mud_manager import primitives as p


def register(registry, *, host="localhost", port=4000, name, password):
    session = Session(host=host, port=port)

    def send_cmd(command):
        session.drain()
        session.send_command(command)
        return session.read_until_prompt()

    def guard():
        if not session.is_open():
            return "error: not connected — call mud_connect first"
        return None

    # ── Connection ──────────────────────────────────────────────────────

    def mud_connect():
        if session.is_open():
            return f"already connected to {session.host}:{session.port}"
        try:
            session.open()
            welcome = session.login(name, password) or ""
            return f"connected to {session.host}:{session.port}\n{welcome}"
        except Session.Error as e:
            return f"error: {e}"

    def mud_disconnect():
        if session.is_open():
            session.close()
            return "disconnected"
        return "already disconnected"

    def mud_status():
        return f"connected to {session.host}:{session.port}" if session.is_open() else "disconnected"

    # ── Perception ──────────────────────────────────────────────────────

    def look(target=None, preposition=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.look(target=target, preposition=preposition))
        except ValueError as e:
            return f"error: {e}"

    def examine(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.examine(target))
        except ValueError as e:
            return f"error: {e}"

    def check(kind):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.info_self(kind))
        except ValueError as e:
            return f"error: {e}"

    # ── Movement ────────────────────────────────────────────────────────

    def move(direction):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.move(direction))
        except ValueError as e:
            return f"error: {e}"

    def flee():
        err = guard()
        if err:
            return err
        return send_cmd(p.flee())

    def set_position(position):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.set_position(position))
        except ValueError as e:
            return f"error: {e}"

    def track(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.track(target))
        except ValueError as e:
            return f"error: {e}"

    # ── Combat ──────────────────────────────────────────────────────────

    def attack(target, style="kill"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.attack(style, target))
        except ValueError as e:
            return f"error: {e}"

    def skill_strike(skill, target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.skill_strike(skill, target))
        except ValueError as e:
            return f"error: {e}"

    def consider(target):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.consider(target))
        except ValueError as e:
            return f"error: {e}"

    # ── Communication ───────────────────────────────────────────────────

    def say(text, mode="say"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_local(mode, text))
        except ValueError as e:
            return f"error: {e}"

    def tell(target, text, mode="tell"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_targeted(mode, target, text))
        except ValueError as e:
            return f"error: {e}"

    def channel_say(channel, text):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.say_channel(channel, text))
        except ValueError as e:
            return f"error: {e}"

    # ── Inventory & equipment ────────────────────────────────────────────

    def get_item(item, container=None, count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.get(item, container=container, count=count))
        except ValueError as e:
            return f"error: {e}"

    def drop_item(item, mode="drop", count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.drop(mode, item, count=count))
        except ValueError as e:
            return f"error: {e}"

    def put_item(item, container, count=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.put(item, container, count=count))
        except ValueError as e:
            return f"error: {e}"

    def equip_item(item, action, body_loc=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.equip(action, item, body_loc=body_loc))
        except ValueError as e:
            return f"error: {e}"

    def consume_item(item, mode="eat"):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.consume(mode, item))
        except ValueError as e:
            return f"error: {e}"

    # ── Magic ────────────────────────────────────────────────────────────

    def cast_spell(spell, target=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.cast(spell, target=target))
        except ValueError as e:
            return f"error: {e}"

    def use_magic_item(item, mode, target_args=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.use_magic_item(mode, item, target_args=target_args))
        except ValueError as e:
            return f"error: {e}"

    # ── Utility ──────────────────────────────────────────────────────────

    def shop(action, args=None):
        err = guard()
        if err:
            return err
        try:
            return send_cmd(p.shop(action, args=args))
        except ValueError as e:
            return f"error: {e}"

    def practice(skill=None):
        err = guard()
        if err:
            return err
        return send_cmd(p.practice(skill))

    def save_character():
        err = guard()
        if err:
            return err
        return send_cmd(p.save_char())

    def send_raw(command):
        err = guard()
        if err:
            return err
        session.send_command(command)
        return session.read_until_quiet()

    # ── Registration ───────────────────────────────────────────────────

    registry.tool("mud_connect",
        "Open the connection to the MUD server and log in with the configured character name "
        "and password. Safe to call when already connected (returns current status instead of "
        "reconnecting).",
        {}, mud_connect)
    registry.tool("mud_disconnect",
        "Close the connection to the MUD server gracefully.",
        {}, mud_disconnect)
    registry.tool("mud_status",
        "Return whether the MUD session is currently connected.",
        {}, mud_status)

    registry.tool("look",
        "Look at the current room or at a specific target. Call with NO arguments to describe "
        "the current room (do NOT pass target: 'room'). Pass a target to inspect a specific "
        "item, mob, or player (e.g. target: 'sword'). Use preposition 'in' to look inside a "
        "container, 'at' to inspect something, or a direction (north/east/south/west/up/down) "
        "to peek into an adjacent room.",
        {
            "target": {"type": "string", "description": "Item, mob, or player name to inspect. Omit entirely to describe the current room."},
            "preposition": {"type": "string", "description": "Preposition: in, at, north, east, south, west, up, down (optional)"},
        }, look)
    registry.tool("examine",
        "Examine a target in detail (more verbose than look).",
        {"target": {"type": "string", "description": "The item, mob, or player to examine"}}, examine)
    registry.tool("check",
        "Query information about your character or surroundings. Kinds: score, inventory, "
        "equipment, gold, exits, time, weather, levels, wimpy, toggle, where.",
        {"kind": {"type": "string", "description": "What to check: score | inventory | equipment | gold | exits | time | weather | levels | wimpy | toggle | where"}}, check)

    registry.tool("move",
        "Move in a compass direction or up/down.",
        {"direction": {"type": "string", "description": "Direction: north | east | south | west | up | down"}}, move)
    registry.tool("flee",
        "Attempt to flee from combat in a random available direction.",
        {}, flee)
    registry.tool("set_position",
        "Change body position. Use 'rest' or 'sleep' between fights to recover HP and mana. "
        "Must be standing to move or fight.",
        {"position": {"type": "string", "description": "Position: stand | sit | rest | sleep | wake"}}, set_position)
    registry.tool("track",
        "Attempt to track a mob or player by name, revealing which direction they are in. "
        "Requires the Track skill.",
        {"target": {"type": "string", "description": "Name of the mob or player to track"}}, track)

    registry.tool("attack",
        "Attack a target. Style 'kill' is the standard approach; 'murder' bypasses the mercy "
        "check; 'hit' is a one-off strike.",
        {
            "target": {"type": "string", "description": "Name of the mob or player to attack"},
            "style": {"type": "string", "description": "Attack style: kill | hit | murder (default: kill)"},
        }, attack)
    registry.tool("skill_strike",
        "Use a combat skill against a target.",
        {
            "skill": {"type": "string", "description": "Skill: bash | kick | backstab | rescue | assist"},
            "target": {"type": "string", "description": "Name of the mob or player"},
        }, skill_strike)
    registry.tool("consider",
        "Assess a mob's relative strength before engaging in combat. Returns a phrase such as "
        "'You could kill it easily' or 'Death awaits you'. Always consider before attacking an "
        "unknown mob.",
        {"target": {"type": "string", "description": "Name of the mob to consider"}}, consider)

    registry.tool("say",
        "Speak or emote in the current room.",
        {
            "text": {"type": "string", "description": "What to say or emote"},
            "mode": {"type": "string", "description": "Mode: say | emote | reply (default: say)"},
        }, say)
    registry.tool("tell",
        "Send a private message to a specific player.",
        {
            "target": {"type": "string", "description": "Player name to message"},
            "text": {"type": "string", "description": "The message"},
            "mode": {"type": "string", "description": "Mode: tell | whisper | ask (default: tell)"},
        }, tell)
    registry.tool("channel_say",
        "Broadcast a message over a global channel.",
        {
            "channel": {"type": "string", "description": "Channel: shout | gossip | auction | grats | holler"},
            "text": {"type": "string", "description": "The message to broadcast"},
        }, channel_say)

    registry.tool("get_item",
        "Pick up an item from the room or from a container.",
        {
            "item": {"type": "string", "description": "Name of the item to get"},
            "container": {"type": "string", "description": "Container to get it from (optional)"},
            "count": {"type": "integer", "description": "Number of items to get (optional)"},
        }, get_item)
    registry.tool("drop_item",
        "Drop, donate, or junk an item.",
        {
            "item": {"type": "string", "description": "Name of the item"},
            "mode": {"type": "string", "description": "Mode: drop | donate | junk (default: drop)"},
            "count": {"type": "integer", "description": "Number of items (optional)"},
        }, drop_item)
    registry.tool("put_item",
        "Put an item into a container.",
        {
            "item": {"type": "string", "description": "Name of the item to put"},
            "container": {"type": "string", "description": "Name of the container"},
            "count": {"type": "integer", "description": "Number of items (optional)"},
        }, put_item)
    registry.tool("equip_item",
        "Wear, wield, hold, grab, or remove an item.",
        {
            "item": {"type": "string", "description": "Name of the item"},
            "action": {"type": "string", "description": "Action: wear | wield | hold | grab | remove"},
            "body_loc": {"type": "string", "description": "Body location to wear on (optional, e.g. 'head', 'finger')"},
        }, equip_item)
    registry.tool("consume_item",
        "Eat, drink, taste, or sip a consumable item.",
        {
            "item": {"type": "string", "description": "Name of the item to consume"},
            "mode": {"type": "string", "description": "Mode: eat | drink | taste | sip (default: eat)"},
        }, consume_item)

    registry.tool("cast_spell",
        "Cast a spell, optionally at a target.",
        {
            "spell": {"type": "string", "description": "Full spell name (e.g. 'cure light wounds', 'magic missile')"},
            "target": {"type": "string", "description": "Target mob, player, or object (optional)"},
        }, cast_spell)
    registry.tool("use_magic_item",
        "Activate a magic item: quaff a potion, recite a scroll, or use a wand/staff.",
        {
            "item": {"type": "string", "description": "Name of the item to activate"},
            "mode": {"type": "string", "description": "Mode: quaff | recite | use"},
            "target_args": {"type": "string", "description": "Optional target arguments (e.g. mob name for a wand)"},
        }, use_magic_item)

    registry.tool("shop",
        "Interact with a shop NPC: list stock, buy, sell, or get the value of an item.",
        {
            "action": {"type": "string", "description": "Action: list | buy | sell | value | offer"},
            "args": {"type": "string", "description": "Item name or number (optional)"},
        }, shop)
    registry.tool("practice",
        "List your known skills at a guildmaster, or practice a specific skill.",
        {"skill": {"type": "string", "description": "Skill name to practice (omit to list all)"}}, practice)
    registry.tool("save_character",
        "Save your character to disk so progress is not lost on disconnect.",
        {}, save_character)
    registry.tool("send_raw",
        "Send an arbitrary command string to the MUD and return the response. Use this as an "
        "escape hatch when no structured tool fits.",
        {"command": {"type": "string", "description": "The raw command to send (e.g. 'who', 'help backstab')"}}, send_raw)

    # Auto-connect at startup so the session is ready immediately and the
    # agent doesn't need to waste a turn calling mud_connect first.
    try:
        session.open()
        session.login(name, password)
    except Session.Error as e:
        print(f"[boukensha] MUD auto-connect failed: {e} — call mud_connect manually", file=sys.stderr)
```

Notes:
- **`_MUD_MANAGER_DIR = Path(__file__).resolve().parents[5] / ...`** —
  verified by walking `.parents` from
  `boukensha/tools/mud.py`: `[0]=tools`, `[1]=boukensha`,
  `[2]=10_standard_tool_library`, `[3]=python`, `[4]=week1_baseline`,
  `[5]=` the repo root — so `parents[5] / "week0_explore" / "mud_manager"
  / "python"` is `week0_explore/mud_manager/python`, the new package
  directory. Mirrors Ruby's Gemfile `path: "../../../week0_explore/mud_manager"`
  (relative from `ruby/10_standard_tool_library/Gemfile`, also resolving to
  the repo-root-anchored `week0_explore/mud_manager`).
- **The `sys.path` insert lives inside `mud.py` itself**, not in every
  caller (`example.py`, the launcher) — this centralizes the "where does
  `mud_manager` come from" resolution in one place, the same way Bundler's
  `Gemfile` centralizes it once for every Ruby consumer instead of each
  script doing its own path math.
- **Every guarded tool follows the same two-line shape**: `err = guard();
  if err: return err`, then a `try/except ValueError` around the
  `primitives` call + `send_cmd`. This is the direct Python idiom for
  Ruby's `next guard.call if guard.call` early-return-from-block pattern —
  Python doesn't have `next`-with-a-value inside a plain function, so an
  early `return` is the natural equivalent, not a workaround.
- **`attack`'s Python parameter order is `(target, style="kill")`**, matching
  the tool's declared parameter order in Ruby (`target:, style: "kill"`),
  even though the underlying `primitives.attack(style, target)` call takes
  them the other way around — same mismatch exists in the Ruby source
  itself (`p.attack(style, target)` inside a block declared `|target:,
  style: "kill"|`), preserved faithfully rather than "fixed."
- `flee`, `practice`, `save_character`, `send_raw` don't wrap their
  `primitives`/`session` call in `try/except ValueError` — matches Ruby
  exactly (`flee`, `practice`, `save_char` take no enum/required-string
  arguments so can't raise `ArgumentError`; `send_raw` bypasses
  `primitives` entirely).

### `boukensha/context.py` — add `working_dir`

```python
import os

from .message import Message


class Context:
    def __init__(self, task, system=None, working_dir=None):
        self.task = task
        self.system = system
        self.working_dir = os.path.abspath(working_dir) if working_dir else None
        self.messages = []
        self.tools = {}
    # ... register_tool / add_message / clear_messages / tool_count / turn_count / __str__ unchanged
```

Matches `attr_reader :working_dir` + `@working_dir = working_dir ?
File.expand_path(working_dir) : nil`.

### `boukensha/version.py` — bump

```python
VERSION = "0.10.0"
```

Python has no `09_global_executable` step, so there's no Python `"0.9.0"`
to have passed through — the version jumps straight from `"0.8.0"` (08's
value, still sitting in the copied tree) to `"0.10.0"`, matching the
Python step-folder number (`10_standard_tool_library`), consistent with how
every prior step's `version.py` has tracked its own Python step number
rather than mirroring every intermediate Ruby release.

### `boukensha/repl.py` — `mud=` param and banner status line

```python
import socket
...

class Repl:
    ...
    def __init__(self, *, context, registry, builder, client, logger,
                 config_dir=None, provider=None, model=None, version=None,
                 api_key=None, mud=None, task_settings=None, max_iterations=None,
                 max_output_tokens=None):
        ...
        self.mud = mud
        self.turn = 0

    def _banner(self):
        key_status = "✗ API key not set" if not (self.api_key and self.api_key.strip()) else "✓ API key set"
        provider_line = f"{self.provider or 'default'} ({self.model or 'default'})  {key_status}"
        config_exists = bool(self.config_dir) and Path(self.config_dir).is_dir()
        config_line = self.config_dir if config_exists else f"{self.config_dir or '(default)'}  ✗ directory not found"
        ver = self.version or "?.?.?"
        mud_stat = self._mud_status_string()

        return f"""
╔══════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v{ver}){" " * (9 - len(ver))}║
╚══════════════════════════════════════╝
  config:    {config_line}
  provider:  {provider_line}
  mud:       {mud_stat}

  /quiet or /loud   toggle logging
  /clear           reset conversation history
  /exit or /quit    leave the REPL
"""

    def _mud_status_string(self):
        if not self.mud:
            return "(not configured)"
        host = self.mud.get("host", "localhost")
        port = self.mud.get("port", 4000)
        name = self.mud.get("name")
        return f"{host}:{port}  {self._probe_mud(host, port, name)}"

    # TCP reachability only — the tool session auto-connects at startup
    # (in tools/mud.py's register()), so probing login here would cause a
    # double-login.
    def _probe_mud(self, host, port, name):
        try:
            socket.create_connection((host, port), timeout=3).close()
        except OSError:
            return "✗ not reachable"
        except Exception as e:
            return f"✗ probe error: {e}"
        return "(Reachable)" if name and str(name).strip() else "(Reachable, no credentials)"
```

`_run_turn` is unchanged. `mud` is stored as a plain dict (the same shape
`_mud_opts_from_config`/the caller's explicit `mud=` argument produces in
`__init__.py`), read with `.get(...)` rather than Ruby's `@mud[:host]`
hash-with-symbol-keys access.

### `boukensha/__init__.py` — tool auto-registration

```python
import os

from .tools import file_system, shell, mud as mud_tools


def _mud_opts_from_config(cfg):
    if not (cfg.mud_host and cfg.mud_username):
        return None
    return {
        "host": cfg.mud_host,
        "port": cfg.mud_port,
        "name": cfg.mud_username,
        "password": cfg.mud_password,
    }


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
    working_dir=None,
    allowed_commands=None,
    shell_timeout=30,
    mud=None,
    configure=None,
):
    cfg = config()  # loads .env; populates os.environ
    # ... system/model/backend/api_key defaulting unchanged ...

    resolved_working_dir = (
        None if working_dir is False
        else (working_dir if working_dir is not None else os.getcwd())
    )

    ctx = Context(task=task_class, system=system, working_dir=resolved_working_dir)
    registry = Registry(ctx)

    if resolved_working_dir:
        file_system.register(registry, working_dir=resolved_working_dir)
        shell.register(registry, working_dir=resolved_working_dir,
                        timeout=shell_timeout, allowed_commands=allowed_commands)

    resolved_mud = None if mud is False else (mud or _mud_opts_from_config(cfg))
    if resolved_mud:
        mud_tools.register(registry, **resolved_mud)

    if configure is not None:
        configure(RunDSL(registry))

    # ... backend construction, PromptBuilder/Client, Logger, Agent.run() unchanged ...
```

`repl()` gets the identical `working_dir`/`allowed_commands`/`shell_timeout`/
`mud` params and the identical `resolved_working_dir`/`resolved_mud` block,
plus passes `mud=resolved_mud` into the `Repl(...)` constructor call
alongside the existing `config_dir=`/`provider=`/etc. kwargs.

Notes:
- **`working_dir=None` in the signature, resolved to `os.getcwd()` inside
  the function body — not `working_dir=os.getcwd()` as the default
  value.** This is a deliberate, important divergence in *form* to
  preserve identical *behavior*: Ruby's `working_dir: Dir.pwd` default
  expression is re-evaluated on every call (Ruby evaluates keyword
  defaults per-invocation), so each `Boukensha.run(...)` call with no
  explicit `working_dir:` gets the caller's *current* working directory at
  call time. A Python default of `working_dir=os.getcwd()` would instead
  freeze the value once, at function-definition time (i.e., at module
  import), which is wrong if the process's cwd ever changes between import
  and call. Resolving it inside the body reproduces Ruby's actual
  per-call-fresh behavior.
- **`working_dir=False` (matching Ruby's `working_dir: false`) opts out of
  file/shell tools entirely** — `example.py`'s new MUD demo uses exactly
  this (`working_dir=False`, since it needs no filesystem tools).
- **`mud` truthiness**: Python's `mud or _mud_opts_from_config(cfg)`
  mirrors Ruby's `mud || mud_opts_from_config(cfg)` for the common cases
  (`None`/`nil` → fall back to config; a real dict/Hash → use it). One
  minor edge case differs and is not worth special-casing: an *explicitly
  passed empty dict* (`mud={}`) is falsy in Python (falls back to config)
  but truthy in Ruby (`{}` is truthy there, so it would be used as-is and
  immediately fail inside `Tools::Mud.register` for missing the required
  `name:` keyword) — passing an empty MUD options dict on purpose isn't a
  real use case either language's README documents or this course
  exercises.
- `mud is False` is checked with `is`, not `==`, to avoid Python's
  `0 == False` / falsy-dict-equals-False surprises — matches the intent of
  Ruby's `mud == false` (which in Ruby is also a strict identity-shaped
  check, since `false` is a singleton).

## `README.md`

Rewrite following the established 00–08 structure (title/link → Environment
setup → New/Updated files tables → design explanation → run example →
Considerations → Files table), covering:

- Title `# 10 · A Standard Tool Library (Python)`, link to
  `../../ruby/10_standard_tool_library/README.md`.
- **New files:** `boukensha/tools/{file_system,shell,mud}.py`, plus (called
  out separately since it lives outside this step's directory)
  `week0_explore/mud_manager/python/mud_manager/{__init__,session,primitives}.py`.
- **`FileSystem` tools table** and **`Shell` tools table**, same content as
  Ruby's README tables (`pwd`, `list_directory`, `read_file`, `write_file`,
  `delete_file`, `search_files` / `run_command`), translated to Python
  signatures.
- **New `boukensha.run`/`boukensha.repl` keyword arguments** section:
  `working_dir`, `allowed_commands`, `shell_timeout`, `mud`, with the same
  "nil/None permits everything, pass an explicit list to lock it down"
  framing Ruby's README uses.
- **Direct registration** section showing
  `file_system.register(registry, working_dir="/my/project")` /
  `shell.register(registry, working_dir=..., timeout=..., allowed_commands=...)`
  for finer-grained manual control.
- **A `Mud` tools table** — note that Ruby's own README omits this table
  (it only documents `FileSystem`/`Shell` despite `mud.rb` being the
  largest addition); the Python README should **not** copy that omission,
  and should include the full 27-tool table since it's genuinely new,
  working functionality here.
- **Technical Considerations**, adapted from Ruby's own (which notes the
  `mud_manager` gem had to be hardcoded into the Gemfile, and includes
  token-cost observations about Sonnet vs. Haiku for status checks) plus a
  Python-specific one: `mud_manager` has no PyPI package, so
  `boukensha/tools/mud.py` resolves it via a `sys.path` insert pointing at
  the sibling `week0_explore/mud_manager/python/` directory rather than a
  package-manager dependency.
- Run example: `./week1_baseline/bin/python/10_standard_tool_library`.
- Files table: add the four new files under `boukensha/tools/`.

Ruby's README also references `ruby examples/demo.rb`, but the actual file
in every version of this step (08 through 10) is `examples/example.rb` —
another one-off naming slip in the upstream README, same class of issue
flagged in the `07`/`08` plans. The Python README should reference the real
file, `examples/example.py`.

## `examples/example.py`

Full rewrite, following Ruby's new `example.rb` structure:

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

cfg = boukensha.config()
print(f"Config: {cfg}")
print(f"API key set? {os.environ.get('ANTHROPIC_API_KEY') is not None}")
print()

# mud: comes from config (.boukensha/settings.yaml's `mud:` block) automatically.
boukensha.run(
    task="Connect to the MUD, look at your surroundings, check your score, "
         "then look at the available exits and tell me what you see.",
    working_dir=False,  # no filesystem tools needed for MUD play
)
```

Notes:
- Switches from step 08's `boukensha.repl(configure=...)` file-reading demo
  to a one-shot `boukensha.run(task=..., working_dir=False)` MUD demo —
  matches Ruby's rewritten `example.rb` exactly (drops the `read_file`/
  `list_directory` manual tool registrations entirely, since `working_dir`
  now auto-registers the standard library instead, and this particular demo
  doesn't need filesystem tools at all).
- No explicit `mud=` kwarg — relies on `_mud_opts_from_config` picking up
  the repo's own `.boukensha/settings.yaml`, which already has a `mud:`
  block (`host: localhost`, `port: 4000`, `username: dummy`, `password:
  helloworld`) pointing at the local CircleMUD test server used elsewhere
  in this repo's exploration work.

## `bin/python/10_standard_tool_library` (new file)

```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$HOME/code/virtualenv/claude/bin/activate"
cd "$(dirname "$0")/../../python/10_standard_tool_library"
python3 examples/example.py
```

Needs `chmod +x`. Same shape as `bin/python/08_the_repl_loop` — no
`BOUKENSHA_DIR` export needed since `examples/example.py` sets it itself via
`os.environ.setdefault(...)`.

## Expected output / how to verify parity

1. Start (or confirm running) the local CircleMUD test server the repo's
   `.boukensha/settings.yaml` `mud:` block points at (`localhost:4000`,
   `dummy`/`helloworld`) — the same server other exploration work in
   `week0_explore/` already targets.
2. Run both `bundle exec ruby examples/example.rb` (under
   `ruby/10_standard_tool_library`) and `python3 examples/example.py`
   (under `python/10_standard_tool_library`, or the new
   `bin/python/10_standard_tool_library` launcher) and confirm both connect,
   log in, and produce a room description + score + exits in the final
   response.
3. Confirm the auto-connect warning path: point `mud.host`/`port` at
   something unreachable (e.g. port 1) and confirm both languages print
   `MUD auto-connect failed: ...` to stderr and still start up (the agent
   simply doesn't have a working MUD session until `mud_connect` succeeds).
4. Exercise `FileSystem`/`Shell` directly (they're easier to test than the
   live MUD): call `boukensha.run(task="...", working_dir="...")` with a
   task like "list the files in the working directory, read one, then
   append a line to it," and confirm `pwd`/`list_directory`/`read_file`/
   `write_file`/`search_files` all behave identically in both languages,
   including the path-traversal rejection (`../../etc/passwd` style paths
   should return the `error: path '...' escapes the working directory`
   string, not raise or actually read outside the sandbox).
5. Confirm `allowed_commands` actually blocks disallowed executables:
   `boukensha.run(task="run `curl google.com`", allowed_commands=["python3"])`
   should return the `'curl' is not in the allowed-commands list (python3)`
   error string from the tool, in both languages.
6. Confirm the REPL banner's new `mud:` line in both: shows
   `(not configured)` with no `mud:` settings, `✗ not reachable` when the
   host/port refuse a TCP connection, and `(Reachable)`/`(Reachable, no
   credentials)` when the port is open (with/without a configured
   username), without triggering a duplicate login (only one `mud_connect`
   worth of login traffic should hit the server per REPL start).
7. Confirm `client.py`/`config.py` are untouched: the 401-specific
   `ApiError` message and the 3-step `_resolve_dir` lookup both still work
   exactly as they did after `08_the_repl_loop` (this step should not have
   regressed either one).

## Carried-over known gaps (not fixed in this port, for parity)

Same items prior steps' READMEs leave alone, still true at this step:
- No persistent memory or context compaction across turns.
- Settings file must be exactly `.yaml`, not `.yml`.
- `quiet()`/`loud()`/`is_quiet()` are toggled but nothing reads
  `is_quiet()` to actually suppress output.
- `run_command`'s `allowed_commands` allow-list only checks the first
  whitespace-split token — it does not parse shell syntax, so
  `"python3 -c 'import os; os.system(\"curl ...\")'"` would pass the
  allow-list check and then do whatever it wants once the shell runs it.
  This is Ruby's own documented threat model for this tool (an allow-list
  of *first tokens*, not a sandboc), carried forward unchanged, not a new
  Python-side weakness.
- The `mud_manager` Python port's `Session` has no reconnect/retry logic
  beyond what `login()` does for the CircleMUD menu dance — matches Ruby.

## Decisions already made (from the 00–08 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml` — the
  new `mud_manager` Python package follows the same convention (a plain
  importable directory, no `setup.py`/`pyproject.toml` of its own).
- `bin/` split into per-language subdirectories; this step adds
  `bin/python/10_standard_tool_library`.
- Tests: parity with Ruby — `examples/example.py` as a manual/smoke test
  only, no pytest suite.
- Minimum Python version: 3.9+ (unchanged; nothing in this step needs
  newer syntax — `threading.Condition`, `dataclasses`, `re.Pattern` are all
  available since 3.7+).
- Output parity: exact field-for-field match where behavior is
  deterministic; MUD server responses and model tool-call sequences remain
  non-deterministic.
- One shared venv at the repo root; per-step manifests (unchanged —
  `requirements.txt` for this step is identical to 08's).
- Reuse of already-ported code: everything from `08_the_repl_loop` carries
  over unchanged except the additions listed above.
- README vs. actual implementation: follow the executable code, not
  aspirational/stale README prose (directly relevant again here — Ruby's
  own README both omits a `Mud` tools table and references a nonexistent
  `demo.rb` filename).

## New decisions specific to this step

- **`mud_manager` gets a full Python port** at
  `week0_explore/mud_manager/python/`, mirroring the Ruby gem's location
  rather than vendoring it inside `boukensha/` — confirmed as the intended
  scope before writing this plan, over the alternatives of stubbing
  `tools/mud.py` out or dropping MUD tooling from this step entirely.
- **Ruby's two regressions between 08 and 10 (the missing 401 check, the
  reverted 3-step `resolve_dir`) are explicitly not ported** — `client.py`
  and `config.py` need no changes this step, on the grounds that porting a
  bug Ruby introduced by accident in an unrelated step (09, which Python
  has no counterpart for) would make Python strictly worse for no reason.
- **`Session.RETURN`/`Session.ENTER` sentinel objects** replace Ruby's
  `:return`/`:enter` symbols — the direct unambiguous equivalent given
  Python has no symbol type.
- **`Session.Error`/`ConnectionError`/`LoginError`/`Timeout` nested inside
  the `Session` class** (not module-level), preserving Ruby's
  `Session::Error`-style namespacing exactly.
- **`file_system.py`'s path resolution uses lexical `os.path.normpath`, not
  `Path.resolve()`** — preserves Ruby's `File.expand_path`'s "no symlink
  resolution" semantics exactly, rather than silently becoming stricter/
  different by resolving symlinks.
- **`working_dir` and `mud` defaults are resolved inside the function body,
  not as Python default-argument expressions** — required to reproduce
  Ruby's per-call-fresh `Dir.pwd` evaluation instead of freezing a value at
  import time.

---

## Addendum — MCP-based tools (implemented after the initial port)

Everything above this line describes the initial port, which was
implemented and verified exactly as planned (registry-level tests plus a
live CircleMUD session). This addendum documents a **follow-up change,
also already implemented and verified**, made in response to an explicit
instructor requirement: "Verify the Standard Tool Library now uses
MCP-based tools while preserving the existing project architecture." No
Ruby counterpart exists for this change — it's Python-only, driven by the
instructor's ask rather than a Ruby diff.

### Scope decisions (confirmed before implementation)

Three open questions were resolved with the user before writing any code:

1. **Which tools move to MCP** — `file_system` and `shell` only. `mud`
   stays a native Python registration. Reason: `tools/mud.py` wraps a
   single long-lived, stateful `mud_manager.Session` (one login, one
   socket, shared across every tool call for the life of an agent run) —
   that doesn't map cleanly onto MCP's request/response tool-call model
   without a custom *stateful* MCP server or a larger redesign, and no
   published MCP server for a custom CircleMUD exists to point at instead.
   Converting it was considered and explicitly deferred, not overlooked.
2. **Custom servers vs. published ones** — write our own MCP servers in
   Python using the official SDK's `FastMCP`, rather than pointing at
   published reference servers (e.g. the official Node-based
   `@modelcontextprotocol/server-filesystem`). Keeps the whole stack
   Python/self-contained, consistent with this course's build-it-yourself
   philosophy, and is the only option for `shell` anyway (no generic
   published "run arbitrary shell command" MCP server exists, for obvious
   safety reasons).
3. **Language scope** — Python only. No equivalent change was made to the
   Ruby track.

### Why this is additive to the existing architecture, not a rewrite

The instructor's phrasing ("while preserving the existing project
architecture") maps directly onto one design constraint: **`Context`,
`Registry`, `Tool`, `Agent`, `PromptBuilder`, and every file under
`backends/` needed zero changes.** Confirmed after implementation via
`grep -rl "mcp" boukensha/*.py boukensha/backends/*.py boukensha/tasks/*.py
boukensha/tools/mud.py` — zero hits outside the new `mcp_client.py` itself.
The only files touched were `tools/file_system.py` and `tools/shell.py`
(rewritten internals, identical `register()` signatures), plus new files.

The trick that makes this possible: `backends/anthropic.py` (and the other
backends) already expect `Tool.parameters` in boukensha's own flat shape —
`{name: {"type": ..., "description": ...}}` — which they wrap into
`"properties"`/`"required"` themselves when building the API payload. MCP's
`tools/list` response instead returns a full JSON Schema object
(`inputSchema`, with its own `"properties"`/`"required"`/`"type"`). The
bridge layer (`register_mcp_tools()`) unpacks `inputSchema["properties"]`
back into the flat shape at registration time, so nothing downstream has
to know or care that a tool's implementation now lives in a separate
process talking JSON-RPC over stdio instead of a local Python closure:

```
Agent.run() → Registry.dispatch("read_file", {...})
            → Tool.block(**args)                       # unchanged call shape
            → McpClient.call_tool("read_file", {...})  # NEW: bridges to...
            → mcp_servers/file_system_server.py          # ...a separate process
```

### New files

| File | Purpose |
|---|---|
| `boukensha/mcp_client.py` | `McpClient` — synchronous bridge to an MCP server run as a stdio subprocess; `register_mcp_tools(registry, *, command, args, env)` — discovers a server's tools via `tools/list` and registers each into a `Registry` |
| `boukensha/mcp_servers/__init__.py` | Empty — makes `mcp_servers` a regular package |
| `boukensha/mcp_servers/file_system_server.py` | `FastMCP` server exposing `pwd`/`list_directory`/`read_file`/`write_file`/`delete_file`/`search_files` — identical logic to the tool-file version it replaced, sandboxed to `BOUKENSHA_MCP_FS_ROOT` (an env var, since the server is a subprocess with no other way to receive its root directory) |
| `boukensha/mcp_servers/shell_server.py` | `FastMCP` server exposing `run_command`, configured via `BOUKENSHA_MCP_SHELL_ROOT`/`_TIMEOUT`/`_ALLOWED` env vars |

### Rewritten files (signatures unchanged, internals replaced)

| File | Before | After |
|---|---|---|
| `boukensha/tools/file_system.py` | Local Python closures registered directly via `registry.tool(...)` | Spawns `mcp_servers/file_system_server.py` via `sys.executable`, bridges its tools in via `register_mcp_tools()` |
| `boukensha/tools/shell.py` | Local Python closure registered directly | Spawns `mcp_servers/shell_server.py`, bridges `run_command` in |

`register(registry, *, working_dir)` / `register(registry, *, working_dir,
timeout=30, allowed_commands=None)` — both signatures are byte-for-byte
unchanged from the pre-MCP version, and both now return the `McpClient`
handle for the spawned subprocess (previously returned `None` implicitly).
`boukensha/__init__.py`'s call sites (`file_system.register(...)`,
`shell.register(...)`) needed **no changes** as a result.

### `requirements.txt`

One new dependency: `mcp>=1.28.1` (the official MCP Python SDK). Already
present in the shared venv at the time this was implemented
(`importlib.metadata.version("mcp")` → `1.28.1`), so no install step was
needed beyond adding the line to `requirements.txt` for anyone setting up
the venv from scratch.

### `boukensha/mcp_client.py` — the sync/async bridge

The official MCP SDK is asyncio-based (`ClientSession`, `stdio_client`);
`boukensha`'s `Agent`/`Registry` loop is fully synchronous throughout.
`McpClient` runs the entire connect → serve → close lifetime as **one**
coroutine on a dedicated background thread's event loop, and exposes plain
blocking `list_tools()`/`call_tool()`/`close()` methods that hand work to
that loop via `asyncio.run_coroutine_threadsafe(...).result()` and block
for the answer — conceptually the same "own the concurrency internally,
expose a synchronous interface" shape as `mud_manager.Session`'s background
reader thread earlier in this port, just built on `asyncio` instead of raw
sockets and threading primitives.

```python
class McpClient:
    def __init__(self, *, command, args=None, env=None):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        self._session = None
        self._stop_event = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._connect_error = None

        params = StdioServerParameters(command=command, args=args or [], env=env)
        asyncio.run_coroutine_threadsafe(self._session_main(params), self._loop)
        if not self._ready.wait(timeout=15):
            raise TimeoutError(f"MCP server did not become ready in time: {command} {args}")
        if self._connect_error is not None:
            raise self._connect_error

        atexit.register(self.close)

    async def _session_main(self, params):
        self._stop_event = asyncio.Event()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as e:
            self._connect_error = e
            self._ready.set()
        finally:
            self._closed.set()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def list_tools(self):
        return self._run(self._session.list_tools()).tools

    def call_tool(self, name, arguments):
        result = self._run(self._session.call_tool(name, arguments))
        parts = [block.text for block in result.content if getattr(block, "text", None) is not None]
        text = "\n".join(parts)
        if result.isError:
            return f"error: {text}" if text else "error: tool call failed"
        return text

    def close(self):
        if self._closed.is_set():
            return
        if self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
            self._closed.wait(timeout=5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)
```

**Why the whole session has to live in one coroutine — a bug found by
testing, not anticipated in advance.** The first draft entered the
`stdio_client`/`ClientSession` async context managers in one
`run_coroutine_threadsafe` call (during `__init__`) and exited them in a
second, separate `run_coroutine_threadsafe` call (during `close()`). That
raised at close time:

```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

`anyio`'s cancel scopes (which `ClientSession`/`stdio_client` use
internally) require `__aenter__` and `__aexit__` to happen in the *same*
asyncio Task — and each separately-scheduled `run_coroutine_threadsafe`
call runs as its own Task, even on the same thread/loop. `list_tools()`
and `call_tool()` were confirmed to work fine when scheduled as separate
tasks (they don't open their own cancel scope, just send a request and
await the existing session's response) — only the enter/exit pair needed
fixing. The fix: restructure so `_session_main()` is a single coroutine
that opens both context managers, signals readiness via a
`threading.Event`, waits on an `asyncio.Event` for a stop signal, and lets
the `async with` blocks close naturally when that event fires — one Task,
start to finish. This was caught with a small throwaway MCP server and
client script before it was ever pointed at the real `file_system`/`shell`
servers, exactly so a concurrency bug wouldn't surface for the first time
against production code.

### `register_mcp_tools()`

```python
def register_mcp_tools(registry, *, command, args=None, env=None):
    client = McpClient(command=command, args=args, env=env)

    def make_block(tool_name):
        return lambda **kwargs: client.call_tool(tool_name, kwargs)

    for tool in client.list_tools():
        parameters = (tool.inputSchema or {}).get("properties", {})
        registry.tool(tool.name, tool.description or "", parameters, make_block(tool.name))

    return client
```

Notes:
- **`make_block` is a factory, not an inline lambda in the loop** — the
  classic Python late-binding-closure bug (a lambda referencing the loop
  variable `tool.name` directly would see whatever `tool` was left as
  after the loop finished, not the value at each iteration). This mirrors
  the same care Ruby's block-based `registry.tool` calls get "for free"
  from the language's per-call closure semantics.
- **`inputSchema["properties"]`, not the full `inputSchema`** — passing
  the whole JSON Schema object through as `parameters` would double-wrap
  it once `backends/anthropic.py` builds its own `{"type": "object",
  "properties": tool.parameters, ...}` around it. Only the properties dict
  is what boukensha's existing `Tool.parameters` shape expects.
- **Verified schema fidelity**: per-parameter `description`s survive the
  round trip only if the MCP server functions use
  `Annotated[str, Field(description="...")]` (plain type hints alone
  produce a schema with `title` but no `description`) — confirmed via a
  throwaway FastMCP server before writing the real ones, then applied
  consistently across both `file_system_server.py` and `shell_server.py`
  so the tool descriptions the model sees are unchanged from the pre-MCP
  version.

### `boukensha/mcp_servers/file_system_server.py` / `shell_server.py`

Both are line-for-line translations of the logic that used to live
directly in `tools/file_system.py`/`tools/shell.py` — same sandboxing
(`_resolve`, the traversal check), same shell-allow-list semantics, same
error-string conventions (`"error: ..."` rather than raising) — just moved
into a standalone script decorated with `@mcp.tool()` instead of a closure
registered via `registry.tool(...)`. Configuration that used to arrive as
Python function arguments (`working_dir`, `timeout`, `allowed_commands`)
now arrives via environment variables, since a subprocess has no other
direct channel to receive them from its parent at spawn time:

| Env var | Consumer | Meaning |
|---|---|---|
| `BOUKENSHA_MCP_FS_ROOT` | `file_system_server.py` | Sandboxed root directory (required) |
| `BOUKENSHA_MCP_SHELL_ROOT` | `shell_server.py` | `cwd` for spawned commands (required) |
| `BOUKENSHA_MCP_SHELL_TIMEOUT` | `shell_server.py` | Seconds before a command is killed (default `"30"`) |
| `BOUKENSHA_MCP_SHELL_ALLOWED` | `shell_server.py` | Comma-separated allow-list; unset = allow all; present-but-empty = reject everything (same emergent behavior as the pre-MCP version's `allowed_commands=[]`, not a special case) |

`tools/file_system.py`/`tools/shell.py` set these when constructing the
`env` dict passed to `register_mcp_tools()`; `stdio_client` (confirmed by
reading its source, `mcp/client/stdio.py`) merges that dict with a curated
default environment rather than replacing the subprocess's environment
entirely, so `PATH`/`HOME`/etc. are still present in the child process.

### Verification performed (not just read-through)

1. **Registry-level, isolated**: `register_mcp_tools()` against both real
   servers in a temp directory — `pwd`/`list_directory`/`read_file`/
   `write_file`/`search_files`/`delete_file`/`run_command`, path-traversal
   rejection, and `allowed_commands` enforcement all produced **identical
   output** to the pre-MCP direct-Python version.
2. **Through `tools/file_system.py`/`tools/shell.py`'s actual
   `register()`** (not the lower-level helper directly) — same checks,
   same results, confirming the production call path works end to end.
3. **Through a real `Agent` loop with a real Claude API call**: a
   `boukensha.run(task="List the files ... read notes.txt ... tell me the
   secret ingredient", working_dir=<tmp dir with a planted file>, mud=False)`
   call correctly listed the directory, read the file via the MCP-backed
   tools, and answered from its contents — proof the whole chain
   (`Agent` → `Registry.dispatch` → `Tool.block` → `McpClient.call_tool` →
   subprocess → response → back into the model's next turn) works under
   real conditions, not just in isolation.
4. **Architecture-preservation check**: `grep -rl "mcp" boukensha/*.py
   boukensha/backends/*.py boukensha/tasks/*.py boukensha/tools/mud.py` →
   only `mcp_client.py` itself, confirming no other file was touched.

### Known limitations (documented, not fixed)

- **Subprocess lifecycle**: each `working_dir`-registering call spawns two
  subprocesses (file-system and shell servers) that live until `atexit`
  fires on normal process exit, or until the caller explicitly closes the
  `McpClient` handles `file_system.register()`/`shell.register()` now
  return. A process calling `boukensha.run()` many times in a loop (rather
  than once, or via the REPL's single registration) accumulates one
  subprocess pair per call unless it manages those handles itself.
- **`mud` was not converted**, by design — see "Scope decisions" above.
- **No Ruby equivalent exists or is planned** — this addendum is Python-only.
