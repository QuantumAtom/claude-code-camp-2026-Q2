# Python Port Plan — 01_struct_skeleton

## Goal

Port `week1_baseline/ruby/01_struct_skeleton` to
`week1_baseline/python/01_struct_skeleton`. Same behavior, same on-disk config
format, new language. No new features — this is a straight port of the
existing step.

**Starting point (already done): `week1_baseline/python/01_struct_skeleton`
already exists as a byte-for-byte copy of the already-ported Python
`00_config`.** All eight shared files (`README.md`, `requirements.txt`,
`boukensha/__init__.py`, `boukensha/config.py`, `boukensha/tasks/base.py`,
`boukensha/tasks/player.py`, `examples/example.py`, `prompts/system.md`) are
identical to 00. So this port is **an in-place edit of that copied tree**, not
a from-scratch build.

Structurally, **step 01 is step 00 plus three new data-structure files, minus
the default-prompt machinery.** The `Config`/`Tasks` code is already present
(copied from Python `00_config`); the only *new* content to author is `Tool`,
`Message`, and `Context`, plus small edits to `config.py`, `__init__.py`,
`example.py`, and `README.md`, and deletion of `prompts/`.

## Source of truth (what to port)

| Ruby file | Purpose | Δ vs `00_config` |
|---|---|---|
| `week1_baseline/ruby/01_struct_skeleton/README.md` | Design spec — documents the 3 data structures (Tool, Message, Context) with field tables + `to_s` examples | Rewritten (new topic) |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha.rb` | Top-level requires: config, tasks/player, tool, message, context | +3 requires |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/config.rb` | `Boukensha::Config` — dir resolution, `.env`, `settings.yaml`, `dig`/`tasks`/`mud_*` | **Dropped `PROMPTS_DIR`** constant (91 vs 94 lines) |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tasks/base.rb` | Abstract `Tasks::Base` — stateless provider/model/prompt classmethods | **Identical** to 00 |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tasks/player.rb` | Concrete `Tasks::Player`, `task_name = "player"` | **Identical** to 00 |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/tool.rb` | **NEW** — `Tool` Struct(name, description, parameters, block) + `to_s` | New |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/message.rb` | **NEW** — `Message` Struct(role, content, tool_use_id) + `to_s` | New |
| `week1_baseline/ruby/01_struct_skeleton/lib/boukensha/context.rb` | **NEW** — `Context` class: task/system/messages/tools + register/add helpers | New |
| `week1_baseline/ruby/01_struct_skeleton/examples/example.rb` | Runnable smoke test building Config → system prompt → Context → Tool → messages | Rewritten |
| `week1_baseline/ruby/01_struct_skeleton/Gemfile` | Only dependency: `dotenv` | Identical |
| `week1_baseline/bin/ruby/01_struct_skeleton` | Bash wrapper that runs the Ruby example | Sibling of 00 |

Also relevant for context (not ported, background only): the already-shipped
Python `week1_baseline/python/00_config/` (the source of the current copy),
`docs/plans/python_port/00_config` (the plan template this doc follows), and
`week1_baseline/ITERATIONS.md`.

Note: Ruby step 01 has **no `prompts/` directory** — it deleted the
`PROMPTS_DIR` machinery that `00_config` had.

## Concrete delta (this is the actual work)

Because the target is already a copy of Python 00, the port reduces to the
following edits inside `week1_baseline/python/01_struct_skeleton/`:

**ADD (net-new files):**
- `boukensha/tool.py` — `@dataclass Tool` (see below)
- `boukensha/message.py` — `@dataclass Message` (see below)
- `boukensha/context.py` — plain `Context` class (see below)

