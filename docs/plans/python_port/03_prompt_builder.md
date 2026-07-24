# Python Port Plan — 03_prompt_builder

## Goal

Port `week1_baseline/ruby/03_prompt_builder` to
`week1_baseline/python/03_prompt_builder`. Same behavior, same on-disk config
format, same API payload shapes per backend, new language. No new features —
this is a straight port of the existing step.

**Starting point (already partially done): `week1_baseline/python/03_prompt_builder`
already exists as a copy of `week1_baseline/python/02_the_registry`.**
`boukensha/config.py`, `boukensha/tool.py`, `boukensha/message.py`,
`boukensha/context.py`, `boukensha/registry.py`, `boukensha/errors.py`,
`boukensha/tasks/base.py`, `boukensha/tasks/player.py`, and
`requirements.txt` are already present and correct **except** for two small
gaps called out below (`errors.py` is missing `UnsupportedModelError`,
`config.py` is missing the `PROMPTS_DIR` constant). Ruby 03 doesn't touch
`Registry`/`Message`/`Tool`/`Context`/`Tasks::Base`/`Tasks::Player` at all —
same files, same content, confirmed identical to `ruby/02_the_registry`'s
versions. So this port is **an in-place edit of the copied tree**, not a
from-scratch build: add `prompt_builder.py` + `backends/` (net new — the
biggest piece of this step), fill the two gaps in `errors.py`/`config.py`,
then rewrite `__init__.py`, `examples/example.py`, and `README.md` (all three
are currently leftover Step‑2 content — `README.md` still says "02 · The Tool
Registry (Python)" and `examples/example.py` is still the registry dispatch
demo, not the prompt-builder demo).

`boukensha/tasks/__init__.py` is an empty file (0 bytes) — matches upstream,
leave it empty. Stray `boukensha/__pycache__/` and
`boukensha/tasks/__pycache__/` directories exist in the copy; `.gitignore`
already covers `__pycache__/`/`*.pyc` so these are harmless, but delete them
opportunistically while working in this tree. No nested recursive
`week1_baseline/` self-copy pollution was found here (unlike the 01/02
ports) — nothing to clean up on that front.

## Source of truth (what to port)

