import os

from .config import Config
from . import telemetry

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


from .version import VERSION
from .models import Models
from .tool import Tool
from .message import Message
from .context import Context
from .errors import UnknownToolError, UnsupportedModelError, ApiError, LoopError
from .registry import Registry
from .prompt_builder import PromptBuilder
from .logger import Logger
from .client import Client
from .agent import Agent
from .backends.base import Base
from .backends.anthropic import Anthropic
from .backends.gemini import Gemini
from .backends.openai import OpenAI
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud
from .backends.zai import Zai
from .run_dsl import RunDSL
from .repl import Repl
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


# The top-level entry point. Wires together every primitive so the caller
# only has to describe *what* to do, not *how* to plumb it.
#
#   result = boukensha.run(task="Summarise lib/boukensha.rb", configure=lambda dsl: (
#       dsl.tool(
#           "read_file",
#           "Read a file from disk",
#           {"path": {"type": "string", "description": "File path"}},
#           lambda path: open(path).read(),
#       )
#   ))
#
# Options:
#   task:         (required) The user message to hand the agent.
#   system:       System prompt. Defaults to Config#system_prompt.
#   model:        Model name. Defaults to Config#model.
#   backend:      "anthropic" (default from settings), "openai", "gemini",
#                 "ollama", "ollama_cloud", or "zai".
#   api_key:      API key for the chosen backend. Defaults to the matching
#                 ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY / ZAI_API_KEY
#                 env var (loaded from .boukensha/.env). Not needed for "ollama".
#   ollama_host:  Ollama base URL. Defaults to "http://localhost:11434".
#   log:          Optional JSONL path override. Defaults to .boukensha/sessions/<session-id>.jsonl.
#   max_output_tokens: Per-reply output cap. Defaults to Config#agent_max_output_tokens.
#   configure:    Optional callback receiving a RunDSL — call dsl.tool(...)
#                 inside it to register tools.
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
    telemetry.configure()
    if system is None:
        system = cfg.system_prompt
    if model is None:
        model = cfg.model
    if backend is None:
        backend = cfg.provider_type
    if api_key is None:
        api_key = {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
            "ollama_cloud": os.environ.get("OLLAMA_API_KEY"),
            "zai": os.environ.get("ZAI_API_KEY"),
        }.get(backend)

    context_window = Models.context_window(model)

    # working_dir defaults to the caller's *current* cwd at call time, not
    # at import time — resolved here in the body (not as a Python default
    # argument) so it stays fresh across calls, matching Ruby's Dir.pwd
    # default which re-evaluates per invocation.
    resolved_working_dir = (
        None if working_dir is False
        else (working_dir if working_dir is not None else os.getcwd())
    )

    ctx = Context(system=system, context_window=context_window, working_dir=resolved_working_dir,
                  compaction_threshold=cfg.agent_compaction_threshold)
    registry = Registry(ctx)

    if resolved_working_dir:
        file_system.register(registry, working_dir=resolved_working_dir)
        shell.register(registry, working_dir=resolved_working_dir,
                        timeout=shell_timeout, allowed_commands=allowed_commands)

    # mud: None means "use config if host is set"; mud: False means "skip entirely"
    resolved_mud = None if mud is False else (mud or _mud_opts_from_config(cfg))
    if resolved_mud:
        mud_tools.register(registry, **resolved_mud)

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
    elif backend == "zai":
        be = Zai(api_key=api_key, model=model)
    else:
        raise ValueError(
            f"Unknown backend {backend!r}. Use 'anthropic', 'openai', "
            "'gemini', 'ollama', 'ollama_cloud', or 'zai'."
        )

    builder = PromptBuilder(ctx, be)
    client = Client(builder)

    logger = None
    try:
        logger = Logger(log=log, snapshot={
            "max_iterations": cfg.agent_max_iterations,
            "max_turn_tokens": cfg.agent_max_turn_tokens,
            "max_output_tokens": (max_output_tokens or cfg.agent_max_output_tokens),
            "context_window": context_window,
            "model": model,
            "provider": backend,
        })
        agent = Agent(
            context=ctx, registry=registry, builder=builder, client=client,
            logger=logger,
            max_iterations=cfg.agent_max_iterations,
            max_turn_tokens=cfg.agent_max_turn_tokens,
            max_output_tokens=(max_output_tokens or cfg.agent_max_output_tokens),
        )
        ctx.add_message("user", task)
        return agent.run()
    finally:
        if logger is not None:
            logger.close()
        # Flushes whatever spans are still sitting in the
        # BatchSpanProcessor's queue before the process exits -- without
        # this, a short-lived run can exit before the processor's next
        # scheduled export and silently drop every span it recorded.
        telemetry.shutdown()