**CHANGE (already present as 00's copy, must be edited):**
- `boukensha/config.py` — delete the `PROMPTS_DIR` block. In the current copy
  that is **lines 14–16** (comment + `PROMPTS_DIR = ...` + blank line), to
  match Ruby 01.
- `boukensha/__init__.py` — currently exports only `Config, Player`; expand to
  export `Config, Player, Tool, Message, Context` (and update `__all__`).
- `examples/example.py` — currently 00's "Step 0: Configuration" demo, which
  calls `Player.system_prompt(..., default_prompts_dir=Config.PROMPTS_DIR)`
  (~line 29). Rewrite as the struct-skeleton demo and **remove the
  `default_prompts_dir=Config.PROMPTS_DIR` argument** (it breaks once
  `PROMPTS_DIR` is gone).
- `README.md` — currently titled `# 00 · Configuration (Python)`; rewrite for
  the struct-skeleton topic (field tables + examples).

**DELETE:**
- `prompts/` (and `prompts/system.md`) — Ruby 01 ships none.

**LEAVE AS-IS (identical in Ruby too, already correct from the 00 copy):**
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`,
  `boukensha/tasks/__init__.py`
- `requirements.txt` (`PyYAML`, `python-dotenv` — the new structs add no deps)

**ADD outside the step dir:**
- `bin/python/01_struct_skeleton` (mirror `bin/python/00_config`; see below).
  `bin/ruby/01_struct_skeleton` already exists and is correct.

## Cleanup required first: recursive-copy pollution

The copy that produced Python 01 (and Python 00) contains a **runaway
recursive self-copy**: `week1_baseline/python/01_struct_skeleton/week1_baseline/
python/...` nested ~182 levels deep (≈1450 dirs, ≈2500 files, hundreds of
`__pycache__/` dirs and `.pyc` files). It is untracked and **not** gitignored.

Before/while porting, **delete these nested `week1_baseline/` trees** from both
`week1_baseline/python/01_struct_skeleton/` and
`week1_baseline/python/00_config/`, and remove stray `__pycache__/` / `*.pyc`.
`.gitignore` already ignores `.venv/`, `__pycache__/`, and `*.pyc`; the nested
`week1_baseline/` tree itself is **not** ignored, so it must be physically
deleted. Do not commit the nested trees.

## Hard requirement: on-disk compatibility

Unchanged from the 00 port. The Python `Config` must read the **same**
`~/.boukensha/` directory — same `settings.yaml` schema, same `.env`, same
`BOUKENSHA_DIR` override, same `prompts/<task>/system.md` overrides — as the
Ruby version. A user should point both implementations at one shared config
directory and get identical results.

## Target structure

```
week1_baseline/python/01_struct_skeleton/
  README.md
  requirements.txt
  boukensha/
    __init__.py
    config.py
    tool.py
    message.py
    context.py
    tasks/
      __init__.py
      base.py
      player.py
  examples/
    example.py
```

**No `prompts/` directory** — mirroring Ruby step 01 (delete the copied
`prompts/`).
No `pyproject.toml` (plain `pip` + `requirements.txt`, per the 00 decision).
`examples/example.py` imports the local `boukensha` package by adding the
step's own directory to `sys.path` — same trick as `00_config`'s
`example.py` — so no `pip install -e .` is needed.

## Python environment setup

Same shared-venv / per-step-manifest model as 00 — nothing new here.

- Venv path: `<repo root>/.venv` (shared across all weeks/steps), created once
  with `python3 -m venv .venv` from the repo root.
- `requirements.txt` path:
  `week1_baseline/python/01_struct_skeleton/requirements.txt`
  (`PyYAML`, `python-dotenv` — the new structs add **no** dependencies;
  dataclasses & typing are stdlib). Installed into the shared venv:
  `pip install -r week1_baseline/python/01_struct_skeleton/requirements.txt`.
- Setup instructions go at the top of the step's `README.md`.
- `bin/python/01_struct_skeleton` sources `<repo root>/.venv/bin/activate`
  itself before running (see below).
- `.gitignore` for `.venv/` / `__pycache__/` / `*.pyc` already exists at the
  repo root from the 00 port — no change needed.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Already copied; edit exports from `Config, Player` to `Config, Player, Tool, Message, Context` |
| `lib/boukensha/config.rb` | `boukensha/config.py` | Already copied; delete `PROMPTS_DIR` lines 14–16 to match Ruby 01 |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tasks/player.rb` | `boukensha/tasks/player.py` | Already copied and correct; leave unchanged |
| `lib/boukensha/tool.rb` | `boukensha/tool.py` | NEW — `@dataclass` |
| `lib/boukensha/message.rb` | `boukensha/message.py` | NEW — `@dataclass` |
| `lib/boukensha/context.rb` | `boukensha/context.py` | NEW — plain class |
| `examples/example.rb` | `examples/example.py` | Rewrite mirroring 00's `sys.path` pattern |
| `Gemfile` (`dotenv`) | `requirements.txt` (`PyYAML`, `python-dotenv`), per-step, unpinned |
| `README.md` | `README.md` | Port field tables + examples, Python run instructions |
| `bin/ruby/01_struct_skeleton` | `bin/python/01_struct_skeleton` | Mirror `bin/python/00_config` |

## New class/struct behavior (the actual porting work)

### `Tool` (`tool.rb` → `tool.py`)

Ruby: `Tool = Struct.new(:name, :description, :parameters, :block)` — four
positional fields:
- `name` — string, e.g. `"move"`
- `description` — string shown to the agent
- `parameters` — hash of arg name → schema, e.g.
  `{ direction: { type: "string", description: "..." } }`
- `block` — a callable run when the tool is invoked

Ruby `to_s`:
`"#<Tool name=#{name} description=#{description.to_s[0..40]} params=#{parameters.keys}>"`

Python (`@dataclass` + `__str__`):
```python
from dataclasses import dataclass
from typing import Callable, Optional

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    block: Optional[Callable] = None

    def __str__(self):
        return (
            f"#<Tool name={self.name} "
            f"description={str(self.description)[:41]} "
            f"params={list(self.parameters.keys())}>"
        )
```

### `Message` (`message.rb` → `message.py`)

Ruby: `Message = Struct.new(:role, :content, :tool_use_id)`:
- `role` — `user` / `assistant` / `tool_result`
- `content` — string
- `tool_use_id` — optional, links a tool result to its call

Ruby `to_s`: builds `id_tag = tool_use_id ? " [#{tool_use_id}]" : ""`, then
`"#<Message role=#{role}#{id_tag} content=#{content.to_s[0..60]}...>"`
(the `...` is always appended literally, not conditional).

Python:
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Message:
    role: str
    content: str
    tool_use_id: Optional[str] = None

    def __str__(self):
        id_tag = f" [{self.tool_use_id}]" if self.tool_use_id else ""
        return f"#<Message role={self.role}{id_tag} content={str(self.content)[:61]}...>"
```

### `Context` (`context.rb` → `context.py`)

A real class (not a Struct). Ruby API:
- `attr_reader :task, :system, :messages, :tools`
- `initialize(task:, system: nil)` — `@messages = []`, `@tools = {}` (keyed by tool name)
- `register_tool(tool)` → `@tools[tool.name] = tool`
- `add_message(role, content, tool_use_id: nil)` → appends `Message.new(...)`
- `tool_count` → `@tools.size`; `turn_count` → `@messages.size`
- `to_s` → `"#<Context task=#{task&.task_name} turns=#{turn_count} tools=#{tool_count}>"`
  (`task` is the `Player` **class**, so `task_name` is a class-method call)

Python:
```python
from .message import Message

class Context:
    def __init__(self, task, system=None):
        self.task = task
        self.system = system
        self.messages = []
        self.tools = {}

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    @property
    def tool_count(self):
        return len(self.tools)

    @property
    def turn_count(self):
        return len(self.messages)

    def __str__(self):
        tn = self.task.task_name() if self.task else None
        return f"#<Context task={tn} turns={self.turn_count} tools={self.tool_count}>"
```

## Idiom translations

Config/Tasks idioms are inherited unchanged from the 00 port (dropped dual
string/symbol lookup, `@classmethod` Base, `NotImplementedError` `task_name`,
`yaml.safe_load`, guarded `load_dotenv`, `Path().expanduser().resolve()`).
New for step 01:

- `Struct.new(...)` with custom `to_s` → `@dataclass` with `__str__` override.
  Dataclass (not `NamedTuple`) matches the Ruby README's "in practice we'd
  use Classes" note.
- **Inclusive → exclusive truncation.** Ruby `str[0..40]` is inclusive (41
  chars) → Python `str[:41]`; Ruby `str[0..60]` → Python `str[:61]`. Do **not**
  reuse 00's `[:60]` blindly — the counts differ per struct.
- Ruby symbols → Python strings: `add_message(:user, ...)` →
  `add_message("user", ...)`; interpolates identically (`role=user`).
- `task&.task_name` (safe-nav, class-method call on the `Player` class) →
  `self.task.task_name() if self.task else None`.
- `block` lambda → Python lambda:
  `lambda direction: f"You move {direction} into a torch-lit corridor."`
- `__init__.py` re-exports `Config, Player, Tool, Message, Context` with
  `__all__`.

## `examples/example.py`

Mirror 00's `example.py` structure (sys.path insert, `BOUKENSHA_DIR`
setdefault pointing at the repo-root `.boukensha` via `Path(__file__)
.resolve().parents[4]`), then:

1. `config = Config()`; `player_settings = config.tasks("player")`
2. `system_prompt = Player.system_prompt(player_settings,
   user_prompts_dir=config.user_prompts_dir)` — **note: no
   `default_prompts_dir`** (step 01 dropped `PROMPTS_DIR`).
3. `ctx = Context(task=Player, system=system_prompt)`
4. `ctx.register_tool(Tool("move", "Move the player in a direction (north,
   south, east, west, up, down)", {"direction": {"type": "string",
   "description": "The direction to move"}}, lambda direction: f"You move
   {direction} into a torch-lit corridor."))`