| Ruby file | Purpose | Status |
|---|---|---|
| `ruby/03_prompt_builder/README.md` | Design spec — PromptBuilder delegation, backend table, per-backend payload/message/tool-schema differences, considerations | Rewrite (new topic) |
| `ruby/03_prompt_builder/lib/boukensha.rb` | Top-level requires: config, tasks/player, tool, message, context, errors, registry, **prompt_builder, backends/{base,anthropic,gemini,ollama,ollama_cloud,openai}** | `__init__.py` needs the new exports |
| `ruby/03_prompt_builder/lib/boukensha/config.rb` | Adds `PROMPTS_DIR` constant (shipped default prompts dir) vs 02 | `config.py` missing this — **gap to fill** |
| `ruby/03_prompt_builder/lib/boukensha/errors.rb` | Adds `UnsupportedModelError < StandardError` vs 02 | `errors.py` missing this — **gap to fill** |
| `ruby/03_prompt_builder/lib/boukensha/tool.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/message.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/context.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/registry.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/tasks/base.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/tasks/player.rb` | Identical to 02 | Already correct, leave unchanged |
| `ruby/03_prompt_builder/lib/boukensha/prompt_builder.rb` | **NEW** — `PromptBuilder` delegates `to_messages`/`to_tools`/`to_api_payload`/`headers`/`url` to a backend | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/base.rb` | **NEW** — shared backend contract: `MODELS` registry, `validate_model!`, `model_info`, cost/context-window accessors, `estimate_cost` | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/anthropic.rb` | **NEW** — Anthropic Messages API serialization | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/gemini.rb` | **NEW** — Gemini `generateContent` serialization | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/openai.rb` | **NEW** — OpenAI Chat Completions serialization | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/ollama.rb` | **NEW** — local Ollama `/api/chat` serialization | New |
| `ruby/03_prompt_builder/lib/boukensha/backends/ollama_cloud.rb` | **NEW** — Ollama Cloud `/api/chat` serialization | New |
| `ruby/03_prompt_builder/prompts/system.md` | Default system prompt, shipped alongside the lib | **NEW** — missing entirely on the Python side |
| `ruby/03_prompt_builder/examples/example.rb` | Builds a backend from `player_settings`'s provider/model, wraps it in `PromptBuilder`, prints the full JSON API payload | Rewrite — Python's `example.py` is currently Step 2's registry-dispatch demo |
| `ruby/03_prompt_builder/Gemfile` | Only dependency: `dotenv` (no HTTP client — this step never calls the network) | `requirements.txt` already matches (`PyYAML`, `python-dotenv`), no change |
| `week1_baseline/bin/ruby/03_prompt_builder` | Bash wrapper that runs the Ruby example | Already exists, correct |
| `week1_baseline/bin/python/03_prompt_builder` | Bash wrapper for the Python example | **Exists but wrong** — currently a stray copy of `bin/python/02_the_registry` (wrong `cd` target: `python/02_the_registry`) — must be fixed |

Also relevant for context (not ported, background only):
`docs/plans/python_port/02_the_registry.md` (the plan template this doc
follows), `.boukensha/settings.yaml` at the repo root (currently configures
`tasks.player.provider: gemini`, `tasks.player.model: "gemini-3.1-flash-lite"`,
`prompt_override.system: true` — this is what `examples/example.py` will
actually resolve to at runtime).

## Concrete delta (this is the actual work)

Because the target is already a copy of Python 02, the port reduces to the
following edits inside `week1_baseline/python/03_prompt_builder/`:

**ADD (net-new files):**
- `boukensha/prompt_builder.py` — `PromptBuilder` class (see below)
- `boukensha/backends/__init__.py` — empty, makes `backends` a package
- `boukensha/backends/base.py` — `Base` backend contract
- `boukensha/backends/anthropic.py` — `Anthropic` backend
- `boukensha/backends/gemini.py` — `Gemini` backend
- `boukensha/backends/openai.py` — `OpenAI` backend
- `boukensha/backends/ollama.py` — `Ollama` backend
- `boukensha/backends/ollama_cloud.py` — `OllamaCloud` backend
- `prompts/system.md` — default system prompt, copied verbatim from Ruby (sibling of `boukensha/`, matching Ruby's `lib/`-sibling `prompts/` layout)

**FILL (small gaps in otherwise-correct copied files):**
- `boukensha/errors.py` — add `UnsupportedModelError(Exception): pass` alongside the existing `UnknownToolError`
- `boukensha/config.py` — add a `PROMPTS_DIR` class attribute pointing at the step's shipped `prompts/` directory (see "New class behavior" below)

**CHANGE (already present as 02's copy, must be rewritten for this step's topic):**
- `boukensha/__init__.py` — currently exports `Config, Player, Tool, Message,
  Context, UnknownToolError, Registry`; expand to also export
  `UnsupportedModelError, PromptBuilder`, and the six backend classes
  (`backends.Base`, `.Anthropic`, `.Gemini`, `.OpenAI`, `.Ollama`,
  `.OllamaCloud`), updating `__all__` to match.
- `examples/example.py` — currently Step 2's registry-dispatch demo
  (registers `move`/`shout`, dispatches them, catches `UnknownToolError`).
  Rewrite per Ruby's `examples/example.rb`: build `Context`/`Registry` (reuse
  the `look`/`move` tools + the three-message conversation from Ruby's
  example, not Step 2's `move`/`shout` pair — see "examples/example.py"
  below), resolve `provider`/`model` from `player_settings`, branch on
  `provider` to construct the matching backend (reading its API key from the
  matching env var, or no key for `ollama`), wrap in `PromptBuilder`, and
  print the full `to_api_payload` as pretty JSON.
- `README.md` — currently titled `# 02 · The Tool Registry (Python)`;
  rewrite for the prompt-builder topic (delegation diagram, `PromptBuilder`
  method table, per-backend payload/message/tool/role differences, cost
  model fields, considerations).

