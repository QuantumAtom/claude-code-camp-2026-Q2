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
                 api_key=None, task_settings=None, max_iterations=None,
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
        self.turn = 0

    def start(self):
        print(self._banner())

        while True:
            try:
                line = input(self.PROMPT)
            except EOFError:
                break  # Ctrl-D

            line = line.strip()
            if not line:
                continue

            if line in ("/exit", "/quit"):
                print("Goodbye.")
                break
            elif line == "/help":
                print(self.HELP)
                continue
            elif line == "/quiet":
                from . import quiet
                quiet()
                print("(logging suppressed — type /loud to re-enable)")
                continue
            elif line == "/loud":
                from . import loud
                loud()
                print("(logging enabled)")
                continue
            elif line == "/clear":
                self.context.clear_messages()
                self.turn = 0
                print("(conversation history cleared)")
                continue

            self._run_turn(line)

    def _banner(self):
        key_status = "✗ API key not set" if not (self.api_key and self.api_key.strip()) else "✓ API key set"
        provider_line = f"{self.provider or 'default'} ({self.model or 'default'})  {key_status}"
        config_exists = bool(self.config_dir) and Path(self.config_dir).is_dir()
        config_line = self.config_dir if config_exists else f"{self.config_dir or '(default)'}  ✗ directory not found"
        ver = self.version or "?.?.?"

        return f"""
╔══════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v{ver}){" " * (9 - len(ver))}║
╚══════════════════════════════════════╝
  config:    {config_line}
  provider:  {provider_line}

  /quiet or /loud   toggle logging
  /clear           reset conversation history
  /exit or /quit    leave the REPL
"""

    def _run_turn(self, text):
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
            print(f"\n[error] {e}")
            return
        except ApiError as e:
            print(f"\n[error] API call failed: {e}")
            return

        print()
        print(result)
