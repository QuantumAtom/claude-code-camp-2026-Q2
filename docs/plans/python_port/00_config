# Python Port Plan — 00_config

## Goal

Port `week1_baseline/ruby/00_config` to `week1_baseline/python/00_config`
(currently empty). Same behavior, same on-disk config format, new language.
No new features — this is a straight port of the existing step.

## Source of truth (what to port)

| Ruby file | Purpose |
|---|---|
| `week1_baseline/ruby/00_config/README.md` | Design spec for this step — schema, resolution order, everything below is derived from it |
| `week1_baseline/ruby/00_config/lib/boukensha.rb` | Top-level require |
| `week1_baseline/ruby/00_config/lib/boukensha/config.rb` | `Boukensha::Config` — dir resolution, `.env` loading, `settings.yaml` loading, `dig`/`tasks`/`mud_*` accessors |
| `week1_baseline/ruby/00_config/lib/boukensha/tasks/base.rb` | Abstract `Boukensha::Tasks::Base` — stateless class methods for provider/model/prompt resolution |
| `week1_baseline/ruby/00_config/lib/boukensha/tasks/player.rb` | Concrete `Boukensha::Tasks::Player`, defines `task_name = "player"` |
| `week1_baseline/ruby/00_config/prompts/system.md` | Default system prompt shipped with the library |
| `week1_baseline/ruby/00_config/examples/example.rb` | Runnable smoke test exercising the whole step |
| `week1_baseline/ruby/00_config/Gemfile` | Only dependency: `dotenv` |
| `week1_baseline/bin/00_config` | Bash wrapper that runs the Ruby example |

Also relevant for context (not ported, background only):
`docs/journal/1_week1.md` (goals for week 1) and `week1_baseline/ITERATIONS.md`
("Andrew decided on Ruby, but we are porting to Python").

## Hard requirement: on-disk compatibility

The Python `Config` must read the **same** `~/.boukensha/` directory —
same `settings.yaml` schema, same `.env`, same `BOUKENSHA_DIR` override — as
the Ruby version. A user should be able to point both implementations at one
shared config directory and get identical results. Nothing about the file
format changes in this port.

## Target structure

```
week1_baseline/python/00_config/
  README.md
  requirements.txt
  boukensha/
    __init__.py
    config.py
    tasks/
      __init__.py
      base.py
      player.py
  prompts/
    system.md
  examples/
    example.py
```