**LEAVE AS-IS (identical in Ruby too, already correct from the 02 copy):**
- `boukensha/tool.py`, `boukensha/message.py`, `boukensha/context.py`,
  `boukensha/registry.py`
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`,
  `boukensha/tasks/__init__.py`
- `requirements.txt` (`PyYAML`, `python-dotenv` — the prompt builder adds
  **no** new deps; it only serializes to dicts, it never performs HTTP
  requests)

**FIX outside the step dir:**
- `bin/python/03_prompt_builder` — currently `cd`s into
  `../../python/02_the_registry` and is missing its `set -e`/`ROOT`/`source`
  preamble entirely (it's a stray, incomplete copy). Rewrite to mirror
  `bin/python/02_the_registry`'s full pattern, pointed at
  `python/03_prompt_builder`. `bin/ruby/03_prompt_builder` already exists
  and is correct — no change needed there.

**CLEANUP (opportunistic, not required):**
- Delete `boukensha/__pycache__/` and `boukensha/tasks/__pycache__/` from
  the copied tree — already gitignored, but no reason to leave them lying
  around while editing this directory.

## Hard requirement: on-disk compatibility

Unchanged from the 00/01/02 ports. The Python `Config` must read the
**same** `~/.boukensha/` directory — same `settings.yaml` schema, same
`.env`, same `BOUKENSHA_DIR` override — as the Ruby version. New for this
step: `Config::PROMPTS_DIR` (shipped default prompts, distinct from the
user's override directory) must resolve to the **Python package's own**
`prompts/system.md`, not to Ruby's — the two implementations ship their own
copies of the same file, one per language tree, exactly as `config.py`
already lives separately from `config.rb`.

## Target structure

```
week1_baseline/python/03_prompt_builder/
  README.md
  requirements.txt
  prompts/
    system.md
  boukensha/
    __init__.py
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    prompt_builder.py
    tasks/
      __init__.py
      base.py
      player.py
    backends/
      __init__.py
      base.py
      anthropic.py
      gemini.py
      openai.py
      ollama.py
      ollama_cloud.py
  examples/
    example.py
```

No `pyproject.toml` (plain `pip` + `requirements.txt`, per the 00 decision).
`examples/example.py` keeps the same `sys.path` insert trick already present
in the copied file to import the local `boukensha` package — no change
needed there, only its `parents[N]` index if the file's depth changes (it
won't; the file stays at `examples/example.py`).

## Python environment setup

Same shared-venv / per-step-manifest model as 00/01/02 — nothing new here.

- Venv path: `<repo root>/.venv` (shared across all weeks/steps).
- `requirements.txt` path:
  `week1_baseline/python/03_prompt_builder/requirements.txt` (`PyYAML`,
  `python-dotenv` — unchanged from 02; the prompt builder adds **no** new
  dependencies since it only builds payload dicts, it never issues HTTP
  requests). Installed into the shared venv: `pip install -r
  week1_baseline/python/03_prompt_builder/requirements.txt`.
- Setup instructions go at the top of the step's `README.md`.
- `bin/python/03_prompt_builder` sources `<repo root>/.venv/bin/activate`
  itself before running (see below).

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Already copied; edit exports to add `UnsupportedModelError, PromptBuilder`, backend classes |
| `lib/boukensha/config.rb` | `boukensha/config.py` | Already copied; **add `PROMPTS_DIR`** |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | Already copied; **add `UnsupportedModelError`** |
| `lib/boukensha/tool.rb` | `boukensha/tool.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/message.rb` | `boukensha/message.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/context.rb` | `boukensha/context.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/registry.rb` | `boukensha/registry.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tasks/player.rb` | `boukensha/tasks/player.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/prompt_builder.rb` | `boukensha/prompt_builder.py` | NEW — plain delegator class |
| `lib/boukensha/backends/base.rb` | `boukensha/backends/base.py` | NEW — classmethods for model table + instance cost accessors |
| `lib/boukensha/backends/anthropic.rb` | `boukensha/backends/anthropic.py` | NEW |
| `lib/boukensha/backends/gemini.rb` | `boukensha/backends/gemini.py` | NEW |
| `lib/boukensha/backends/openai.rb` | `boukensha/backends/openai.py` | NEW |
| `lib/boukensha/backends/ollama.rb` | `boukensha/backends/ollama.py` | NEW |
| `lib/boukensha/backends/ollama_cloud.rb` | `boukensha/backends/ollama_cloud.py` | NEW |
| `prompts/system.md` | `prompts/system.md` | NEW — copy verbatim |
| `examples/example.rb` | `examples/example.py` | Rewrite for the prompt-builder demo |
| `Gemfile` (`dotenv`) | `requirements.txt` (`PyYAML`, `python-dotenv`) | Unchanged |
| `README.md` | `README.md` | Port delegation diagram, backend table, payload/role/tool-schema differences, considerations |
| `bin/ruby/03_prompt_builder` | `bin/python/03_prompt_builder` | Fix the stray copy to mirror `bin/python/02_the_registry`, pointed at `03_prompt_builder` |

## New class behavior (the actual porting work)

### `UnsupportedModelError` (`errors.rb` → `errors.py`)

Ruby adds one line to the existing `errors.rb`:
`class UnsupportedModelError < StandardError; end`. Same bare-exception
shape as `UnknownToolError`.

```python
class UnknownToolError(Exception):
    pass


class UnsupportedModelError(Exception):
    pass
