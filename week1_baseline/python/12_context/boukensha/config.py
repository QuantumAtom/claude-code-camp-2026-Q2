import os
from pathlib import Path

import yaml
from dotenv import load_dotenv


class Config:
    # The .boukensha config directory is resolved in this order:
    #   1. BOUKENSHA_DIR environment variable (set before loading .env)
    #   2. .boukensha in the current working directory, if it exists
    #   3. ~/.boukensha  (default)
    DEFAULT_DIR = str(Path.home() / ".boukensha")

    # Default prompts shipped alongside this package.
    PROMPTS_DIR = str(Path(__file__).resolve().parent.parent / "prompts")

    def __init__(self):
        self.dir = self._resolve_dir()
        self._load_env()
        self.settings = self._load_settings()

    # ---------- provider ----------------------------------------------------

    @property
    def provider_type(self):
        return self.dig("tasks", "player", "provider") or "anthropic"

    @property
    def model(self):
        return self.dig("tasks", "player", "model") or "claude-haiku-4-5"

    # ---------- system prompt ------------------------------------------------

    @property
    def system_override(self):
        return self.dig("system", "override") is True

    # ---------- MUD connection --------------------------------------------

    @property
    def mud_host(self):
        return self.dig("mud", "host") or "localhost"

    @property
    def mud_port(self):
        return self.dig("mud", "port") or 4000

    @property
    def mud_username(self):
        return self.dig("mud", "username")

    @property
    def mud_password(self):
        return self.dig("mud", "password")

    # ---------- agent limits ----------------------------------------------
    # Static per-turn circuit breakers, read where the agent is constructed.
    # A value of 0 or None means "disabled" (no ceiling) -- useful for
    # debugging.

    @property
    def agent_max_iterations(self):
        v = self.dig("agent", "max_iterations")
        return 25 if v is None else int(v)

    @property
    def agent_max_output_tokens(self):
        v = self.dig("agent", "max_output_tokens")
        return 1024 if v is None else int(v)

    @property
    def agent_max_turn_tokens(self):
        v = self.dig("agent", "max_turn_tokens")
        return 60_000 if v is None else int(v)

    @property
    def agent_compaction_threshold(self):
        v = self.dig("agent", "compaction_threshold")
        return 0.85 if v is None else float(v)

    # ---------- low-level helpers -------------------------------------------

    # Fetch a nested key path from settings, e.g. dig("mud", "host")
    def dig(self, *keys):
        node = self.settings
        for key in keys:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
        return node

    def __str__(self):
        return f"#<Boukensha::Config dir={self.dir} provider={self.provider_type} model={self.model}>"

    __repr__ = __str__

    def _resolve_dir(self):
        # 1. Explicit override
        env_dir = os.environ.get("BOUKENSHA_DIR")
        if env_dir:
            return str(Path(env_dir).expanduser().resolve())

        # 2. .boukensha in the current working directory
        cwd_dir = Path.cwd() / ".boukensha"
        if cwd_dir.is_dir():
            return str(cwd_dir)

        # 3. ~/.boukensha default
        return str(Path(self.DEFAULT_DIR).expanduser().resolve())

    def _load_env(self):
        env_file = Path(self.dir) / ".env"
        if env_file.exists():
            load_dotenv(env_file)

    def _load_settings(self):
        settings_file = Path(self.dir) / "settings.yaml"
        if settings_file.exists():
            return yaml.safe_load(settings_file.read_text()) or {}
        return {}

    # Resolves the system prompt. When the player task opts into a prompt
    # override (tasks.player.prompt_override.system: true), the task-scoped
    # file prompts/player/system.md wins; otherwise the flat prompts/system.md
    # under the user's config dir is used. If neither exists, falls back to
    # the default prompt shipped in PROMPTS_DIR.
    @property
    def system_prompt(self):
        if self.dig("tasks", "player", "prompt_override", "system") is True:
            task_file = Path(self.dir) / "prompts" / "player" / "system.md"
            if task_file.exists():
                return task_file.read_text().strip()

        system_file = Path(self.dir) / "prompts" / "system.md"
        if system_file.exists():
            return system_file.read_text().strip()

        default_file = Path(self.PROMPTS_DIR) / "system.md"
        return default_file.read_text().strip() if default_file.exists() else None