# Interactive REPL: register tools once, then loop — reading tasks from
# stdin, running the agent, and printing replies — until the user types
# exit or sends EOF.
#
# Conversation history accumulates across every turn so the agent always
# sees the full transcript.
#
# Options are the same as boukensha.run, minus `task` (the user supplies
# tasks interactively). system/model/backend/api_key all default to config
# values.
def repl(
    *,
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
    tui=True,
):
    cfg = config()  # loads .env; populates os.environ
    telemetry.configure()
    if system is None:
        system = cfg.system_prompt
    if model is None:
        model = cfg.model
    if backend is None:
        backend = cfg.provider_type
    if api_key is None:
        api_key = {
            "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
            "openai": os.environ.get("OPENAI_API_KEY"),
            "gemini": os.environ.get("GEMINI_API_KEY"),
            "ollama_cloud": os.environ.get("OLLAMA_API_KEY"),
            "zai": os.environ.get("ZAI_API_KEY"),
        }.get(backend)

    context_window = Models.context_window(model)

    resolved_working_dir = (
        None if working_dir is False
        else (working_dir if working_dir is not None else os.getcwd())
    )

    ctx = Context(system=system, context_window=context_window, working_dir=resolved_working_dir,
                  compaction_threshold=cfg.agent_compaction_threshold)
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
    elif backend == "zai":
        be = Zai(api_key=api_key, model=model)
    else:
        raise ValueError(
            f"Unknown backend {backend!r}. Use 'anthropic', 'openai', "
            "'gemini', 'ollama', 'ollama_cloud', or 'zai'."
        )

    builder = PromptBuilder(ctx, be)
    client = Client(builder)

    logger = None
    try:
        logger = Logger(log=log, snapshot={
            "max_iterations": cfg.agent_max_iterations,
            "max_turn_tokens": cfg.agent_max_turn_tokens,
            "max_output_tokens": (max_output_tokens or cfg.agent_max_output_tokens),
            "context_window": context_window,
            "model": model,
            "provider": backend,
        })
        repl_instance = Repl(
            context=ctx, registry=registry, builder=builder, client=client,
            logger=logger,
            max_iterations=cfg.agent_max_iterations,
            max_turn_tokens=cfg.agent_max_turn_tokens,
            max_output_tokens=(max_output_tokens or cfg.agent_max_output_tokens),
            config_dir=cfg.dir, provider=backend, model=model,
            version=VERSION, api_key=api_key, mud=resolved_mud,
        )
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
        # Flushes whatever spans are still sitting in the
        # BatchSpanProcessor's queue before the process exits -- without
        # this, a short-lived run can exit before the processor's next
        # scheduled export and silently drop every span it recorded.
        telemetry.shutdown()


__all__ = [
    "VERSION",
    "Config",
    "Tool",
    "Message",
    "Context",
    "UnknownToolError",
    "UnsupportedModelError",
    "ApiError",
    "LoopError",
    "Registry",
    "PromptBuilder",
    "Logger",
    "Client",
    "Agent",
    "Base",
    "Anthropic",
    "Gemini",
    "OpenAI",
    "Ollama",
    "OllamaCloud",
    "Zai",
    "RunDSL",
    "Repl",
    "run",
    "repl",
    "config",
    "quiet",
    "loud",
    "is_quiet",
    "debug",
    "is_debug",
]