```

### `Config::PROMPTS_DIR` (`config.rb` → `config.py`)

Ruby: `PROMPTS_DIR = File.expand_path("../../prompts", __dir__).freeze`,
evaluated from `lib/boukensha/config.rb`'s own directory
(`lib/boukensha/`), landing two levels up at `<gem root>/prompts` — i.e. the
`prompts/` directory that sits as a **sibling of `lib/`** at the project
root, shipped with the library itself (distinct from the user's
`~/.boukensha/prompts/` override directory, which is `user_prompts_dir`).

Python equivalent, resolved from `config.py`'s own file location the same
way (`boukensha/config.py` → up one level to the package root
`03_prompt_builder/`, landing at `03_prompt_builder/prompts`, the sibling of
`boukensha/`):

```python
class Config:
    DEFAULT_DIR = str(Path.home() / ".boukensha")
    PROMPTS_DIR = str(Path(__file__).resolve().parent.parent / "prompts")
```

This is a **class attribute**, computed once at import time from
`__file__`, matching Ruby's constant (evaluated once when the file loads).
Do not make it a per-instance `@property` — Ruby's `PROMPTS_DIR` is a
class-level `Config::PROMPTS_DIR`, referenced directly in
`examples/example.rb` as `Boukensha::Config::PROMPTS_DIR` without
instantiating a `Config`, and `examples/example.py` should mirror that by
referencing `Config.PROMPTS_DIR` the same way.

### `PromptBuilder` (`prompt_builder.rb` → `prompt_builder.py`)

Ruby API — a thin delegator, five methods, all forwarding to `@backend`:
- `initialize(context, backend)` — stores both
- `to_messages` → `@backend.to_messages(@context.messages)`
- `to_tools` → `@backend.to_tools(@context.tools)`
- `to_api_payload(max_output_tokens: 1024)` →
  `@backend.to_payload(@context, max_output_tokens: max_output_tokens)`
- `headers` → `@backend.headers`
- `url` → `@backend.url`

```python
class PromptBuilder:
    def __init__(self, context, backend):
        self.context = context
        self.backend = backend

    def to_messages(self):
        return self.backend.to_messages(self.context.messages)

    def to_tools(self):
        return self.backend.to_tools(self.context.tools)

    def to_api_payload(self, max_output_tokens=1024):
        return self.backend.to_payload(self.context, max_output_tokens=max_output_tokens)

    def headers(self):
        return self.backend.headers()

    def url(self):
        return self.backend.url()
```

Note `headers`/`url` become **methods** (`self.backend.headers()`), not
properties, for consistency with how the backends themselves are ported
below (Ruby's zero-arg `def headers` / `def url` are ordinary methods too,
just called without parens per Ruby style — nothing here is an
attr-derived value that changes per access, so either `@property` or a
plain method is defensible; this plan picks plain methods to keep call
sites explicit, e.g. `builder.headers()`, matching `to_messages()`/`to_tools()`).

### `Backends::Base` (`backends/base.rb` → `backends/base.py`)

Ruby API, all class-level except the cost/window accessors:
- `self.models` → `const_get(:MODELS)`, raising `NotImplementedError` if the
  subclass never defined a `MODELS` hash
- `self.model_info(model)` → `models[model.to_s]`
- `self.validate_model!(model)` → looks up `model_info`; raises
  `UnsupportedModelError` (with the sorted list of supported models in the
  message) if the model string isn't a key in `MODELS`; returns the
  (stringified) model on success
- instance `configure_model(model)` (private) — called by each subclass's
  `initialize`; sets `@model` via `validate_model!` and caches `@model_info`
- instance accessors: `model_info`, `context_window`, `input_token_cost_per_million`,
  `output_token_cost_per_million`, `usage_unit`, `usage_level` (nil-safe —
  `model_info[:usage_level]`, no `.fetch`), and
  `estimate_cost(input_tokens:, output_tokens:)` — returns `nil` if either
  cost-per-million value is `nil` (e.g. Ollama Cloud), otherwise
  `(input_tokens * input_cost + output_tokens * output_cost) / 1_000_000.0`

Python port — `MODELS` becomes a class attribute (dict) each subclass
defines; `validate_model!`/`configure_model` become classmethods/methods
using `getattr`/`hasattr` instead of `const_get`/`rescue NameError`:

```python
from ..errors import UnsupportedModelError


