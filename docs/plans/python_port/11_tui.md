# Python Port Plan — 11_tui

## Goal

Port `week1_baseline/ruby/11_tui` to `week1_baseline/python/11_tui`. Same
behavior, new language, one new module (`boukensha/tui.py`) plus the small
set of wiring changes it depends on. **No new features beyond what Ruby 11
actually adds. Plan only — no source files are touched by writing this
document.**

**This plan only covers what changed between the Python baseline
(`10_standard_tool_library`) and Ruby 11.** Everything already ported
correctly through `10_standard_tool_library` (the agent loop, backends,
config, MCP-backed `file_system`/`shell` tools, the MUD tool suite,
`Logger#subscribe`) stays exactly as it is. Nothing gets rewritten from
scratch and nothing that already works gets touched or regenerated.

**Starting point:** `week1_baseline/python/11_tui` does not exist yet.
It starts as a copy of the finished `week1_baseline/python/10_standard_tool_library`
tree, then receives the delta below in place — the same "in-place edit of
the copied tree" pattern every prior step has used, not a from-scratch build.

## Source of truth (what changed, Ruby 10 → Ruby 11)

Verified with `diff -rq ruby/10_standard_tool_library/lib ruby/11_tui/lib`,
a full-text diff of every file it flagged, `diff` on `examples/`, `Gemfile`,
`boukensha.gemspec`, and `README.md`, plus direct inspection of the new
`patches/bubbletea/` directory:

