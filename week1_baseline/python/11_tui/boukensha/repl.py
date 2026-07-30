import socket
from pathlib import Path

from .agent import Agent
from .errors import ApiError, LoopError


class Repl:
    # Repl is the interactive session loop.
    #
    # It wraps the same primitives as a single boukensha.run() call, but
    # instead of running once it stays alive: it reads a task from the
    # user, runs the agent, prints the reply, and loops back to the prompt.
    #
    # The Context is shared across every turn so conversation history
    # accumulates naturally — the agent sees the full transcript each time
    # it is called.
    #
    # Built-in commands (not sent to the agent):
    #   /help    print the command list
    #   /quiet   suppress detailed logging
    #   /loud    re-enable logging
    #   /clear   wipe conversation history (tools stay registered)
    #   /exit    leave the REPL
    #   /quit    alias for /exit
    #
    # on_output/handle_command/run_turn are public so an alternate front-end
    # (Tui) can drive this same session logic instead of the raw
    # input()/print() loop in start().
    PROMPT = "boukensha> "

    HELP = """Commands:
  /quiet   suppress logging output
  /loud    re-enable logging output
  /clear   wipe conversation history (tools stay)
  /exit    leave the REPL
  /help    show this message
"""

    def __init__(self, *, context, registry, builder, client, logger,
                 config_dir=None, provider=None, model=None, version=None,
                 api_key=None, mud=None, task_settings=None, max_iterations=None,
                 max_output_tokens=None):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        self.logger = logger
        self.task_settings = task_settings
        self.max_iterations = max_iterations
        self.max_output_tokens = max_output_tokens
        self.config_dir = config_dir
        self.provider = provider
        self.model = model
        self.version = version
        self.api_key = api_key
        self.mud = mud
        self.turn = 0
        self._output_cb = None

    # Register a callback that receives every string the REPL would
    # otherwise print to stdout. When set, print() is suppressed entirely
    # and all output is routed through the callback instead. Used by Tui.
    def on_output(self, callback):
        self._output_cb = callback

    def banner(self):
        return self._banner()

    # Handle a slash command. Returns "quit", "command", or None (not a
    # command). Output is routed through the registered on_output callback
    # if present.
    def handle_command(self, line):
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

    def run_turn(self, text):
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
                line = input(self.PROMPT)
            except EOFError:
                break  # Ctrl-D

            line = line.strip()
            if not line:
                continue

            result = self.handle_command(line)
            if result == "quit":
                break
            if result == "command":
                continue

            self.run_turn(line)

    def _output(self, s):
        if self._output_cb:
            self._output_cb(str(s))
        else:
            print(s)

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

    # Build the mud status string shown in the banner.
    # Only checks TCP reachability — the tool session auto-connects at startup
    # (in tools/mud.py's register()), so probing login here would cause a
    # double-login.
    def _mud_status_string(self):
        if not self.mud:
            return "(not configured)"

        host = self.mud.get("host", "localhost")
        port = self.mud.get("port", 4000)
        name = self.mud.get("name")

        return f"{host}:{port}  {self._probe_mud(host, port, name)}"

    def _probe_mud(self, host, port, name):
        try:
            socket.create_connection((host, port), timeout=3).close()
        except OSError:
            return "✗ not reachable"
        except Exception as e:
            return f"✗ probe error: {e}"

        return "(Reachable)" if name and str(name).strip() else "(Reachable, no credentials)"