class Base:
    MODELS = None

    @classmethod
    def models(cls):
        if cls.MODELS is None:
            raise NotImplementedError(f"{cls.__name__} must define MODELS")
        return cls.MODELS

    @classmethod
    def model_info_for(cls, model):
        return cls.models().get(str(model))

    @classmethod
    def validate_model(cls, model):
        model = str(model)
        if cls.model_info_for(model) is not None:
            return model
        supported = ", ".join(sorted(cls.models().keys()))
        raise UnsupportedModelError(
            f"{cls.__name__} does not support model {model!r}. Supported models: {supported}"
        )

    def configure_model(self, model):
        self.model = self.validate_model(model)
        self.model_info = self.model_info_for(self.model)

    @property
    def context_window(self):
        return self.model_info["context_window"]

    @property
    def input_token_cost_per_million(self):
        return self.model_info["cost_per_million"]["input"]

    @property
    def output_token_cost_per_million(self):
        return self.model_info["cost_per_million"]["output"]

    @property
    def usage_unit(self):
        return self.model_info["usage_unit"]

    @property
    def usage_level(self):
        return self.model_info.get("usage_level")

    def estimate_cost(self, input_tokens, output_tokens):
        in_cost = self.input_token_cost_per_million
        out_cost = self.output_token_cost_per_million
        if in_cost is None or out_cost is None:
            return None
        return (input_tokens * in_cost + output_tokens * out_cost) / 1_000_000.0
```

Note: Ruby names the class-level lookup `self.model_info(model)` and the
*instance* method `model_info` (no args, returns `@model_info`) — two
same-named methods distinguished only by class vs. instance scope, which
Ruby permits freely. Python has no such overload-by-receiver; this plan
renames the **class** method to `model_info_for(model)` and keeps
`model_info` as the **instance attribute** (set directly in
`configure_model`, not wrapped in a property) to avoid a name collision
without inventing an unrelated name.

`usage_unit`/`context_window`/token-cost values use `["cost_per_million"]["input"]`
direct indexing (mirroring Ruby's `.fetch`, which raises loudly on a missing
key) for fields that must always be present per model entry, but
`.get("usage_level")` (mirroring Ruby's bare `[:usage_level]`, which
silently returns `nil`) for the one genuinely optional field (only
`OllamaCloud` models set it).

### Each concrete backend (`backends/{anthropic,gemini,openai,ollama,ollama_cloud}.rb`)

All five follow the same shape: a `MODELS` class dict (values, pricing, and
`usage_unit`/`usage_level` copied **verbatim** from the Ruby source — these
are tutorial-static prices as of 2026-06-16 per the Ruby README, not to be
"corrected" or re-researched during the port), an `__init__` that stores
credentials and calls `configure_model(model)`, and four methods:
`to_messages`, `to_tools`, `to_payload`, `headers`, `url`.

Key per-backend differences to preserve exactly (all confirmed by reading
each `.rb` file):

- **Anthropic** (`BASE_URL = "https://api.anthropic.com/v1/messages"`):
  `to_messages(messages)` takes **one** arg (no `system`); tool-result
  messages become `{"role": "user", "content": [{"type": "tool_result",
  "tool_use_id": ..., "content": ...}]}`, everything else is
  `{"role": str(role), "content": content}`. `to_tools` uses
  `input_schema` wrapping. `to_payload` puts `system` as a **top-level**
  key alongside `messages`. Headers use `x-api-key` +
  `anthropic-version: 2023-06-01`.
- **Gemini** (`BASE_URL = ".../v1beta/models"`, `url` appends
  `/{model}:generateContent`): `to_messages` renames `:assistant` → `"model"`
  and wraps everything in `{"role": ..., "parts": [{"text": ...}]}`;
  tool-result becomes a `functionResponse` part. `to_tools` returns `[]` for
  an empty tool dict (**not** `[{"functionDeclarations": []}]` — Ruby's
  `return [] if tools.empty?` short-circuits before building the wrapper),
  otherwise one dict with a `functionDeclarations` array. `to_payload` uses
  `systemInstruction: {parts: [{text: ...}]}`, `contents` (not `messages`),
  and `generationConfig: {maxOutputTokens: ...}`. Header:
  `x-goog-api-key`.
- **OpenAI** (`BASE_URL = ".../v1/chat/completions"`): `to_messages(system,
  messages)` takes **two** args — prepends a `{"role": "system", "content":
  system}` message, tool-result becomes `{"role": "tool", "tool_call_id":
  ..., "content": ...}`. `to_tools` wraps in `{"type": "function",
  "function": {...}}`. `to_payload` uses `max_completion_tokens` (not
  `max_tokens`). Header: `Authorization: Bearer {api_key}`.
- **Ollama** (no `BASE_URL` constant — `host` is instance state, default
  `"http://localhost:11434"`; **no API key** — `initialize(host:
  "http://localhost:11434", model:)`): same two-arg `to_messages(system,
  messages)` shape as OpenAI/OllamaCloud but tool-result uses `"tool_name"`
  (not `"tool_call_id"`). `to_payload` includes `"stream": false` and has
  **no `max_output_tokens` field at all** (Ollama's payload ignores the
  `max_output_tokens:` kwarg entirely — confirm this is preserved, it's easy
  to "fix" by accident during a port). `url` is `"{host}/api/chat"`. Header
  is just `Content-Type` (no auth).
- **OllamaCloud** (`BASE_URL = "https://ollama.com"`, **does** take an
  `api_key:`): identical body shape to `Ollama` (`stream: false`, no
  `max_output_tokens`, `"tool_name"` field) but `url` is
  `"{BASE_URL}/api/chat"` and header adds `Authorization: Bearer {api_key}`.
  Its `MODELS` entries have `cost_per_million: {input: nil, output: nil}`
  (public pricing is plan-based, not token-based) plus a `usage_level`
  field (`:medium`/`:high`) that the other backends' entries don't set, and
  one entry (`minimax-m3:cloud`) additionally carries an
  `advertised_context_window` key alongside `context_window` — carry that
  key through unchanged even though nothing currently reads it (parity with
  Ruby's data, not dead-code cleanup).

Python constructor signatures mirror Ruby's keyword-arg style using
keyword-only parameters (`*`) so call sites read the same:

```python
# anthropic.py / openai.py / ollama_cloud.py
def __init__(self, *, api_key, model):
    self.api_key = api_key
    self.configure_model(model)

