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
from .errors import UnknownToolError, UnsupportedModelError, ApiError
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

__all__ = [
    "Config",
    "Player",
    "Tool",
    "Message",
    "Context",
    "UnknownToolError",
    "UnsupportedModelError",
    "ApiError",
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
    "config",
    "quiet",
    "loud",
    "is_quiet",
    "debug",
    "is_debug",
]