5. `ctx.add_message("user", "Explore north and tell me what you find.")`;
   `ctx.add_message("assistant", "Sure, let me head north and take a look.")`
6. Print header, `Config:`, `Context:`, `Tool:` (via `ctx.tools["move"]`),
   then each message.

(The system prompt is stored on the Context but never printed — `Context`'s
string form doesn't include it, matching Ruby.)

## `bin/python/01_struct_skeleton`

Mirror `bin/python/00_config` exactly (activates the shared root venv itself):
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/01_struct_skeleton"
python3 examples/example.py
```
Assumes the venv exists and this step's `requirements.txt` is installed (per
the README). The Ruby `bin/ruby/01_struct_skeleton` already exists with the
correct path — no change needed there.

## Expected output

Run via `./week1_baseline/bin/python/01_struct_skeleton`. Byte-for-byte match
with the Ruby example, with only Python-native spelling divergences:
```
=== Boukensha Step 1: Struct Skeleton ===

Config:   #<Boukensha::Config dir=/home/you/.boukensha tasks=player>
Context:  #<Context task=player turns=2 tools=1>
Tool:     #<Tool name=move description=Move the player in a direction (north, so params=['direction']>
Messages:
  #<Message role=user content=Explore north and tell me what you find....>
  #<Message role=assistant content=Sure, let me head north and take a look....>
```
(`dir=` differs per machine. The one field that visibly differs from Ruby:
Ruby prints `params=[:direction]` (symbols); Python's string-keyed dict prints
`params=['direction']` — a native divergence analogous to the `True`/`true`
one 00 already accepted.)

## Carried-over known gaps (not fixed in this port, for parity)

Same items the Ruby READMEs already flag as deliberately unfixed:
- Default prompt is hardcoded rather than scoped per task
  (`prompts/<task>/system.md`).
- Settings file must be exactly `.yaml`, not `.yml`.

## Decisions already made (from the 00 port, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories: `bin/ruby/01_struct_skeleton`
  (exists) and `bin/python/01_struct_skeleton` (new).
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+ (dataclasses need 3.7+, fine).
- Output parity: exact field-for-field match with the Ruby example where
  possible.
- `requirements.txt`: per-step, unpinned (`PyYAML`, `python-dotenv`).
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: the target is already copied from Python 00;
  leave `tasks/base.py`, `tasks/player.py`, `tasks/__init__.py`, and
  `requirements.txt` unchanged, and edit `config.py` only to remove
  `PROMPTS_DIR`.
- `PROMPTS_DIR` / `prompts/`: settled by straight-port scope — match Ruby 01,
  drop both from the copied Python tree.
- README vs actual `context.rb`: follow the executable Ruby implementation
  (`#<Context task=player turns=2 tools=1>`), not the README's aspirational
  richer representation.
- Struct representation: use `@dataclass`, matching Python conventions and the
  Ruby README's "in practice we'd use Classes" note.

## Remaining cosmetic decision

- **`params=[:direction]` vs `params=['direction']`.** Python has no symbols.
  Default to Python-native `['direction']` and document it like 00 documented
  `True`/`False`; hand-format Ruby-style symbols only if exact textual output
  parity is explicitly required.