# ollama.py
def __init__(self, *, model, host="http://localhost:11434"):
    self.host = host
    self.configure_model(model)
```

`to_tools`'s `required` list — Ruby: `tool.parameters.keys.map(&:to_s)` →
Python: `list(tool.parameters.keys())` (parameter dict keys are already
Python `str`, no per-element `.to_s` conversion needed, same idiom already
established for `Tool.__str__`'s `params=` rendering).

### `prompts/system.md`

Copy Ruby's file verbatim (one line):
```
You are a MUD player assistant. Use the tools available to you to help the player explore, fight, and interact with the world.
```

## Idiom translations

Config/Tool/Message/Context/Registry/Tasks idioms are inherited unchanged
from the 00/01/02 ports. New for step 03:

- Ruby `const_get(:MODELS) rescue NameError -> raise NotImplementedError` →
  Python a `MODELS = None` class attribute checked with `if cls.MODELS is
  None: raise NotImplementedError(...)` (no exception-driven control flow
  needed since Python doesn't have Ruby's `const_get` miss-as-exception
  idiom for a plain class attribute lookup).
- Ruby `model.to_s` (coercing a symbol/string argument) → Python `str(model)`
  (arguments are already strings in idiomatic Python call sites, but the
  coercion is kept for parity and defensiveness, matching how `Registry.tool`
  already does `str(name)`).
- Ruby class method vs. instance method sharing the name `model_info` →
  Python renames the **class** lookup to `model_info_for(model)` to avoid
  colliding with the **instance** attribute `model_info` (see "New class
  behavior" above for why).
- Ruby `attr_reader :model` (class exposes `@model` set via `configure_model`)
  → Python: `configure_model` sets `self.model`/`self.model_info` directly
  as plain instance attributes (no need for an explicit property when a
  plain assigned attribute already reads the same way).
- Ruby's private `configure_model` (via `private` keyword, section-scoped) →
  Python: a regular public method (`self.configure_model(model)`); Python
  has no enforced-private method visibility, and a single leading
  underscore isn't warranted here since every subclass's `__init__` must
  call it directly, exactly as in Ruby.
- Ruby `BASE_URL` per-backend constant → Python per-backend `BASE_URL` class
  attribute (string), same casing.
- Ruby string interpolation building the `f"..."`-equivalent error/URL
  strings (`"#{name} does not support..."`, `"#{@host}/api/chat"`) → Python
  f-strings, same content.
- Ruby `tools.values.map { |tool| {...} }` → Python
  `[{...} for tool in tools.values()]` (or an explicit loop — either is
  fine, match existing style already used elsewhere in the ported files;
  the plan snippets above use list comprehensions where Ruby uses `.map`).
- Ruby `messages.map do |msg| case msg.role when :tool_result ... else ... end end`
  → Python `[... for msg in messages]` with an `if msg.role == "tool_result":
  ... else: ...` branch inside (message roles are already plain Python
  strings per `message.py`, not an enum — `msg.role == "tool_result"`, not
  `msg.role is Role.TOOL_RESULT`).
- Ruby `return [] if tools.empty?` early-exit (Gemini's `to_tools`) →
  Python `if not tools: return []` at the top of the method — **must** be
  preserved exactly; dropping it changes Gemini's empty-tools payload shape.

## `examples/example.py`

Mirror the currently-copied `example.py`'s existing scaffolding (`sys.path`
insert, `BOUKENSHA_DIR` setdefault, `Config()`), then follow Ruby's
`examples/example.rb` structure exactly (this is a full rewrite of the
Step‑2 registry demo, not an incremental edit):

1. `player_settings = config.tasks("player")`
2. `system_prompt = Player.system_prompt(player_settings,
   user_prompts_dir=config.user_prompts_dir,
   default_prompts_dir=Config.PROMPTS_DIR)` — note the **added**
   `default_prompts_dir` argument vs. Step 2's call, now that
   `Config.PROMPTS_DIR` exists.
3. `ctx = Context(task=Player, system=system_prompt)`; `registry =
   Registry(ctx)`.
4. Register two tools through the registry, matching Ruby's example
   exactly (**not** Step 2's `move`/`shout` pair):
   - `"look"`, description `"Look around the current room for details"`,
     `parameters={}`, block returns the fixed string `"A damp stone
     corridor stretches north. Torches flicker on the walls."`
   - `"move"`, description `"Move the player in a direction (north, south,
     east, west, up, down)"`, `parameters={"direction": {"type": "string",
     "description": "The direction to move"}}` (the **richer** three-key
     schema from Ruby 03's example, not Step 2's leaner two-key version —
     confirm against `ruby/03_prompt_builder/examples/example.rb`, not
     `ruby/02_the_registry/examples/example.rb`), block returns
     `f"You move {direction} into a torch-lit corridor."`
