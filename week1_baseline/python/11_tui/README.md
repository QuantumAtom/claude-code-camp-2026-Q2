# 11 · A Terminal UI (Python)

Python port of [`week1_baseline/ruby/11_tui`](../../ruby/11_tui/README.md).

Boukensha now ships a full terminal UI (TUI) built on
[Textual](https://textual.textualize.io/) — the Python analog of Ruby's
`charm` gem (bubbletea + lipgloss + bubbles): an async app loop, a widget
library, and CSS-style declarative styling. The plain REPL from step 10 is
still there and can be selected with `tui=False`.

## What's new

### `boukensha.tui.Tui`

New class (`boukensha/tui.py`), a `textual.app.App` subclass. Wraps a `Repl`
instance and replaces its raw `print()`/`input()` I/O with a structured
four-zone display:

```
┌──────────────────────────────────────────────┐
│  conversation viewport (scrollable)           │
├──────────────────────────────────────────────┤
│  ⟳ live progress line (hidden when idle)     │
├──────────────────────────────────────────────┤
│  boukensha> input box                         │
├──────────────────────────────────────────────┤
│  status line (always-on)                      │
└──────────────────────────────────────────────┘
```

The **progress line** shows a spinner, current action, iteration counter
(`n/MAX`), elapsed seconds, token counts (↑ in / ↓ out), and tool call count
while the agent is running. When idle it shows context usage and turn
count.

The **status line** always shows: version · model · context tokens used ·
registered tool count · wall-clock time.

**Keyboard shortcuts:**

| Key | Action |
|-----|--------|
| `Enter` | Submit input or slash command |
| `Esc` | Interrupt the running agent turn |
| `Ctrl+L` | Clear conversation history |
| `PgUp` / `PgDn` | Scroll conversation viewport |
| `Ctrl+C` | Quit |

The agent runs on a background worker thread (`App.run_worker(...,
thread=True)`) so the UI stays responsive during long turns. Unlike Ruby's
`Thread#raise(Interrupt)`, Python has no safe way to force an exception into
another thread — `Esc` detaches the UI from the running turn (stops the
spinner, marks it interrupted) rather than truly aborting it; the worker
thread finishes its current call in the background and its result is
discarded on arrival. See `docs/plans/python_port/11_tui.md` for the
tradeoff this decision was weighed against.

### `boukensha.repl()` — new `tui=` keyword

```python
boukensha.repl(tui=True)   # default — launches the Textual TUI
boukensha.repl(tui=False)  # falls back to the plain terminal REPL
```

The `--no-tui` flag on `bin/python/11_tui` sets `tui=False` from the command
line.

### `Repl` refactored for composability

`Repl` no longer hard-codes `print()`/`input()`. Three methods are now
public so `Tui` (or any other front-end) can drive it:

| Method | Purpose |
|--------|---------|
| `on_output(callback)` | Route all REPL output through a callback instead of stdout |
| `handle_command(line)` | Process a slash command; returns `"quit"`, `"command"`, or `None` |
| `run_turn(text)` | Run one agent turn and route the result through `on_output` |

`banner()`, `logger`, `context`, `model`, and `version` are also available
as plain attributes/methods. The existing Python-only `/quiet`/`/loud`
commands (not present in Ruby) are unchanged and route through the same
`on_output` mechanism.

### `Logger.subscribe`

Already present since `10_standard_tool_library` — no change in this step.
`Tui` uses it to update the live progress line, delivered via
`App.call_from_thread(...)` from the background turn thread rather than a
polled queue (Textual's own thread-safety primitive, simpler than Ruby's
`Queue`-drained-on-tick since there's no bubbletea-style polling loop to
feed).

### File-system / shell tools (MCP) and MUD tools

Unchanged from `10_standard_tool_library` — this step is purely additive
(the TUI layer sits on top of the existing agent loop and tools, and
doesn't touch how they run).

One new dependency: `textual`, added to `requirements.txt`.

## Run Example

The TUI is interactive, so it's run via its own launcher rather than
`examples/example.py` (that file is the step 10 MUD demo, carried over
unchanged — it doesn't exercise the TUI):

```bash
# launches the Textual TUI:
./week1_baseline/bin/python/11_tui

# plain REPL (no textual dependency exercised):
./week1_baseline/bin/python/11_tui --no-tui
```

Requires the same `.boukensha/settings.yaml` + API key setup as every prior
step, plus `pip install -r week1_baseline/python/11_tui/requirements.txt`
(shared venv, same as every other step).
