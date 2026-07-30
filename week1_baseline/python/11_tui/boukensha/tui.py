import time

from textual.app import App, ComposeResult
from textual.widgets import RichLog, Input, Static

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
    #prompt_input {{ color: {COLORS["red"]}; }}
    #status {{ color: {COLORS["blue"]}; background: {COLORS["violet"]}; }}
    RichLog {{ height: 1fr; }}
    Input {{ height: 1; border: none; }}
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
        # markup=False: this text is literal data (tool names, error
        # messages, "[ready]"), not Rich console markup — Static defaults to
        # markup=True, which would otherwise parse a literal "[ready]" as an
        # (invalid) style tag and silently swallow it.
        yield Static(id="progress", markup=False)
        yield Input(id="prompt_input", placeholder="Type a message…")
        yield Static(id="status", markup=False)

    def on_mount(self):
        self.query_one("#conversation", RichLog).write(self.repl.banner())
        self.repl.on_output(self._on_output)
        self.repl.logger.subscribe(self._on_log_event)
        self.query_one("#prompt_input", Input).focus()
        self.set_interval(TICK_SECONDS, self._on_tick)
        self.render_progress()
        self.render_status()

    # ── output routed from Repl (banners, command replies, turn results) ───
    def _on_output(self, s):
        self.query_one("#conversation", RichLog).write(s)

    # ── event delivery from the worker thread ──────────────────────────────
    # Pushed via call_from_thread instead of a polled Queue — Textual
    # delivers this safely onto the UI's own event loop for us, removing the
    # poll-interval-vs-CPU-vs-latency tuning Ruby's Queue-drained-on-tick
    # design needed to work around bubbletea's threading model.
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
    # — no manual key-name dispatch needed, unlike Ruby's raw KeyMessage
    # handling (Textual's Input widget already does its own key handling
    # internally; this is the idiomatic hook for "done typing").

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

        self.turn_thread = self.run_worker(lambda: self._run_turn_worker(text), thread=True, exclusive=True)

    def _run_turn_worker(self, text):
        try:
            self.repl.run_turn(text)
        except Exception as e:
            self._on_log_event({"phase": "turn_error", "error": str(e)})
        finally:
            self._on_log_event({"phase": "turn_complete"})

    # ── key bindings ────────────────────────────────────────────────────────

    def action_quit(self):
        self.exit()

    def action_interrupt(self):
        # "Detach, don't kill": Python threads can't be safely force-killed
        # the way Ruby's Thread#raise(Interrupt) works, so this just stops
        # the UI from treating the turn as active — the worker thread
        # finishes its current blocking call in the background and its
        # result is discarded on arrival.
        if self.live_active:
            self.live_active = False
            self._handle_event({"phase": "turn_interrupted"})

    def action_clear(self):
        self.repl.handle_command("/clear")
        self.turn_count = 0
        self.render_progress()

    def action_scroll_up(self):
        self.query_one("#conversation", RichLog).scroll_up()

    def action_scroll_down(self):
        self.query_one("#conversation", RichLog).scroll_down()