No `pyproject.toml` (per your call: plain `pip` + `requirements.txt`,
matching the lightweight feel of the Ruby `Gemfile`). `examples/example.py`
imports the local `boukensha` package by adding the step's own directory to
`sys.path` — the Python equivalent of Ruby's `require_relative
"../lib/boukensha"` — so no `pip install -e .` is needed.

## Python environment setup

**Revised**: `requirements.txt` lives per-step (here, alongside the code),
matching the Ruby `Gemfile`-per-step pattern — an earlier draft of this
plan put it at the repo root as one cumulative file, but that was reverted
per your follow-up. The venv itself is still shared at the repo root, just
the dependency manifests are per-step now.

- Venv path: `<repo root>/.venv` (i.e. `claude-code-camp-2026-Q2/.venv`,
  a sibling of `week1_baseline/`, `week2_capable/`, etc.) — created once
  with `python3 -m venv .venv` from the repo root.
- `requirements.txt` path: `week1_baseline/python/00_config/requirements.txt`
  (`PyYAML`, `python-dotenv`). Later steps/weeks each get their own
  `requirements.txt` next to their code, installed into the same shared
  venv as you reach them: `pip install -r <step>/requirements.txt`.
- Setup instructions (create the venv once, then `pip install -r
  week1_baseline/python/00_config/requirements.txt` for this step) go at
  the top of `week1_baseline/python/00_config/README.md`.
- `bin/python/00_config` sources `<repo root>/.venv/bin/activate` itself
  before running, so it works whether or not the caller's shell already has
  the venv active (see updated script below).
- `.gitignore` for `.venv/` goes at the **repo root** `.gitignore` (the venv
  itself is still shared/root-level, only the manifest moved).

## Ruby → Python file mapping

| Ruby | Python |
|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` |
| `lib/boukensha/config.rb` | `boukensha/config.py` |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` |
| `lib/boukensha/tasks/player.rb` | `boukensha/tasks/player.py` |
| `prompts/system.md` | `prompts/system.md` (copied verbatim) |
| `examples/example.rb` | `examples/example.py` |
| `Gemfile` (`dotenv`) | `requirements.txt` (`python-dotenv`, `PyYAML`), per-step like the Ruby `Gemfile` |
| `README.md` | `README.md` (same schema/behavior docs, Python run instructions) |
| `bin/00_config` | `bin/python/00_config` — both wrapper scripts now live under per-language subdirectories, `bin/ruby/00_config` and `bin/python/00_config` |

## Idiom translations

- `YAML.safe_load` → `yaml.safe_load` (PyYAML)
- `Dotenv.load(path)` → `dotenv.load_dotenv(path)`, only called `if
  Path(path).exists()`, same as the Ruby guard
- `Pathname#expand_path` → `pathlib.Path(...).expanduser().resolve()`
- `File.exist?` / `File.read` → `Path.exists()` / `Path.read_text()`
- `File.join(Dir.home, ".boukensha")` → `Path.home() / ".boukensha"`
- `File.expand_path("../../prompts", __dir__)` (in `config.rb`, resolving to
  the step's `prompts/` dir) → `Path(__file__).resolve().parent.parent /
  "prompts"` (in `config.py`, resolving to `python/00_config/prompts/`)
- `to_s` / `inspect` → `__str__` / `__repr__`
- **Dropped: Ruby's dual string/symbol key lookup.** `Config#dig` and
  `Tasks::Base.fetch` check both `node[key.to_s]` and `node[key.to_sym]`
  because Ruby call sites pass symbols (`config.tasks(:player)`) while
  `YAML.safe_load` returns string keys. Python has no symbol/string split —
  `yaml.safe_load` always returns `str` keys, and call sites will just pass
  strings (`config.tasks("player")`). `dig()` becomes a plain
  `functools.reduce`-style walk over `dict.get(key)`, no dual lookup needed.
- **Stateless class methods.** Ruby's `Tasks::Base` is instantiated never —
  every method is a class method taking a `settings` hash. Python mirrors
  this with `@classmethod` throughout `Tasks.Base`; `Tasks.Player` only
  overrides `task_name`. The Ruby "private class methods" (`class << self;
  private; end`) become leading-underscore classmethods (`_fetch`,
  `_read_user_prompt`, `_read_default_prompt`, `_read_file`) — Python has no
  real class-method privacy, underscore is the idiomatic signal.
- **Abstract method.** Ruby's `Tasks::Base.task_name` raises
  `NotImplementedError` if not overridden — no `abc`/metaclass machinery.
  Python does the same: `task_name()` on `Base` raises `NotImplementedError`
  directly, keeping it stdlib-only per the repo's stated preference for
  avoiding unnecessary abstraction.

## Config directory resolution & schema (unchanged from Ruby)

Resolution order:
1. `BOUKENSHA_DIR` env var
2. `~/.boukensha` (default)

Expected layout:
```
.boukensha/
  .env
  settings.yaml
  prompts/
    <task>/
      system.md
```

Schema (identical to the Ruby README):
```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
mud:
  host: localhost
  port: 4000
  username: dummy
  password: helloworld
```

System prompt resolution order (per task): `.boukensha/prompts/<task>/system.md`
(if `prompt_override.system` is `true` and the file exists), else the
library-shipped `prompts/system.md`.

## `bin/python/00_config`

`bin/` is now split into per-language subdirectories: `bin/ruby/00_config`
(the original script, moved) and `bin/python/00_config` (new). The Python
one activates the shared root venv itself (see "Python environment setup"
above) rather than assuming the caller's shell already has it active:
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/00_config"
python3 examples/example.py
```
Assumes the venv has already been created and this step's `requirements.txt`
installed into it per the README's setup instructions — matching the Ruby
side's assumption of `bundle install` having been run first.

The moved `bin/ruby/00_config` needed its relative path fixed too — it was
originally written assuming it lived directly in `bin/`
(`cd "$(dirname "$0")/../ruby/00_config"`), which broke once moved one
level deeper. Fixed to `cd "$(dirname "$0")/../../ruby/00_config"`.

## Expected output

Same shape as the Ruby example, run via `./week1_baseline/bin/python/00_config`:
```
=== Boukensha Step 0: Configuration ===

Config dir:     /home/you/.boukensha
Tasks:          player

-- player task --
Provider:       anthropic
Model:          claude-haiku-4-5
Prompt override?True
System prompt:  You are a MUD player assistant. Use the tools available to y...

MUD host:       localhost:4000
MUD user:       dummy

API key set?    True

<Boukensha::Config dir=/home/you/.boukensha tasks=player>
```
(Booleans print as `True`/`False`, Python's native spelling — everything
else matches the Ruby output field-for-field.)

## Carried-over known gaps (not fixed in this port, for parity)

Same two items the Ruby README already flags as deliberately unfixed:
- Default prompt is hardcoded rather than scoped per task
  (`prompts/<task>/system.md`).
- Settings file must be exactly `.yaml`, not `.yml`.

## Also add

- An entry in the **repo root** `.gitignore` for `.venv/`, `__pycache__/`,
  and `*.pyc` — the Ruby side gitignores `.bundle/`/`vendor/` per-step
  (`week1_baseline/.gitignore`), but since the venv itself is shared at the
  repo root rather than per-step, its ignore entry belongs there too.

## Decisions already made (from your answers)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` is split into per-language subdirectories: `bin/ruby/00_config`
  (moved, path fixed) and `bin/python/00_config` (new) — a layout change
  from the original "flat `bin/00_config_py` sibling" plan, made partway
  through implementation at your direction.
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite added in this step.
- Minimum Python version: 3.9+.
- Output parity: exact field-for-field match with the Ruby example where
  possible.
- `requirements.txt`: unpinned (`PyYAML`, `python-dotenv`), matching the
  Ruby `Gemfile`'s unpinned `dotenv`.
- One shared venv at the repo root (`<repo root>/.venv`) for all Python
  work across weeks/steps, not one per step — see "Python environment
  setup" above.
- `requirements.txt` is **per-step** (`week1_baseline/python/00_config/requirements.txt`),
  matching the Ruby `Gemfile`-per-step pattern — reverted from an earlier
  root-level-cumulative-file draft per your follow-up correction. Only the
  venv is shared/root-level; the manifests are not.