5. Seed the conversation directly on `ctx` (not through dispatch — Ruby
   calls `ctx.add_message` three times, simulating a turn that already
   happened):
   - `ctx.add_message("user", "I just arrived in the dungeon. What's around me, and can you move north?")`
   - `ctx.add_message("assistant", "Let me take a look around first.")`
   - `ctx.add_message("tool_result", "A damp stone corridor stretches north. Torches flicker on the walls.", tool_use_id="toolu_01X")`
6. Print header `=== BOUKENSHA Step 3: Prompt Builder ===`.
7. `provider = Player.provider(player_settings)`; `model =
   Player.model(player_settings)`.
8. Branch on `provider` to construct the matching backend, reading API keys
   from `os.environ[...]` (raising `KeyError` on a missing var, mirroring
   Ruby's `ENV.fetch` — do **not** soften this to `.get(...)` with a
   default, a missing key should fail loudly exactly as it does in Ruby):
   - `"anthropic"` → `Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model=model)`
   - `"ollama"` → `Ollama(model=model)` (no key)
   - `"ollama_cloud"` → `OllamaCloud(api_key=os.environ["OLLAMA_API_KEY"], model=model)`
   - `"openai"` → `OpenAI(api_key=os.environ["OPENAI_API_KEY"], model=model)`
   - `"gemini"` → `Gemini(api_key=os.environ["GEMINI_API_KEY"], model=model)`
   - else → `raise ValueError(f"Unsupported provider for player task: {provider}")`
9. `builder = PromptBuilder(ctx, backend)`.
10. Print `Config: {config}`, `Provider: {provider}`, `Model: {model}`, then
    `json.dumps(builder.to_api_payload(), indent=2)` (Python's
    `json.dumps(..., indent=2)` is the direct equivalent of Ruby's
    `JSON.pretty_generate`).