| Ruby file | Change vs. 10 | Status |
|---|---|---|
| `lib/boukensha/tui.rb` | **NEW** — `Boukensha::Tui`, a bubbletea/lipgloss/bubbles four-zone terminal UI wrapping a `Repl` | New — see design section below |
| `lib/boukensha/repl.rb` | `Repl` refactored for composability: `on_output(&block)` routes all output through a callback instead of `puts`; `handle_command`/`run_turn` made public (were private/inline) so `Tui` can drive them; `attr_reader :logger, :context, :model, :version` added | `repl.py` needs the equivalent refactor, preserving its own existing `/quiet`/`/loud` commands (Python-only, not in Ruby, not touched) |
| `lib/boukensha/logger.rb` | `Logger#subscribe` — broadcasts every structured log event to registered subscribers in addition to writing the JSONL file | **Already present in `logger.py`** (confirmed via `grep -n subscribe`) — no change needed |
| `lib/boukensha.rb` | `self.repl` gains a `tui:` keyword (default `true`); dispatches to `Tui.new(repl).start` when `tui` is true and `Tui` is defined, else `repl.start` | `__init__.py`'s `repl()` needs a matching `tui=True` kwarg and dispatch |
| `lib/boukensha/version.rb` | `VERSION` bumped `0.10.0` → `0.11.0` | `version.py` needs to become `"0.11.0"` |
| `lib/boukensha_loader.rb` | Gains `--no-tui` CLI flag handling (`ARGV.delete("--no-tui")` → `repl_opts[:tui] = false`) | **Out of scope** — Ruby packaging/global-executable concern, no Python equivalent (see `10_standard_tool_library.md`'s identical call on `boukensha_loader.rb`/`bin/boukensha`). The `--no-tui` *behavior* is what matters and is ported via `repl(tui=...)`; the CLI-flag plumbing is Ruby-gem-executable-specific |
| `Gemfile`, `boukensha.gemspec` | Adds `gem "charm"` / `spec.add_dependency "charm"` (bubbletea + lipgloss + bubbles + bubblezone + glamour + gum + harmonica + ntcharts, ~8 sub-gems) | `requirements.txt` needs one new dependency: `textual` — see framework choice below |
| `patches/bubbletea/*` | **NEW** — a native-extension (C) patch for a burst-input bug in the precompiled `bubbletea` gem (see design section) | **Out of scope, and does not apply** — Textual has no analogous bug (see below) |
| `examples/example.rb` | **Unchanged** from step 10 (confirmed via `diff` — the one line that differs, `BOUKENSHA_DIR` path depth, is a **pre-existing off-by-one bug in Ruby 11's copy**, not a step-11 feature; see callout below) | `examples/example.py` carries over from `10_standard_tool_library` **unchanged** — do not port the Ruby 11 path regression |
| `README.md` | Documents `Tui`, the `tui:` keyword, the `Repl` refactor, `Logger#subscribe`, and switches the "Run Example" section from `examples/example.rb` to the global `boukensha` executable | See README plan below |
| `lib/boukensha/tools/file_system.rb`, `tools/shell.rb`, `mcp_client.rb`, `mcp_servers/*.rb` | MCP-backed tool transport (added in this same working session, on top of step 10/11) | **Already present in Python** — `boukensha/mcp_client.py` and `boukensha/mcp_servers/*.py` were ported *before* Ruby's equivalent existed (Python got MCP first). No new work; carries forward unchanged from `10_standard_tool_library` |
| `Gemfile`'s `mud_manager` path fix | A pre-existing bug fix (missing `path:` override), unrelated to the TUI feature itself | **Out of scope** — Ruby packaging bug, no Python equivalent; Python's `mud_manager` port already resolves correctly via a `sys.path` insert, not a Bundler path dependency |
| `lib/boukensha/registry.rb`, `tool.rb`, `context.rb`, `errors.rb`, `message.rb`, `prompt_builder.rb`, `agent.rb`, `run_dsl.rb`, `client.rb`, `config.rb`, `backends/*.rb`, `tasks/*.rb`, `tools/mud.rb` | Unchanged (confirmed via `diff -q`, file by file) | No change |
| `prompts/system.md` | Unchanged | No change |

### Pre-existing Ruby bug found, deliberately not carried forward

`examples/example.rb` in `ruby/11_tui` differs from `ruby/10_standard_tool_library`'s
copy by exactly one line:

```diff
- ENV["BOUKENSHA_DIR"] ||= File.expand_path("../../../../.boukensha", __dir__)
+ ENV["BOUKENSHA_DIR"] ||= File.expand_path("../../../.boukensha", __dir__)
```

Both files live at the same depth (`ruby/<step>/examples/example.rb`), so the
correct relative path to the repo-root `.boukensha/` is identical in both —
four `../` segments (`examples` → `<step>` → `ruby` → `week1_baseline` →
repo root). Step 10's four-`../` version is correct; step 11's
three-`../` version resolves to `week1_baseline/.boukensha` instead, which
doesn't exist. This only bites when `BOUKENSHA_DIR` isn't already set in the
environment before running the example directly — a real but narrow,
easy-to-miss regression, the same category of thing `10_standard_tool_library.md`
flagged for `client.rb`/`config.rb`. **Not ported**: Python's
`examples/example.py` already computes this path independently and
correctly (`Path(__file__).resolve().parents[4]`, confirmed 4 levels), and
is carried over unchanged, so this bug has no way to reach Python.

## Scope decision: Textual as the TUI framework

Ruby's `charm` gem is FFI bindings to compiled Go libraries (bubbletea +
lipgloss + bubbles, a precompiled **platform gem** with a C extension glue
layer) — there is no direct Python equivalent to "bind the same Go
binaries," and building one would be a large, out-of-scope undertaking for
a teaching repo. The natural Python analog, confirmed available
(`pip index versions textual` → `8.2.8` latest, actively maintained), is
**[Textual](https://textual.textualize.io/)**:

| Ruby (bubbletea/lipgloss/bubbles) | Python (Textual) |
|---|---|
| `Bubbletea::Model` (`init`/`update`/`view`) + `Bubbletea::Runner` | `textual.app.App` (`compose`, message handlers, reactive attributes) + its own built-in async run loop |
| `Lipgloss::Style.new.foreground(hex).background(hex).bold(true)` | Textual CSS (`color: #hex; background: #hex; text-style: bold;`), applied via a `CSS`/`DEFAULT_CSS` class attribute or a `.tcss` file |
| `Bubbles::Viewport` (scrollable text pane) | `textual.widgets.RichLog` (auto-scrolling log widget) |
| `Bubbles::TextArea` (configured to `height = 1`, i.e. really a single-line input) | `textual.widgets.Input` (single-line text entry with `placeholder`) — the more precise analog for how Ruby actually uses it, despite the Ruby class being named `TextArea` |
| `Bubbletea.tick(seconds) { TickMsg.new }` (recurring spinner tick) | `self.set_interval(seconds, self._on_tick)` |
| `Thread.new { @repl.run_turn(input) }` (background agent turn) | `self.run_worker(self._run_turn_worker, thread=True)` |
| `Queue.new` drained in the tick handler (cross-thread event delivery) | See threading/event-bridge decision below |

### Why no patch-the-native-extension step is needed

The `patches/bubbletea/` directory exists because `bubbletea`'s C extension
does one `read()` of up to 256 bytes per poll, parses a single key event,
and **discards the rest of the chunk** — a real bug that drops keystrokes
whenever more than one byte arrives in a single read (fast typing, paste,
or — relevant to how this project's own testing works — anything feeding
input faster than a human types). Textual has no equivalent failure mode:
it's pure Python, reads from its own async stream abstraction with proper
buffering, and there's no native extension to patch or reinstall-and-lose.
**This is a case where the Python port is structurally simpler than Ruby,
not a gap to fill.**

### Threading / event-bridge decision (needs your confirmation)

Ruby's `Tui` receives live progress updates from the background turn
thread via a plain `Queue`, drained on every tick (60ms) on the main UI
thread — a polling design, with comments in the source explicitly about
tuning `input_timeout`/`fps` to trade idle CPU against latency.

Textual's own idiomatic pattern for a threaded worker is
`self.call_from_thread(callback, *args)`, which pushes an update into the
UI's message loop immediately, from the worker thread, with no polling
needed at all. This plan recommends switching to `call_from_thread` in the
Python port — same event *content* as Ruby's `Logger#subscribe`
callback (`iteration`, `tool_call`, `tool_result`, `response`,
`turn_complete`, etc.), just delivered push-style instead of drained on a
timer. The spinner animation still needs its own lightweight
`set_interval` tick (advancing the frame index and elapsed-seconds
counter has nothing to do with event delivery), but the event-queue/timer
coupling Ruby needed disappears. **Recommended over a literal `Queue`-port**
because it removes an entire tuning axis (poll interval vs. CPU vs.
latency) that only existed to work around bubbletea's threading model, not
because boukensha's own logic needs it. Flag if you'd rather mirror Ruby's
queue-and-drain structure exactly instead, for closer traceability to the
source.

### Cancellation decision (needs your confirmation)

Ruby's `Esc` key calls `@turn_thread.raise(Interrupt)` — Ruby threads
support asynchronous exception injection from another thread, so the
in-flight turn actually stops wherever it happens to be. **Python's
`threading.Thread` has no safe, built-in equivalent** — there is no
sanctioned way to force an exception into an arbitrary point in another
thread's execution. Three options, in order of how closely they preserve
Ruby's actual behavior:

1. **`ctypes.pythonapi.PyThreadState_SetAsyncExc`** — the same trick
   libraries like `stopit` use to fake Ruby's `Thread#raise`. Closest
   behavioral match, but a known-hacky CPython-internals technique: raising
   at an arbitrary bytecode boundary can leave objects (e.g. an open
   subprocess pipe mid-`Open3`-equivalent call) in an inconsistent state.
2. **Cooperative cancellation** — a `threading.Event` the agent loop checks
   between iterations, raising internally when set. Safe and clean, but
   requires a small change to `agent.py`'s iteration loop to add a
   checkpoint — touching code this plan otherwise treats as frozen/shared.
3. **Detach, don't kill** (recommended) — `Esc` immediately marks the turn
   as interrupted *in the UI* (stops the spinner, prints `[interrupted]`,
   returns control to the input box) but lets the worker thread finish
   its current blocking call in the background; its eventual result is
   discarded on arrival since the UI has already moved on. Simplest, safest,
   no changes outside `tui.py` — the tradeoff is a real in-flight LLM call
   or MCP tool call keeps running to completion server-side/subprocess-side
   even though the UI stopped waiting for it, unlike Ruby's true abort.

This plan defaults to **option 3** in the code sketch below (zero blast
radius, no shared-code changes) but this is exactly the kind of judgment
call worth confirming before writing the actual implementation, given it's
a real, user-visible behavior difference from Ruby, not just an
implementation detail.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/tui.py` — `Tui`, a Textual `App` subclass wrapping a `Repl`
- `bin/python/11_tui` — launcher script for the *interactive* TUI (doesn't
  exist yet; distinct from `examples/example.py`, same reasoning as Ruby's
  README: the TUI needs its own entry point, not the one-shot MUD demo)

**FILL (small additions to existing files, currently identical to 10):**
- `boukensha/repl.py` — add `on_output`, promote `handle_command`/`_run_turn`
  to public `handle_command`/`run_turn` returning `"quit"`/`"command"`/`None`
  (matching Ruby's `:quit`/`:command`/`nil` sentinels), route all `print()`
  calls (including the existing `/quiet`/`/loud` messages) through the
  output hook
- `boukensha/__init__.py` — add `tui=True` kwarg to `repl()`; dispatch to
  `Tui(repl).run()` when true, else `repl.start()` (mirrors Ruby's
  `if tui && defined?(Tui) ... else repl.start end`)
- `boukensha/version.py` — bump to `"0.11.0"`
- `requirements.txt` — add `textual`

**LEAVE AS-IS (confirmed identical Ruby 10→11, or already covered by prior
Python work):**
- `boukensha/logger.py` — `subscribe` already present, no change
- `boukensha/mcp_client.py`, `boukensha/mcp_servers/*.py`,
  `boukensha/tools/file_system.py`, `boukensha/tools/shell.py` — MCP
  transport already ported (predates Ruby's own MCP work), no change
- `boukensha/tools/mud.py`, `boukensha/agent.py`, `client.py`, `config.py`,
  `context.py`, `registry.py`, `tool.py`, `errors.py`, `message.py`,
  `prompt_builder.py`, `run_dsl.py`, `backends/*.py`, `tasks/*.py`
- `examples/example.py` — carried over unchanged from `10_standard_tool_library`
  (matches Ruby: `examples/example.rb` is unchanged step-10-to-11, modulo
  the off-by-one bug this plan deliberately does not port — see above)
- `prompts/system.md`

**OUT OF SCOPE (Ruby packaging/native-extension concerns, no Python
equivalent needed):**
- `lib/boukensha_loader.rb`'s `--no-tui` CLI flag plumbing, `bin/boukensha`
  — same "no Python global-executable step" reasoning as
  `10_standard_tool_library.md` gave for the loader itself; the *behavior*
  (`tui: false`) is ported via `repl(tui=...)`, just not the argv-parsing
  wrapper
- `patches/bubbletea/*` — Textual has no analogous native-extension bug
  (see above)
- `Gemfile`'s `mud_manager` path fix — Ruby packaging bug fix, Python's
  `mud_manager` port already resolves correctly

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree

## Target structure

```
week1_baseline/python/11_tui/
  README.md
  requirements.txt                 <- adds `textual`
  prompts/
    system.md
  boukensha/
    __init__.py                    <- FILL: tui=True kwarg + dispatch
    version.py                     <- FILL: "0.11.0"
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    prompt_builder.py
    logger.py                      <- unchanged, subscribe() already present
    run_dsl.py
    client.py
    agent.py
    repl.py                        <- FILL: on_output/handle_command/run_turn
    tui.py                         <- NEW
    mcp_client.py                  <- unchanged
    mcp_servers/
      __init__.py
      file_system_server.py        <- unchanged
      shell_server.py              <- unchanged
    tools/
      __init__.py
      file_system.py               <- unchanged
      shell.py                     <- unchanged
      mud.py                       <- unchanged
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
    example.py                     <- unchanged (MUD one-shot demo)

week1_baseline/bin/python/11_tui    <- NEW
```

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha/tui.rb` | `boukensha/tui.py` | NEW — bubbletea/lipgloss/bubbles → Textual |
| `lib/boukensha/repl.rb` | `boukensha/repl.py` | Add `on_output`/public `handle_command`/`run_turn`; keep existing `/quiet`/`/loud` |
| `lib/boukensha/logger.rb` | `boukensha/logger.py` | **No change** — `subscribe` already present |
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add `tui=` kwarg + dispatch to `repl()` |
| `lib/boukensha/version.rb` | `boukensha/version.py` | `VERSION = "0.11.0"` |
| `Gemfile`'s `charm` | `requirements.txt`'s `textual` | New TUI dependency |
| `patches/bubbletea/*` (out of scope) | — | No Python equivalent needed |
| `lib/boukensha_loader.rb`'s `--no-tui` (out of scope) | — | Behavior ported via `repl(tui=...)`; CLI-wrapper plumbing has no Python step |
| `examples/example.rb` (unchanged since step 10) | `examples/example.py` (unchanged since step 10) | Neither file changes in this step |
| `README.md` | `README.md` | Document `Tui`, `tui=` kwarg, `Repl` refactor, new "Run Example" section |
| `bin/ruby/11_tui`-via-`bin/boukensha` (gem executable) | `bin/python/11_tui` (**new**, plain launcher script) | No installed-executable/loader equivalent |

## New/changed class behavior

### `boukensha/tui.py` (new)

```python
import time
import threading
from queue import Empty

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Input, Static
from textual import events

from .version import VERSION
from .agent import Agent

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
TICK_SECONDS = 0.06

# Same four colors as Ruby's ANSI_COLORS hash — ported 1:1, Textual CSS
# accepts hex colors directly, no translation needed beyond the syntax.
COLORS = {
    "blue":   "#3d60ff",
    "violet": "#c77dff",
    "red":    "#b80041",
    "gold":   "#e59600",
}


class Tui(App):
    # Textual CSS is the direct analog of Ruby's Lipgloss::Style chains —
    # declarative styling instead of a fluent builder, same four colors.
    CSS = f"""
    #progress {{ color: {COLORS["violet"]}; }}
    #progress.idle {{ color: {COLORS["gold"]}; }}
    #prompt {{ color: {COLORS["red"]}; text-style: bold; }}
    #status {{ color: {COLORS["blue"]}; background: {COLORS["violet"]}; }}
    RichLog {{ height: 1fr; }}
    Input {{ height: 1; }}
    Static {{ height: 1; }}
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("escape", "interrupt", "Interrupt"),
        ("ctrl+l", "clear", "Clear"),
        ("pageup", "scroll_up", "Scroll up"),
        ("pagedown", "scroll_down", "Scroll down"),
    ]

    def __init__(self, repl):
        super().__init__()
        self.repl = repl
        self.context = repl.context
        self.turn_count = 0
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.turn_thread = None

        self.live_active = False
        self.spinner_idx = 0
        self.start_time = None
        self.elapsed = 0
        self.current_action = "idle"
        self.iteration = 0
        self.tool_call_count = 0
        self.turn_input_tokens = 0
        self.turn_output_tokens = 0

    def compose(self) -> ComposeResult:
        yield RichLog(id="conversation", wrap=True)
        yield Static(id="progress")
        yield Input(id="prompt_input", placeholder="Type a message…")
        yield Static(id="status")

    def on_mount(self):
        self.query_one("#conversation", RichLog).write(self.repl.banner())
        self.repl.on_output(lambda s: self.query_one("#conversation", RichLog).write(s))
        self.repl.logger.subscribe(self._on_log_event)
        self.query_one("#prompt_input", Input).focus()
        self.set_interval(TICK_SECONDS, self._on_tick)
        self.render_progress()
        self.render_status()

    # ── event delivery from the worker thread ──────────────────────────────
    # Pushed via call_from_thread (see "Threading / event-bridge decision"
    # above) instead of Ruby's Queue-drained-on-tick — Textual delivers this
    # safely onto the UI's own event loop for us.
    def _on_log_event(self, event):
        self.call_from_thread(self._handle_event, event)

    def _handle_event(self, event):
        phase = event.get("phase")
        if phase == "iteration":
            self.iteration = int(event.get("n", 0))
            self.current_action = "Thinking…"
        elif phase == "tool_call":
            self.current_action = f"Calling tool: {event.get('name')}"
            self.tool_call_count += 1
        elif phase == "tool_result":
            self.current_action = "Awaiting result…"
        elif phase == "response":
            usage = event.get("usage") or {}
            itu = int(usage.get("input_tokens", 0) or 0)
            otu = int(usage.get("output_tokens", 0) or 0)
            self.turn_input_tokens += itu
            self.turn_output_tokens += otu
            self.session_input_tokens += itu
            self.session_output_tokens += otu
        elif phase == "turn_complete":
            self.live_active = False
            self.turn_count += 1
        elif phase == "turn_interrupted":
            self.query_one("#conversation", RichLog).write("[interrupted]")
        elif phase == "turn_error":
            self.live_active = False
            self.query_one("#conversation", RichLog).write(f"[error] {event.get('error')}")

        self.render_progress()
        self.render_status()

    def _on_tick(self):
        if self.live_active:
            self.spinner_idx = (self.spinner_idx + 1) % len(SPINNER_FRAMES)
            if self.start_time:
                self.elapsed = time.monotonic() - self.start_time
            self.render_progress()

    # ── rendering ───────────────────────────────────────────────────────────

    def render_progress(self):
        bar = self.query_one("#progress", Static)
        if self.live_active:
            frame = SPINNER_FRAMES[self.spinner_idx]
            bar.remove_class("idle")
            bar.update(
                f"{frame} {self.current_action}  (iter {self.iteration}/{Agent.MAX_ITERATIONS} · "
                f"{int(self.elapsed)}s · ↑ {self._fmt(self.turn_input_tokens)} · "
                f"↓ {self._fmt(self.turn_output_tokens)} · {self.tool_call_count} calls)"
            )
        else:
            bar.add_class("idle")
            bar.update(f"  [ready]   ctx {self._fmt(self.session_input_tokens)}   {self.turn_count} turns")

    def render_status(self):
        bar = self.query_one("#status", Static)
        clock = time.strftime("%H:%M:%S")
        bar.update(
            f" boukensha v{self.repl.version or VERSION} · {self.repl.model or '(model)'}  ·  "
            f"ctx {self._fmt(self.session_input_tokens)}  ·  {self.context.tool_count} tools  ·  {clock} "
        )

    @staticmethod
    def _fmt(n):
        n = int(n or 0)
        return f"{n / 1000.0:.1f}k" if n >= 1000 else str(n)

    # ── input handling ──────────────────────────────────────────────────────
    # Input.Submitted is Textual's own "Enter pressed in this field" message
    # — no manual `case msg.name when "enter"` dispatch needed, unlike Ruby's
    # raw KeyMessage handling (Textual's Input widget already does its own
    # key handling internally; this is the idiomatic hook for "done typing").

    def on_input_submitted(self, message: Input.Submitted):
        text = message.value.strip()
        self.query_one("#prompt_input", Input).value = ""
        if not text:
            return

        if text.startswith("/"):
            result = self.repl.handle_command(text)
            if result == "quit":
                self.exit()
            elif text == "/clear":
                self.turn_count = 0
                self.render_progress()
            return

        self.query_one("#conversation", RichLog).write(f"> {text}")
        self._launch_turn(text)

    def _launch_turn(self, text):
        self.live_active = True
        self.spinner_idx = 0
        self.start_time = time.monotonic()
        self.elapsed = 0
        self.current_action = "Thinking…"
        self.iteration = 0
        self.tool_call_count = 0
        self.turn_input_tokens = 0
        self.turn_output_tokens = 0
        self.render_progress()

        self.turn_thread = self.run_worker(self._run_turn_worker, text, thread=True, exclusive=True)

    def _run_turn_worker(self, text):
        try:
            self.repl.run_turn(text)
        finally:
            self.repl.logger._subscribers and self._on_log_event({"phase": "turn_complete"})

    # ── key bindings ────────────────────────────────────────────────────────

    def action_quit(self):
        self.exit()

    def action_interrupt(self):
        # "Detach, don't kill" — see cancellation decision above. The worker
        # thread is not forcibly stopped; the UI just stops treating it as
        # active and its eventual result is discarded when it arrives.
        if self.turn_thread and self.turn_thread.is_running:
            self.live_active = False
            self._on_log_event({"phase": "turn_interrupted"})

    def action_clear(self):
        self.repl.handle_command("/clear")
        self.turn_count = 0
        self.render_progress()

    def action_scroll_up(self):
        self.query_one("#conversation", RichLog).scroll_up()

    def action_scroll_down(self):
        self.query_one("#conversation", RichLog).scroll_down()
```

Notes:
- **`RichLog.write(s)` appends and auto-scrolls** — the direct analog of
  Ruby's `@conversation << str; @dirty = true` followed by
  `@viewport.content = ...; @viewport.goto_bottom` on the next render.
  Textual's widget owns its own scroll-to-bottom behavior, so there's no
  separate "dirty flag + rebuild content on next view()" step to port —
  another place Textual's widget model does more of the work than
  bubbletea's immediate-mode `view` did.
- **`Input.Submitted` replaces manual `"enter"` key-name matching.**
  Ruby's `Tui#handle_key` has to special-case `msg.name == "enter"` itself
  because bubbletea hands you raw key events; Textual's `Input` widget
  already parses "user pressed Enter while this field is focused" into its
  own message type. All the *other* keys (`ctrl+c`, `esc`, `ctrl+l`,
  `pgup`/`pgdown`) go through Textual's declarative `BINDINGS` list instead
  of a `case` statement — same behavior, more idiomatic shape for the
  framework.
- **`exclusive=True` on `run_worker`** ensures a second Enter-press can't
  spawn a second concurrent turn while one is already running — Ruby gets
  this for free because `@turn_thread` is a single instance variable and
  `submit_input` doesn't check it before launching a new one either
  (**actually a latent bug in the Ruby source**: nothing stops
  double-submission mid-turn in `tui.rb` today; this plan intentionally
  makes the Python port *slightly* more defensive here rather than
  faithfully reproducing that gap, since it's a one-line, zero-cost
  safeguard rather than a behavior change worth debating — flag if you'd
  rather match Ruby exactly instead).
- The `_run_turn_worker`'s `finally` block emitting a synthetic
  `turn_complete` mirrors Ruby's `Thread.new { ... } ensure @events <<
  {phase: :turn_complete} end` — needed because `Logger#subscribe`'s
  `response`/`tool_call`/etc. events don't include a terminal "the turn as
  a whole is done" signal on their own.

### `boukensha/repl.py` (filled in)

Only the pieces that change; everything else (the `/quiet`/`/loud`
handling, `_banner`/`_mud_status_string`/`_probe_mud`, `Agent` construction)
stays as it is today.

```python
class Repl:
    ...
    def __init__(self, ..., ...):
        ...
        self._output_cb = None

    def on_output(self, callback):
        self._output_cb = callback

    def _output(self, s):
        if self._output_cb:
            self._output_cb(str(s))
        else:
            print(s)

    def banner(self):          # renamed from _banner — Tui calls it directly
        return self._banner()

    def handle_command(self, line):
        """Handle a slash command. Returns 'quit', 'command', or None."""
        if line in ("/exit", "/quit"):
            self._output("Goodbye.")
            return "quit"
        elif line == "/help":
            self._output(self.HELP)
            return "command"
        elif line == "/quiet":
            from . import quiet
            quiet()
            self._output("(logging suppressed — type /loud to re-enable)")
            return "command"
        elif line == "/loud":
            from . import loud
            loud()
            self._output("(logging enabled)")
            return "command"
        elif line == "/clear":
            self.context.clear_messages()
            self.turn = 0
            self._output("(conversation history cleared)")
            return "command"
        return None

    def run_turn(self, text):      # renamed from _run_turn — public, Tui calls it
        self.turn += 1
        self.logger.turn(n=self.turn)
        self.context.add_message("user", text)

        agent = Agent(
            context=self.context, registry=self.registry, builder=self.builder,
            client=self.client, logger=self.logger, task_settings=self.task_settings,
            max_iterations=self.max_iterations, max_output_tokens=self.max_output_tokens,
        )
        try:
            result = agent.run()
        except LoopError as e:
            self._output(f"\n[error] {e}")
            return
        except ApiError as e:
            self._output(f"\n[error] API call failed: {e}")
            return

        self._output("")
        self._output(result)

    def start(self):
        self._output(self.banner())
        while True:
            try:
                line = input(self.PROMPT) if not self._output_cb else None
            except EOFError:
                break
            if self._output_cb:
                break  # Tui drives the loop itself via on_input_submitted

            line = line.strip()
            if not line:
                continue

            result = self.handle_command(line)
            if result == "quit":
                break
            if result == "command":
                continue

            self.run_turn(line)
```

Note: the `start()` guard (`break` immediately when `_output_cb` is set) is
a minor structural difference from Ruby's `Repl#start`, which still owns
its own `loop`/`gets` even in TUI mode and just skips printing the prompt
(`unless @output_cb`) — Ruby's `Tui` never actually drives `Repl#start`'s
loop at all; it calls `on_output` then runs its own bubbletea event loop
independently, and `Repl#start` is simply never invoked in TUI mode (only
`boukensha.rb`'s `if tui ... Tui.new(repl).start else repl.start end`
decides which one runs). Match that exactly in Python: `__init__.py`'s
`repl()` calls **either** `Tui(repl).run()` **or** `python_repl.start()`,
never both — the guard above is defensive/unreachable in practice, not a
real code path, included only for symmetry with Ruby's harmless `unless
@output_cb` prompt-suppression. Simplify or remove if it reads as noise
during implementation.

### `boukensha/__init__.py` (filled in)

```python
def repl(
    *,
    system=None, model=None, backend=None, api_key=None,
    ollama_host="http://localhost:11434", log=None, max_output_tokens=None,
    working_dir=None, allowed_commands=None, shell_timeout=30, mud=None,
    configure=None,
    tui=True,
):
    ... # unchanged setup through Repl(...) construction

    repl_instance = Repl(
        context=ctx, registry=registry, builder=builder, client=client,
        logger=logger, task_settings=task_settings,
        max_iterations=effective_max_iterations,
        max_output_tokens=effective_max_output_tokens,
        config_dir=cfg.dir, provider=backend, model=model,
        version=VERSION, api_key=api_key, mud=resolved_mud,
    )
    try:
        if tui:
            from .tui import Tui
            Tui(repl_instance).run()
        else:
            repl_instance.start()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if logger is not None:
            logger.close()
```

`from .tui import Tui` is deliberately deferred to inside the `if tui:`
branch (not a top-level import) so that `tui=False` callers — and anything
importing `boukensha` in an environment without a real terminal — never pay
for or require `textual` at all, mirroring Ruby's `defined?(Tui)` guard,
which likewise only matters if `Tui` failed to load.

### `requirements.txt`

```
PyYAML
python-dotenv
mcp>=1.28.1
textual
```

### `bin/python/11_tui` (new)

The TUI is interactive, so — matching the Ruby README's own reasoning for
switching its "Run Example" section away from `examples/example.rb` — this
launcher doesn't run `examples/example.py` (that stays the one-shot MUD
demo, unchanged). It's a small standalone entry point:

```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$HOME/code/virtualenv/claude/bin/activate"
cd "$(dirname "$0")/../../python/11_tui"

python3 -c "
import sys
sys.path.insert(0, '.')
import boukensha
boukensha.repl(tui='--no-tui' not in sys.argv)
"
```

Matches Ruby's `--no-tui` flag exactly (same flag name, same meaning),
without needing a loader/global-executable layer — Python steps are always
run via their `bin/python/<step>` launcher, never an installed CLI.

## README plan

Mirror the Ruby README's structure and additions for this step:
- A "What's new" section covering `Tui`, the `Repl` refactor
  (`on_output`/`handle_command`/`run_turn` now public), and the `tui=`
  kwarg — `Logger.subscribe` is *not* listed as new (already shipped in
  `10_standard_tool_library`'s Python README, if it documented it there;
  confirm and cross-reference rather than re-describing it as new).
- Replace the "Run Example" section's `python3 examples/example.py`
  invocation with `bin/python/11_tui` for the interactive TUI, keeping a
  note that `examples/example.py` (the MUD one-shot demo) is unchanged and
  still runnable the old way.
- A short keyboard-shortcut table, identical to Ruby's (same keys, same
  actions — Textual's `BINDINGS` reproduces them exactly).
- No "native-extension patch" section — nothing to document, per the
  framework-choice section above.

## Decisions to confirm before implementation

- **Textual** as the TUI dependency (`textual` on PyPI, confirmed available,
  latest `8.2.8`) — no version pin proposed beyond a bare `textual` in
  `requirements.txt`, matching this project's established unpinned-deps
  convention (`PyYAML`, `python-dotenv`).
- **Event delivery**: `call_from_thread` push-style (recommended) vs. a
  literal `Queue`-drained-on-tick port for closer 1:1 traceability to
  Ruby's structure — see "Threading / event-bridge decision" above.
- **Cancellation on Esc**: "detach, don't kill" (recommended, zero blast
  radius) vs. `ctypes`-based forced exception injection vs. a cooperative
  cancellation checkpoint added to `agent.py` — see "Cancellation decision"
  above. This is the one place Python's threading model can't faithfully
  reproduce Ruby's `Thread#raise(Interrupt)`, and the tradeoff should be a
  conscious choice, not an accident of whichever was easiest to write.
- **`Input` vs. `TextArea` widget** for the prompt box — this plan
  recommends Textual's `Input` (single-line, matches how Ruby actually
  configures its `Bubbles::TextArea` at `height = 1`) over Textual's own
  `TextArea` widget (a multi-line code-editor-style widget that would be
  the more literal class-name match but the wrong shape for a one-line
  chat prompt).
- Whether to fix the tiny "double-submit while a turn is running" gap this
  plan noticed in Ruby's own `tui.rb` (via `run_worker(..., exclusive=True)`)
  or intentionally leave Python exactly as permissive as Ruby for parity —
  see the note under `tui.py` above.
