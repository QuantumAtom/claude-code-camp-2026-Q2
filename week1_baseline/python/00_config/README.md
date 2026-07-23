# 00 · Configuration (Python)

Python port of [`week1_baseline/ruby/00_config`](../../ruby/00_config/README.md).
Same behavior, same on-disk `.boukensha/` config format — see that step's
README for the full design rationale. This doc covers the Python-specific
pieces: environment setup and the file layout.

## Environment setup

This repo uses a single shared virtual environment at the repo root for
all Python steps — not one per step. Dependencies, however, are declared
per step (this step's `requirements.txt` lives right here alongside the
code), matching the Ruby side's per-step `Gemfile`.

One-time venv creation, from the repo root:

```bash
cd <repo root>
python3 -m venv .venv
```

Then, for this step:

```bash
source .venv/bin/activate
pip install -r week1_baseline/python/00_config/requirements.txt
```

Later steps install their own `requirements.txt` into the same shared venv
the same way.

## Design Considerations

We want to use the standard library as much as possible avoiding external
packages. We add `PyYAML` (for `settings.yaml`) and `python-dotenv` (for
`.env`) to the root `requirements.txt` — the Python equivalents of the Ruby
side's `yaml` stdlib and `dotenv` gem.

## Code Changes

| File | Purpose |
|------|---------|
| `boukensha/config.py` | `Config` class |
| `boukensha/tasks/base.py` | abstract `tasks.Base` (provider/model + prompt resolution) |
| `boukensha/tasks/player.py` | concrete `tasks.Player` (the main loop) |
| `boukensha/__init__.py` | top-level package exports |
| `prompts/system.md` | default system prompt shipped with the package |
| `examples/example.py` | runnable smoke-test |

---

## Config directory resolution

Identical to the Ruby version. The class looks for a `.boukensha/` directory
in this order:

1. **`BOUKENSHA_DIR` env var** — set this to point at any directory you like.
2. **`~/.boukensha`** — the default location for a real install.

## Config directory structure

```
.boukensha/
  .env                 # stores credentials eg. LLMs APIs (never committed to repo)
  settings.yaml        # all non-secret settings
  prompts/
    <task>/
      system.md        # per-task override for the default system prompt (optional)
```

---

## Tasks

`tasks.Base` is an abstract stateless class. All behaviour is expressed as
class methods that accept a `settings` dict — no instances are created.
Concrete subclasses define `task_name()`. For now only `tasks.Player`
exists; future steps add per-turn ceilings (`max_iterations`,
`max_turn_tokens`, `max_output_tokens`, `compaction_threshold`) — these are
**not** read yet.

`Config.tasks()` returns the raw dict from `settings.yaml` under `tasks:`.
Pass a name to look up a specific task's settings dict, then pass it to the
stateless class:

```python
Player.provider(config.tasks("player"))
Player.system_prompt(
    config.tasks("player"),
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=Config.PROMPTS_DIR,
)
```

## System prompt resolution

Per task, `Player.system_prompt` is resolved in this order:

1. **`.boukensha/prompts/<task>/system.md`** — used when the task's
   `prompt_override.system` is `true` and the file exists.
2. **`prompts/system.md`** — the default system prompt shipped with the
   package.

## Configuration Schema

Same schema as the Ruby version:
- `tasks`: a map of task name → task config (provider, model, prompt_override).
- `tasks.<name>.prompt_override.system`: when `true`, the task's
  `.boukensha/prompts/<name>/system.md` overrides the default system prompt.
- `mud`: MUD connection information for the main player.

```yaml
tasks:
  player:
    provider: anthropic        # provider name (string)
    model: claude-haiku-4-5
    prompt_override:
      system: true
mud:
  host: localhost
  port: 4000
  username: dummy
  password: helloworld
```

## Run Example

```bash
./week1_baseline/bin/python/00_config
```

Expected output (values from your `.boukensha/`):

```
=== Boukensha Step 0: Configuration ===

Config dir:     /home/andrew/Sites/Claude-Code-Camp/.boukensha
Tasks:          player

-- player task --
Provider:       anthropic
Model:          claude-haiku-4-5
Prompt override?True
System prompt:  You are a MUD player assistant. Use the tools available to y...

MUD host:       localhost:4000
MUD user:       dummy

API key set?    True

<Boukensha::Config dir=/home/andrew/Sites/Claude-Code-Camp/.boukensha tasks=player>
```

(Booleans print as `True`/`False` — Python's native spelling — everything
else matches the Ruby output field-for-field.)

## Considerations

Carried over unchanged from the Ruby step — these are things we saw but
didn't fix, as that would break future steps:
- We have a default hard-coded prompt instead of a prompt scoped on tasks,
  ex. `prompts/<task>/system.md`
- Our settings file should take `.yml` and `.yaml`, but now is strictly
  `.yaml`
