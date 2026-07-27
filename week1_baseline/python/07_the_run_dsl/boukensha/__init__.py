import os

from .config import Config

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


from .tasks.player import Player
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
from .run_dsl import RunDSL


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
#   system:       System prompt. Defaults to the player task's system prompt.
#   model:        Model name. Defaults to tasks.player.model.
#   backend:      "anthropic" (default from settings), "openai", "gemini",
#                 "ollama", or "ollama_cloud".
#   api_key:      API key for the chosen backend. Defaults to the matching
#                 ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / OLLAMA_API_KEY
#                 env var (loaded from .boukensha/.env). Not needed for "ollama".
#   ollama_host:  Ollama base URL. Defaults to "http://localhost:11434".
#   log:          Optional JSONL path override. Defaults to .boukensha/sessions/<session-id>.jsonl.
#   max_output_tokens: Per-reply output cap. Defaults to tasks.player.max_output_tokens.
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


__all__ = [
    "Config",
    "Player",
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
    "RunDSL",
    "run",
    "config",
    "quiet",
    "loud",
    "is_quiet",
    "debug",
    "is_debug",
]