Given the repo's live `.boukensha/settings.yaml` sets
`tasks.player.provider: gemini`, running this example end-to-end will
construct a `Gemini` backend and require `GEMINI_API_KEY` in the
environment/`.env` — that's expected, matches Ruby's behavior exactly (it
never actually calls the network in this step, but backend construction
still demands the key up front, same as Ruby's `ENV.fetch`).

## `bin/python/03_prompt_builder`

Fix the existing stray file (currently a broken/incomplete copy of
`bin/python/02_the_registry` pointing at the wrong directory) to mirror the
established pattern exactly:
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/03_prompt_builder"
python3 examples/example.py
```
Assumes the venv exists and this step's `requirements.txt` is installed (per
the README). `bin/ruby/03_prompt_builder` already exists with the correct
path — no change needed there.

## Expected output

Run via `./week1_baseline/bin/python/03_prompt_builder`. Should match the
Ruby example (`bundle exec ruby examples/example.rb` under
`week1_baseline/ruby/03_prompt_builder`) field-for-field, modulo the
provider currently configured in `.boukensha/settings.yaml` (`gemini`).
Shape (exact JSON body depends on live provider/model/prompt-override
config, not hardcoded here):
```
=== BOUKENSHA Step 3: Prompt Builder ===

Config: #<Boukensha::Config dir=/home/you/.boukensha tasks=player>
Provider: gemini
Model: gemini-3.1-flash-lite
{
  "systemInstruction": { "parts": [{ "text": "..." }] },
  "contents": [ ... ],
  "tools": [ { "functionDeclarations": [ ... ] } ],
  "generationConfig": { "maxOutputTokens": 1024 }
}
```
If `GEMINI_API_KEY` isn't set in the environment or `~/.boukensha/.env`,
both the Ruby and Python versions fail identically at backend construction
(`ENV.fetch` / `os.environ[...]` both raise) — this is expected, not a
port bug, and should not be "fixed" by falling back to a default key.

## Carried-over known gaps (not fixed in this port, for parity)

Same items the Ruby README already flags as deliberately unfixed or
explicitly out of scope for this step:
- `PromptBuilder`/backends only **serialize** payloads; nothing in this step
  performs an actual HTTP request. `headers()`/`url()` exist so a future
  step can POST with them, but that wiring doesn't happen here.
- Settings file must be exactly `.yaml`, not `.yml` (carried from 00).
- Pricing/model tables (`MODELS` per backend) are static tutorial data as of
  2026-06-16 per the Ruby README — do not "update" them to reflect real
  current pricing during this port; that would create a Ruby/Python
  divergence, not fix one.
- No real agent decision loop yet — `example.py` still hand-constructs the
  conversation and hand-picks the backend; an agent choosing what to say or
  which tool to call is a later step.

## Decisions already made (from the 00/01/02 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories: `bin/ruby/03_prompt_builder`
  (exists, correct) and `bin/python/03_prompt_builder` (exists, needs
  fixing per above).
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+.
- Output parity: exact field-for-field match with the Ruby example where
  possible (JSON payload shape must match exactly per backend, since that's
  the entire point of this step).
- `requirements.txt`: per-step, unpinned — unchanged from 02 (`PyYAML`,
  `python-dotenv`); this step adds no HTTP client dependency because it
  never performs a request.
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: the target is already copied from Python
  02; leave `tool.py`, `message.py`, `context.py`, `registry.py`,
  `tasks/base.py`, `tasks/player.py`, `tasks/__init__.py` unchanged; fill
  two small gaps in `errors.py`/`config.py`; add
  `prompt_builder.py`/`backends/*`; rewrite `__init__.py`,
  `examples/example.py`, `README.md`.
- README vs. actual Ruby implementation: follow the executable code, not
  any aspirational text in the Ruby README, if the two ever disagree — same
  call made for the 01/02 ports (no such discrepancy was found in Ruby 03's
  README while researching this plan, but the rule still applies if one
  turns up during implementation).
- Struct representation: `@dataclass` for `Tool`/`Message` (unchanged, not
  touched by this step); `PromptBuilder`, `Registry`, and every `Backends.*`
  class are plain classes, matching their Ruby counterparts (none of them
  are data Structs — they're service/strategy objects).
- Class-level model tables (`MODELS`) are plain class attributes (dicts),
  not `Enum` or any other Python-specific data-modeling upgrade — matches
  Ruby's `MODELS = {...}.freeze` constant as directly as possible.

## Remaining cosmetic decisions

- **`headers()`/`url()` as methods vs. properties.** This plan calls them
  as zero-arg methods (`builder.headers()`) for consistency with
  `to_messages()`/`to_tools()`, rather than `@property`. Revisit only if a
  later step's calling convention makes properties clearly preferable.
- **`model_info_for` naming.** Ruby overloads `model_info` as both a class
  method and an instance method; Python can't do that cleanly, so the class
  method is renamed. If this reads awkwardly once written, an alternative
  is `models_lookup`/`lookup_model`, but `model_info_for(model)` most
  directly mirrors the original name's intent.
- **Keyword-only backend constructors (`*, api_key, model`).** Chosen to
  mirror Ruby's `initialize(api_key:, model:)` keyword-argument call sites
  as closely as Python syntax allows. Revisit only if `example.py`'s call
  sites end up reading better as plain positional args (unlikely, since
  Ruby's own example calls them with keywords too).
