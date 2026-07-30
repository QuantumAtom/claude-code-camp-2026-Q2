# Python Port Plan — 12_context

## Goal

Port `week1_baseline/ruby/12_context` to `week1_baseline/python/12_context`. Same
behavior, new language. **No new features beyond what Ruby 12 actually adds.
Plan only — no source files are touched by writing this document.**

This is a bigger step than any prior one: it bundles four independent
features in a single Ruby diff (confirmed via `diff -rq ruby/11_tui
ruby/12_context`, full-text diff of every flagged file, plus direct
inspection of `models.rb`, `Gemfile`, `boukensha.gemspec`, `README.md`):

1. **Context-window tracking + auto/manual compaction** — the step's
   namesake feature.
2. **A "reasoning" content-block contract** added to every backend
   (Anthropic thinking, Gemini `thought`, Ollama `thinking`, OpenAI
   reasoning items) plus two new Logger events (`reasoning`, `plan`).
3. **OpenAI backend rewritten** from Chat Completions to the Responses API
   (new endpoint, new payload/response shape) — unrelated to context
   management itself, just bundled into the same working session.
4. **The `Tasks::Player` abstraction deleted**, folded directly into
   `Config` — plus a **partial reversion of the MCP tool transport**
   back to in-process closures for `file_system`/`shell`.

**This plan only covers what changed between the Python baseline
(`11_tui`) and Ruby 12.** Everything already ported correctly through
`11_tui` stays exactly as it is unless called out below. Nothing gets
rewritten from scratch and nothing that already works gets touched or
regenerated.

**Starting point:** `week1_baseline/python/12_context` already exists and
is a byte-for-byte copy of the finished `week1_baseline/python/11_tui`
tree (confirmed via `diff -rq` — zero output), same "in-place edit of the
copied tree" pattern every prior step has used. It has not yet received
any of the delta below.

## Source of truth (what changed, Ruby 11 → Ruby 12)

| Ruby file | Change vs. 11 | Status |
|---|---|---|
| `lib/boukensha/context.rb` | `task:` kwarg **removed**; `system:` becomes required (was optional); adds `context_window:` (default 200,000), `compaction_threshold:` (default 0.85); new state `current_tokens`, `turn_tokens`; new methods `update_tokens`, `reset_turn_tokens`, `add_turn_tokens`, `usage_fraction`, `usage_pct`, `needs_compaction?`, `compact_messages!` | Port in full — see design below |
| `lib/boukensha/models.rb` | **NEW** — a top-level `Models.context_window(model)` static lookup table, separate from each backend's own `MODELS[model][:context_window]` | Port as `boukensha/models.py` — see note on the two-tables discrepancy below |
| `lib/boukensha/agent.rb` | `task_settings:` kwarg **removed**, replaced by `max_turn_tokens:`; `run` calls `compact_if_needed` before the loop and checks `token_limit_reached?` alongside `iteration_limit_reached?`; records usage every call via `record_usage`; extracts and logs `reasoning` blocks via `log_reasoning`; `log_response`/`normalized_usage` helpers **deleted** (logging simplified — see Logger row) | Port in full — see design below |
| `lib/boukensha/logger.rb` | `prompt` gains `context_window:`; new `compaction(before:, dropped:, context_window:)` and `reasoning(text:, redacted:)`/`plan(text:)` events; `response` **drops** `task:`/`backend:` kwargs and the entire `execution_metadata`/`cost_usd`/`provider`/`usage_unit`/`usage_level` computation (`_execution_metadata`, `_task_name`, `_provider_name`, `_usage_tokens`, `_first_integer`, `_estimate_cost` all deleted) | Port in full — this is a real feature **removal**, not an oversight (see below) |
| `lib/boukensha/config.rb` | `tasks(name)`/`user_prompts_dir` **removed**; new `provider_type`, `model`, `system_override?`, `agent_max_iterations`, `agent_max_output_tokens`, `agent_max_turn_tokens`, `agent_compaction_threshold`, `load_system_prompt`/`system_prompt` (new two-tier resolution — see below); `PROMPTS_DIR` path fixed (was `"../../../prompts"`, now `"../../prompts"` — see bug-fix callout) | Port in full — see design below |
| `lib/boukensha.rb` | Both `run`/`repl` drop `Tasks::Player`/`task_settings` entirely, call `cfg.system_prompt`/`cfg.model`/`cfg.provider_type`/`cfg.agent_max_*` directly; `Context.new` gets `context_window: Models.context_window(model)` and `compaction_threshold: cfg.agent_compaction_threshold`; `require_relative "boukensha/tasks/player"` dropped, `require_relative "boukensha/models"` added | Port in full |
| `lib/boukensha/repl.rb` | `task_settings:` kwarg **removed**, `max_turn_tokens:` added and threaded to `Agent.new`; new `/compact` command (REPL text + banner line) | Port in full |
| `lib/boukensha/tui.rb` | `ANSI_COLORS` palette changed (was `blue`/`violet`/`Red`/`gold`, now `cyan`/`bright_black`/`green`/`white`/`yellow`/`red`); session-cumulative token counters (`@session_input_tokens`/`@session_output_tokens`) **removed** from the idle/status display, replaced by `@context.current_tokens`/`usage_pct`; new `ctx_color`/`CTX_WARN_PCT`(70)/`CTX_ALERT_PCT`(85) colour coding + `⚠` marker; new `compaction` event handler appending a conversation notice; `@textarea.width` now tracked (cosmetic, bubbletea-specific — no Python equivalent needed, Textual's `Input` already fills its container) | Port the behavior (colour thresholds, context-window display, compaction notice); the textarea-width line is Ruby/bubbletea plumbing with no Textual equivalent, skip it |
| `lib/boukensha/backends/base.rb` | Adds a large doc comment specifying the normalized "reasoning" content-block contract (no code change) | Port as a docstring on `Base`/module level |
| `lib/boukensha/backends/anthropic.rb` | Maps `thinking`/`redacted_thinking` response blocks → `{"type"=>"reasoning", ...}`; rebuilds them back to native blocks in `assistant_content` (new — assistant messages previously passed `msg.content` straight through; now routed through `assistant_content`); drops `claude-haiku-4-5-20251001` from `MODELS` | Port in full — see design below |
| `lib/boukensha/backends/gemini.rb` | Adds `thinkingConfig` to the request (disables thinking: `{thinkingBudget: 0}`, or `{thinkingLevel: "LOW"}` for one specific model id that isn't actually in `MODELS` — see bug callout); maps `part["thought"]` → reasoning block, carries `thoughtSignature` through tool-call and reasoning blocks both directions; trims `MODELS` from 5 entries to 2 | Port in full — see design below |
| `lib/boukensha/backends/ollama.rb` | Adds `think: false` to the request payload; maps `message["thinking"]` → reasoning block; trims `MODELS` from 9 entries to 1 (`gemma4:e4b` only) | Port in full |
| `lib/boukensha/backends/ollama_cloud.rb` | Adds `think: false`; maps `message["thinking"]` → reasoning block; `MODELS` unchanged (same 3 entries, cosmetic reorder only) | Port in full |
| `lib/boukensha/backends/openai.rb` | **Full rewrite**: `BASE_URL` → `/v1/responses` (Responses API, not Chat Completions); `to_messages`→`to_input` (messages become `input` items, system prompt becomes top-level `instructions`, tool defs flattened, tool results become `function_call_output` items keyed by `call_id`); `parse_response` reads `response["output"]` (`reasoning`/`message`/`function_call` item types) instead of `choices[0].message`; payload adds `reasoning: {effort: "none"}`; `MODELS` drops `gpt-5.4`, adds `gpt-5.4-nano` | Port in full — see design below |
| `lib/boukensha/errors.rb` | Whitespace-only realignment | No change |
| `lib/boukensha/version.rb` | `VERSION` bumped `0.11.0` → `0.12.0` | `version.py` → `"0.12.0"` |
| `prompts/system.md` | `"CircleMUD"` → `"tbaMUD"` | One-line text change |
| `lib/boukensha/mcp_client.rb`, `lib/boukensha/mcp_servers/*.rb` | **Deleted** — Ruby reverts the MCP stdio-subprocess transport for `file_system`/`shell` back to in-process closures | **Out of scope for Python** — see MCP decision below |
| `lib/boukensha/tools/file_system.rb`, `tools/shell.rb` | Rewritten as direct in-process tool registrations (no MCP); `file_system.rb` **drops** `list_directory`/`search_files` (kept: `pwd`, `read_file`, `write_file`, `delete_file`) and adds an explicit root-escape guard returning an `"error: ..."` string | The *transport* reversion is out of scope (see below); the *tool-surface* change (drop 2 tools) is a real step-12 behavior change worth porting into Python's existing MCP server — see below |
| `lib/boukensha/tasks/base.rb`, `tasks/player.rb` | **Deleted** | See Task-removal decision below |
| `lib/boukensha_loader.rb`, `Gemfile`'s `mud_manager`/`mcp` gems, `boukensha.gemspec`'s `mcp` dependency | Ruby packaging/gem removals tracking the MCP reversion | Out of scope — same reasoning `11_tui.md` gave for `boukensha_loader.rb` |
| `examples/example.rb` | Unchanged (confirmed via `diff`) | `examples/example.py` unchanged |
| `README.md` | Rewritten for step 12 — see README plan below | See README plan below |

### Bug fix noticed, no action needed

Ruby's `Config::PROMPTS_DIR` was broken in `11_tui`
(`File.expand_path("../../../prompts", __dir__)` resolves to
`ruby/prompts`, one level above the step directory — verified by
evaluating it directly, that path doesn't exist). Step 12 fixes it to
`"../../prompts"`, correctly resolving to `ruby/12_context/prompts`.
Python's `Config.PROMPTS_DIR` (`Path(__file__).resolve().parent.parent /
"prompts"`) was **already correct** in `11_tui` and needs no change —
same category as the `examples/example.rb` off-by-one `11_tui.md` flagged,
a Ruby-only regression-and-fix that never reached Python.

### Discrepancy noticed, preserved faithfully (not fixed)

`boukensha.rb` computes `context_window` via the new top-level
`Models.context_window(model)`, **not** via the backend's own
`MODELS[model][:context_window]` that already existed on every backend
class (used internally by `estimate_cost`/`context_window` on the
backend instance itself). The two tables disagree: `Models::TABLE` only
lists 3 Anthropic model ids, all pinned to `200_000`, while
`Backends::Anthropic::MODELS` lists `claude-sonnet-4-6`/`claude-opus-4-8`
at `1_000_000`. Any non-Anthropic model (`gpt-*`, `gemini-*`, `gemma*`,
etc.) silently falls through to `Models::DEFAULT_CONTEXT_WINDOW`
(`32_000`) regardless of its real window. This looks like an
unreconciled leftover from introducing the new `Models` table without
wiring it to the existing per-backend catalogs — **this plan ports it
exactly as-is** (same two-tables-that-disagree structure), rather than
"fixing" it by having `Models.context_window` consult the backend
catalogs, because that's a real behavioral fork worth being visible
during implementation review, not a place to quietly diverge from Ruby.
Flag if you'd rather have Python's `Models.context_window` reconcile with
the backend tables instead of reproducing the disagreement.

Related: Gemini's `thinking_config` special-cases model id
`"gemini-3.1-pro-preview-customtools"`, which **does not appear** in
`Gemini::MODELS` at all (that table only has `gemini-3.5-flash` and
`gemini-3.1-flash-lite`) — selecting that model would fail
`validate_model!` before `thinking_config` is ever reached, making that
branch dead code in the Ruby source today. Ported as-is (dead branch and
all) for the same reason.

## Decisions to confirm before implementation

### 1. Task-system removal: fold into `Config`, delete `tasks/`?

Ruby deleted `Tasks::Base`/`Tasks::Player` wholesale and moved their two
behaviors directly into `Config`:
- `provider`/`model` lookup → `Config#provider_type`/`Config#model`, now
  with silent defaults (`"anthropic"`/`"claude-haiku-4-5"`) instead of
  raising when unset (Ruby's `Tasks::Base.provider`/`.model` raised
  `ArgumentError`-style errors if `tasks.player.provider`/`.model` were
  missing from `settings.yaml`; the new `Config#provider_type`/`#model`
  never raise — this is a real, user-visible looseness change, not just
  a refactor).
- prompt resolution → `Config#load_system_prompt`, with a **new middle
  tier**: previously (`Tasks::Base#prompt`), a non-overridden prompt
  always read the *shipped default* (`default_prompts_dir/system.md`)
  and never consulted anything under the user's `.boukensha` dir unless
  `prompt_override.system: true` was set. Step 12 adds a plain
  `.boukensha/prompts/system.md` check **before** falling back to the
  shipped default, independent of the override flag. Three tiers now,
  checked in order:
  1. If `tasks.player.prompt_override.system == true`:
     `.boukensha/prompts/player/system.md` (task-scoped override)
  2. `.boukensha/prompts/system.md` (flat user override — **new**, works
     without setting the override flag)
  3. The shipped default (`PROMPTS_DIR/system.md`)

Grepping both trees confirms `task`/`task_settings`/`Tasks::`/`Player` has
**zero** remaining references anywhere in Ruby's `lib/`, and in Python is
confined to exactly four files: `__init__.py`, `agent.py`, `context.py`,
`repl.py`. Nothing else touches it (`tools/mud.py`'s unrelated `"target"`
tool-parameter string is the only other grep hit, a false positive).

**Recommendation:** fold `Player`'s two behaviors into `config.py`
exactly as Ruby did (methods below), remove the `task`/`task_settings`
plumbing from `__init__.py`/`agent.py`/`context.py`/`repl.py`, and delete
`boukensha/tasks/` (both files become unreferenced dead code the moment
the fold lands, mirroring Ruby's own deletion). This is the one place in
this plan that removes rather than adds files, which sits in tension with
"retain all previous code, just add the delta" — flagging explicitly
because it's a real Ruby-side deletion, not a Python-only judgment call.
If you'd rather keep the files as inert, unimported leftovers instead of
deleting them, say so and this plan will leave `boukensha/tasks/*.py` in
place unused.

### 2. MCP tool transport: keep it, port only the tool-surface change

Ruby's `file_system.rb`/`shell.rb` revert from the MCP-subprocess
transport (added in the same working session, per `11_tui.md`) back to
plain in-process closures, and `mcp_client.rb`/`mcp_servers/*.rb` are
deleted outright. Python's MCP transport **predates** Ruby's own MCP
work (per `11_tui.md`: "Python got MCP first") and is a legitimate,
independent Python-side architecture choice, not something this step
asks Python to adopt for the first time. Reverting Python's transport to
match Ruby's reversion would mean deleting working, previously-ported
infrastructure (`mcp_client.py`, `mcp_servers/*.py`) purely to mirror a
Ruby implementation detail that Python never needed to copy in the first
place — directly against "retain all previous code."

**Recommendation:** keep Python's MCP transport untouched, but port the
one real *behavioral* change bundled into Ruby's rewrite — the tool
surface itself shrank: `list_directory`/`search_files` are gone,
kept-tools are `pwd`/`read_file`/`write_file`/`delete_file`, and paths
that escape the working directory now return an explicit `"error: path
'...' escapes the working directory"` string. Python's
`mcp_servers/file_system_server.py` **already has** the root-escape guard
(`_resolve`, confirmably present, added ahead of Ruby) — the only actual
delta is dropping the `list_directory` and `search_files` tool functions.
`shell.rb`'s in-process rewrite has no behavioral delta from Python's
existing `mcp_servers/shell_server.py` (same guard, same timeout/allow-list
logic, same error strings) — confirmed via diff, no change needed there
at all.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/models.py` — the `Models.context_window(model)` static
  lookup, ported with the same 3-entry table and the same disagreement
  with the backend catalogs (see discrepancy note above)

**FILL (behavioral changes to existing files):**
- `boukensha/context.py` — drop `task`, require `system`; add
  `context_window`, `compaction_threshold`, `current_tokens`,
  `turn_tokens`, `update_tokens`, `reset_turn_tokens`, `add_turn_tokens`,
  `usage_fraction`, `usage_pct`, `needs_compaction`, `compact_messages`
- `boukensha/agent.py` — drop `task_settings`; add `max_turn_tokens`,
  `_token_limit_reached`, `_record_usage`, `_compact_if_needed`,
  `_log_reasoning`; simplify `_log_response`→ inline
  `self.logger.response(text=..., usage=..., stop_reason=...)` (drop
  `task`/`backend` args entirely, matching Ruby's deletion)
- `boukensha/logger.py` — `prompt()` gains `context_window`; add
  `compaction()`, `reasoning()`, `plan()`; simplify `response()` to drop
  `task`/`backend` kwargs and delete `_execution_metadata`/`_task_name`/
  `_provider_name`/`_usage_tokens`/`_first_int`/`_estimate_cost`
- `boukensha/config.py` — drop `tasks()`/`user_prompts_dir`; add
  `provider_type`, `model`, `system_override` (property), `agent_max_iterations`,
  `agent_max_output_tokens`, `agent_max_turn_tokens`,
  `agent_compaction_threshold`, `system_prompt` (property, three-tier
  resolution above), `_load_system_prompt`
- `boukensha/__init__.py` — both `run()`/`repl()`: drop `Player`/
  `task_settings`, call `cfg.system_prompt`/`cfg.model`/`cfg.provider_type`/
  `cfg.agent_max_*` directly; `Context(...)` gains `context_window=
  Models.context_window(model)` and `compaction_threshold=
  cfg.agent_compaction_threshold`; drop `from .tasks.player import Player`,
  add `from .models import Models`
- `boukensha/repl.py` — drop `task_settings`, add `max_turn_tokens`
  (threaded into `Agent(...)`); add `/compact` handling in
  `handle_command` and the `_banner()` text
- `boukensha/tui.py` — new colour palette (`cyan`/`bright_black`/`green`/
  `white`/`yellow`/`red`); drop `session_input_tokens`/
  `session_output_tokens` from the idle/status render, read
  `self.context.current_tokens`/`usage_pct` instead; add
  `CTX_WARN_PCT`/`CTX_ALERT_PCT`, `_ctx_color`, `⚠` marker; add a
  `compaction` branch in `_handle_event` appending a conversation notice
- `boukensha/backends/base.py` — add the reasoning-contract docstring
  (no behavior change)
- `boukensha/backends/anthropic.py` — `normalize_block`/`denormalize_block`
  for `thinking`/`redacted_thinking` ↔ `reasoning`; route assistant
  messages through the new denormalize step; drop
  `claude-haiku-4-5-20251001` from `MODELS`
- `boukensha/backends/gemini.py` — `thinkingConfig` in the payload;
  `thought`/`thoughtSignature` ↔ `reasoning` mapping (both directions,
  including on tool-call blocks); trim `MODELS` to 2 entries
- `boukensha/backends/ollama.py` — `think: false` in payload;
  `message["thinking"]` → reasoning block; trim `MODELS` to
  `gemma4:e4b` only
- `boukensha/backends/ollama_cloud.py` — `think: false`; `thinking` →
  reasoning block; `MODELS` unchanged
- `boukensha/backends/openai.py` — full rewrite to the Responses API
  (see design below)
- `boukensha/mcp_servers/file_system_server.py` — drop the
  `list_directory`/`search_files` `@mcp.tool()` functions (root-escape
  guard already present, no change there); update the module docstring's
  tool list
- `boukensha/tools/file_system.py` — update the tool-list comment (no
  code change — registration call is unaffected by which tools the
  server process happens to expose)
- `boukensha/version.py` — bump to `"0.12.0"`
- `prompts/system.md` — `"CircleMUD"` → `"tbaMUD"`

**REMOVE (only if decision #1 above is confirmed as "delete"):**
- `boukensha/tasks/base.py`, `boukensha/tasks/player.py`

**LEAVE AS-IS (confirmed identical Ruby 11→12, or Python-specific and not
touched by this step):**
- `boukensha/mcp_client.py`, `boukensha/mcp_servers/shell_server.py`,
  `boukensha/tools/shell.py` — no behavioral delta (see MCP decision)
- `boukensha/message.py`, `registry.py`, `tool.py`, `prompt_builder.py`
  (only gains a docstring on `parse_response`, ported below),
  `run_dsl.py`, `client.py`, `tools/mud.py`
- `examples/example.py`
- `requirements.txt` — Ruby's Gemfile *removes* `mcp`/`mud_manager`
  tracking its MCP reversion; Python keeps `mcp` (transport retained per
  decision #2) — **no change**

**OUT OF SCOPE:**
- Ruby's `mcp_client.rb`/`mcp_servers/*.rb` deletion, `Gemfile`'s
  `mud_manager`/`mcp` gem removal, `boukensha.gemspec`'s `mcp` dependency
  removal — Python-side MCP transport is retained (decision #2)
- `lib/boukensha_loader.rb` — same reasoning as every prior step's plan

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree

## Target structure

```
week1_baseline/python/12_context/
  README.md
  requirements.txt                 <- unchanged (mcp kept, see decision #2)
  prompts/
    system.md                      <- FILL: "tbaMUD"
  boukensha/
    __init__.py                    <- FILL: drop Task, add Models/Config wiring
    version.py                     <- FILL: "0.12.0"
    config.py                      <- FILL: provider_type/model/system_prompt/agent_max_*
    models.py                      <- NEW
    tool.py
    message.py
    context.py                     <- FILL: context_window/compaction
    registry.py
    errors.py
    prompt_builder.py               <- FILL: docstring only
    logger.py                      <- FILL: compaction/reasoning/plan events
    run_dsl.py
    client.py
    agent.py                       <- FILL: max_turn_tokens/compaction/reasoning
    repl.py                        <- FILL: /compact command
    tui.py                         <- FILL: colour coding, context bar
    mcp_client.py                  <- unchanged
    mcp_servers/
      __init__.py
      file_system_server.py        <- FILL: drop list_directory/search_files
      shell_server.py              <- unchanged
    tools/
      __init__.py
      file_system.py               <- FILL: comment only
      shell.py                     <- unchanged
      mud.py                       <- unchanged
    backends/
      __init__.py
      base.py                      <- FILL: docstring
      anthropic.py                 <- FILL: reasoning mapping, MODELS trim
      gemini.py                    <- FILL: reasoning mapping, thinkingConfig, MODELS trim
      openai.py                    <- REWRITE: Responses API
      ollama.py                    <- FILL: think:false, reasoning mapping, MODELS trim
      ollama_cloud.py              <- FILL: think:false, reasoning mapping
    [tasks/ removed — see decision #1]
  examples/
    example.py                     <- unchanged
```

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha/models.rb` | `boukensha/models.py` | NEW |
| `lib/boukensha/context.rb` | `boukensha/context.py` | `task:` → `system:` required; context-window/compaction state |
| `lib/boukensha/agent.rb` | `boukensha/agent.py` | `max_turn_tokens`, `compact_if_needed`, `record_usage`, `log_reasoning` |
| `lib/boukensha/logger.rb` | `boukensha/logger.py` | `compaction`/`reasoning`/`plan` events; `response()` simplified |
| `lib/boukensha/config.rb` | `boukensha/config.py` | `Tasks::Player` folded in; three-tier `system_prompt` |
| `lib/boukensha.rb` | `boukensha/__init__.py` | Drop `Player`, wire `Models`/`Config` directly |
| `lib/boukensha/repl.rb` | `boukensha/repl.py` | `/compact` command |
| `lib/boukensha/tui.rb` | `boukensha/tui.py` | Colour thresholds, context bar, compaction notice |
| `lib/boukensha/backends/base.rb` | `boukensha/backends/base.py` | Docstring only |
| `lib/boukensha/backends/anthropic.rb` | `boukensha/backends/anthropic.py` | thinking/redacted_thinking ↔ reasoning |
| `lib/boukensha/backends/gemini.rb` | `boukensha/backends/gemini.py` | thought/thoughtSignature ↔ reasoning |
| `lib/boukensha/backends/ollama.rb` | `boukensha/backends/ollama.py` | thinking ↔ reasoning, think:false |
| `lib/boukensha/backends/ollama_cloud.rb` | `boukensha/backends/ollama_cloud.py` | thinking ↔ reasoning, think:false |
| `lib/boukensha/backends/openai.rb` | `boukensha/backends/openai.py` | Full rewrite to Responses API |
| `lib/boukensha/version.rb` | `boukensha/version.py` | `"0.12.0"` |
| `prompts/system.md` | `prompts/system.md` | "tbaMUD" |
| `lib/boukensha/tasks/base.rb`, `tasks/player.rb` (deleted) | `boukensha/tasks/base.py`, `tasks/player.py` | Delete iff decision #1 confirmed |
| `lib/boukensha/mcp_client.rb`, `mcp_servers/*.rb` (deleted) | — | No Python action (decision #2) |
| `lib/boukensha/tools/file_system.rb`, `tools/shell.rb` (rewritten, no MCP) | `boukensha/tools/file_system.py`, `tools/shell.py` (unchanged, still MCP) | Tool-surface delta ported into `mcp_servers/file_system_server.py` instead |

## New/changed class behavior

### `boukensha/models.py` (new)

```python
# Static model -> capability table.
#
# context_window is a known *model* fact -- the physical input ceiling --
# not a value the user sets. The agent looks it up from its configured
# model id; the user never configures it in settings.yaml. Unknown models
# fall back to a conservative default so an unrecognised id can't silently
# assume a huge window.
#
# NOTE: this table is independent of (and disagrees with) each backend's
# own MODELS[model]["context_window"] -- ported faithfully from Ruby,
# see 12_context.md's "Discrepancy noticed" note. Non-Anthropic models
# fall through to DEFAULT_CONTEXT_WINDOW regardless of their real window.
TABLE = {
    "claude-opus-4-8":   {"context_window": 200_000},
    "claude-sonnet-4-6": {"context_window": 200_000},
    "claude-haiku-4-5":  {"context_window": 200_000},
}

DEFAULT_CONTEXT_WINDOW = 32_000


class Models:
    @staticmethod
    def context_window(model):
        entry = TABLE.get(str(model))
        return entry["context_window"] if entry else DEFAULT_CONTEXT_WINDOW
```

### `boukensha/context.py` (filled in)

```python
import os

from .message import Message


class Context:
    def __init__(self, *, system, context_window=200_000, working_dir=None,
                 compaction_threshold=0.85):
        self.system = system
        self.context_window = context_window
        self.working_dir = os.path.abspath(working_dir) if working_dir else None
        self.compaction_threshold = compaction_threshold
        self.messages = []
        self.tools = {}
        self.current_tokens = 0
        self.turn_tokens = 0

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    # Update the known context size from the last API response's input_tokens.
    def update_tokens(self, n):
        self.current_tokens = int(n or 0)

    # Reset the cumulative per-turn spend counter. Called at the top of a turn.
    def reset_turn_tokens(self):
        self.turn_tokens = 0

    # Add one API call's input+output tokens to the cumulative per-turn
    # total. This is the spend budget -- distinct from current_tokens
    # (window pressure).
    def add_turn_tokens(self, input_tokens, output_tokens):
        self.turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    # Fraction of the context window currently in use (0.0-1.0).
    @property
    def usage_fraction(self):
        return self.current_tokens / self.context_window if self.context_window > 0 else 0.0

    # Integer percentage (0-100).
    @property
    def usage_pct(self):
        return round(self.usage_fraction * 100)

    # True when we should compact before the next API call.
    def needs_compaction(self, threshold=None):
        threshold = self.compaction_threshold if threshold is None else threshold
        return self.usage_fraction >= threshold

    # Drop the oldest 40% of messages to free space, keeping at least 2.
    # Resets current_tokens to 0 (will be updated by the next API response).
    # Returns the number of messages dropped.
    def compact_messages(self, target_fraction=0.60):
        drop_count = min(int(-(-len(self.messages) * 0.40 // 1)), len(self.messages) - 2)
        drop_count = max(drop_count, 0)
        self.messages = self.messages[drop_count:]
        self.current_tokens = 0
        return drop_count

    # Drop all conversation history, keeping tools and system prompt intact.
    def clear_messages(self):
        self.messages = []
        self.current_tokens = 0

    @property
    def tool_count(self):
        return len(self.tools)

    @property
    def turn_count(self):
        return len(self.messages)

    def __str__(self):
        return (f"#<Context turns={self.turn_count} tools={self.tool_count} "
                f"window={self.context_window} current={self.current_tokens}>")
```

Note: `-(-len(self.messages) * 0.40 // 1)` is a ceiling-division idiom;
`math.ceil(len(self.messages) * 0.40)` is clearer and equivalent — use
whichever reads better during implementation, they're behaviorally
identical (Ruby's `.ceil` on a Float).

### `boukensha/agent.py` (filled in)

Only the pieces that change; everything else (`_extract_text`,
`_handle_tool_calls`'s tool-dispatch loop, `_fallback_message`) stays as
it is.

```python
class Agent:
    MAX_ITERATIONS = 25
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = ...  # unchanged

    def __init__(self, *, context, registry, builder, client, logger=None,
                 max_iterations=None, max_turn_tokens=None, max_output_tokens=None):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        self.logger = logger if logger is not None else Logger()
        self.max_iterations = int(max_iterations) if max_iterations else self.MAX_ITERATIONS
        self.max_turn_tokens = int(max_turn_tokens or 0)   # 0 = disabled
        self.max_output_tokens = max_output_tokens
        self.iteration = 0

    def run(self):
        self.context.reset_turn_tokens()
        self._compact_if_needed()

        while True:
            # Two independent ceilings; stop at whichever trips first.
            if self._iteration_limit_reached():
                self.logger.limit_reached(kind="max_iterations", n=self.iteration, max=self.max_iterations)
                return self._wrap_up("max_iterations")
            if self._token_limit_reached():
                self.logger.limit_reached(kind="max_tokens", n=self.context.turn_tokens, max=self.max_turn_tokens)
                return self._wrap_up("max_tokens")

            self.iteration += 1
            self.logger.iteration(n=self.iteration, max=self.max_iterations)
            self.logger.prompt(messages=self.context.messages, tools=self.context.tools,
                                context_window=self.context.context_window)

            response = self.client.call(**self._call_opts())
            self.logger.raw(data=response)
            parsed = self.builder.parse_response(response)
            self._record_usage(response)
            self._log_reasoning(parsed["content"])

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self.logger.response(text=text, usage=response.get("usage"), stop_reason=parsed["stop_reason"])
                self.logger.turn_end(reason="completed", iterations=self.iteration, tokens=self.context.turn_tokens)
                self.context.add_message("assistant", text)
                return text

    def _iteration_limit_reached(self):
        return self.max_iterations > 0 and self.iteration >= self.max_iterations

    def _token_limit_reached(self):
        return self.max_turn_tokens > 0 and self.context.turn_tokens >= self.max_turn_tokens

    def _call_opts(self):
        return {"max_output_tokens": self.max_output_tokens} if self.max_output_tokens else {}

    # Add this call's input+output to the cumulative turn total (spend
    # budget) and refresh the known context size from input_tokens
    # (compaction pressure).
    def _record_usage(self, response):
        usage = response.get("usage") or {}
        self.context.add_turn_tokens(usage.get("input_tokens"), usage.get("output_tokens"))
        self.context.update_tokens(usage.get("input_tokens"))

    def _compact_if_needed(self):
        if not self.context.needs_compaction():
            return
        before = self.context.current_tokens
        dropped = self.context.compact_messages()
        self.logger.compaction(before=before, dropped=dropped, context_window=self.context.context_window)

    # One reasoning event per reasoning block, so the viewer can show the
    # model's thinking as a first-class step. Empty non-redacted blocks
    # are skipped to avoid noise; a redacted block still renders (it tells
    # the viewer "the model thought here").
    def _log_reasoning(self, content):
        for block in content:
            if block.get("type") != "reasoning":
                continue
            redacted = block.get("redacted") is True
            text = str(block.get("text") or "")
            if not text.strip() and not redacted:
                continue
            self.logger.reasoning(text=text, redacted=redacted)

    def _wrap_up(self, reason):
        self.context.add_message("user", self.WRAP_UP_DIRECTIVE)
        try:
            response = self.client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
            parsed = self.builder.parse_response(response)
            text = self._extract_text(parsed["content"])
            text = text if text.strip() else self._fallback_message(reason)
            self._record_usage(response)
            self.logger.response(text=text, usage=response.get("usage"), stop_reason=parsed["stop_reason"])
            self.logger.turn_end(reason=reason, iterations=self.iteration, tokens=self.context.turn_tokens)
            self.context.add_message("assistant", text)
            return text
        except ApiError:
            msg = self._fallback_message(reason)
            self.logger.turn_end(reason=reason, iterations=self.iteration, tokens=self.context.turn_tokens)
            self.context.add_message("assistant", msg)
            return msg

    @staticmethod
    def _extract_text(content):
        return "\n".join(b["text"] for b in content if b.get("type") == "text")  # NOTE: "\n".join, was "".join

    def _handle_tool_calls(self, content, response):
        tool_calls = [b for b in content if b.get("type") == "tool_use"]

        # Preamble text carries no usage (the placeholder below owns the
        # turn's usage chip).
        preamble = self._extract_text(content)
        if preamble.strip():
            self.logger.plan(text=preamble)
        suffix = "s" if len(tool_calls) != 1 else ""
        self.logger.response(
            text=f"(tool use — {len(tool_calls)} call{suffix})",
            usage=response.get("usage"), stop_reason="tool_use",
        )

        self.context.add_message("assistant", content)
        # ... tool dispatch loop unchanged ...
```

Notes:
- `_extract_text` changes its join separator from `""` to `"\n"` — a
  real (if subtle) behavior change confirmed in the Ruby diff
  (`content.select{...}.map{...}.join` → `.join("\n")`). Multiple text
  blocks in one response now render as separate lines instead of run
  together.
- `_log_response`/`_normalized_usage` are **deleted**, not renamed —
  `task`/`backend` are no longer passed to the logger at all, matching
  Ruby's `Logger#response` signature change (see Logger section).

### `boukensha/logger.py` (filled in)

```python
def prompt(self, *, messages, tools, context_window):
    self._write({
        "phase": "prompt",
        "message_count": len(messages),
        "messages": [self._serialize_message(m) for m in messages],
        "tool_count": len(tools),
        "tools": list(tools.keys()),
        "context_window": context_window,
    })

def compaction(self, *, before, dropped, context_window):
    self._write({"phase": "compaction", "before": before, "dropped": dropped, "context_window": context_window})

def response(self, *, text, usage=None, stop_reason=None):
    self._write({"phase": "response", "text": str(text).strip(), "usage": usage, "stop_reason": stop_reason})

def reasoning(self, *, text, redacted=False):
    self._write({"phase": "reasoning", "text": str(text), "redacted": redacted})

def plan(self, *, text):
    self._write({"phase": "plan", "text": str(text).strip()})
```

`_execution_metadata`, `_task_name`, `_provider_name`, `_usage_tokens`,
`_first_int`, `_estimate_cost` are all **deleted** — `response()` no
longer accepts `task`/`backend` and no longer computes `cost_usd`/
`provider`/`model`/`usage_unit`/`usage_level`. This is a real feature
removal in Ruby (confirmed via diff, not an oversight — the whole block
is gone, replaced with nothing). `Backends::Base#estimate_cost`/
`#usage_unit`/`#usage_level` remain defined on every backend (Ruby didn't
remove those either) — they simply have no caller left in the logging
path. Same for Python: leave `estimate_cost`/`usage_unit`/`usage_level`
on `backends/base.py` untouched, just stop calling them from `logger.py`.

### `boukensha/config.py` (filled in)

```python
# ---------- provider --------------------------------------------------

@property
def provider_type(self):
    return self.dig("tasks", "player", "provider") or "anthropic"

@property
def model(self):
    return self.dig("tasks", "player", "model") or "claude-haiku-4-5"

# ---------- system prompt ----------------------------------------------

@property
def system_override(self):
    return self.dig("system", "override") is True

# ---------- agent limits ------------------------------------------------
# Static per-turn circuit breakers, read where the agent is constructed.
# A value of 0/None means "disabled" (no ceiling) -- useful for debugging.

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
```

`tasks()`/`user_prompts_dir` are removed (no remaining callers once
`__init__.py` is updated — confirmed by the grep above). `__str__` updates
to match Ruby's `"#<Boukensha::Config dir=... provider=... model=...>"`.

### `boukensha/__init__.py` (filled in)

Both `run()` and `repl()` get the identical treatment (they already
duplicate this setup block today):

```python
cfg = config()  # loads .env; populates os.environ
if system is None:
    system = cfg.system_prompt
if model is None:
    model = cfg.model
if backend is None:
    backend = cfg.provider_type
if api_key is None:
    api_key = {...}.get(backend)  # unchanged

context_window = Models.context_window(model)

...
ctx = Context(
    system=system, context_window=context_window,
    working_dir=resolved_working_dir,
    compaction_threshold=cfg.agent_compaction_threshold,
)
...
logger = Logger(log=log, snapshot={
    "max_iterations": cfg.agent_max_iterations,
    "max_turn_tokens": cfg.agent_max_turn_tokens,
    "max_output_tokens": (max_output_tokens or cfg.agent_max_output_tokens),
    "context_window": context_window,
    "model": model,
    "provider": backend,
})
agent = Agent(
    context=ctx, registry=registry, builder=builder, client=client, logger=logger,
    max_iterations=cfg.agent_max_iterations,
    max_turn_tokens=cfg.agent_max_turn_tokens,
    max_output_tokens=(max_output_tokens or cfg.agent_max_output_tokens),
)
```

Drop `from .tasks.player import Player`; add `from .models import Models`.
`Player` is also removed from `__all__` (iff decision #1 is "delete" —
otherwise leave the import/export in place, unused).

### `boukensha/repl.py` (filled in)

```python
HELP = """Commands:
  /quiet    suppress logging output
  /loud     re-enable logging output
  /clear    wipe conversation history (tools stay)
  /compact  drop oldest 40% of messages to free context
  /exit     leave the REPL
  /help     show this message
"""

def __init__(self, *, context, registry, builder, client, logger,
             config_dir=None, provider=None, model=None, version=None,
             api_key=None, mud=None, max_iterations=None,
             max_turn_tokens=None, max_output_tokens=None):
    ...
    self.max_turn_tokens = max_turn_tokens
    ...
    # task_settings dropped entirely

def handle_command(self, line):
    ...
    elif line == "/compact":
        dropped = self.context.compact_messages()
        self._output(f"(compacted context — {dropped} messages dropped)")
        return "command"
    return None

def run_turn(self, text):
    ...
    agent = Agent(
        context=self.context, registry=self.registry, builder=self.builder,
        client=self.client, logger=self.logger,
        max_iterations=self.max_iterations, max_turn_tokens=self.max_turn_tokens,
        max_output_tokens=self.max_output_tokens,
    )
    ...
```

`_banner()` gains one line, `/compact         free context (drop oldest
messages)`, in the same spot Ruby's banner adds it (right after
`/clear`).

### `boukensha/tui.py` (filled in)

```python
COLORS = {
    "cyan":         "#00ffff",
    "bright_black": "#808080",
    "green":        "#00ff00",
    "white":        "#ffffff",
    "yellow":       "#ffcc00",
    "red":          "#ff5555",
}

CTX_WARN_PCT = 70
CTX_ALERT_PCT = 85

class Tui(App):
    CSS = f"""
    #progress {{ color: {COLORS["cyan"]}; }}
    #progress.idle {{ color: {COLORS["bright_black"]}; }}
    #prompt_input {{ color: {COLORS["green"]}; }}
    #status {{ color: {COLORS["white"]}; background: {COLORS["bright_black"]}; }}
    RichLog {{ height: 1fr; }}
    Input {{ height: 1; border: none; }}
    Static {{ height: 1; }}
    """
    ...
    def __init__(self, repl):
        super().__init__()
        self.repl = repl
        self.context = repl.context
        self.turn_count = 0
        # session_input_tokens/session_output_tokens removed -- idle
        # display now reads self.context.current_tokens/usage_pct
        self.turn_thread = None
        ...

    def _handle_event(self, event):
        phase = event.get("phase")
        ...
        elif phase == "compaction":
            dropped = event.get("dropped")
            self.query_one("#conversation", RichLog).write(
                f"[context compacted — {dropped} messages dropped to free space]"
            )
        ...
        self.render_progress()
        self.render_status()

    def render_progress(self):
        bar = self.query_one("#progress", Static)
        if self.live_active:
            ...  # unchanged live-turn rendering
        else:
            bar.add_class("idle")
            pct = self.context.usage_pct
            used = self._fmt(self.context.current_tokens)
            maxw = self._fmt(self.context.context_window)
            bar.update(f"  [ready]   ctx {used} / {maxw} ({pct}%)   {self.turn_count} turns")

    def render_status(self):
        bar = self.query_one("#status", Static)
        pct = self.context.usage_pct
        used = self._fmt(self.context.current_tokens)
        maxw = self._fmt(self.context.context_window)
        clock = time.strftime("%H:%M:%S")
        marker = " ⚠ " if pct >= CTX_ALERT_PCT else " "
        bar.update(
            f" boukensha v{self.repl.version or VERSION} · {self.repl.model or '(model)'}  ·  "
            f"ctx {used}/{maxw} ({pct}%){marker}·  {self.context.tool_count} tools  ·  {clock} "
        )

    @staticmethod
    def _ctx_color(pct):
        if pct >= CTX_ALERT_PCT:
            return "red"
        if pct >= CTX_WARN_PCT:
            return "yellow"
        return "bright_black"
```

Note: Ruby's `render_progress`'s idle branch also recolors the whole bar
via `lip(ctx_color(pct))` (foreground swaps between grey/yellow/red based
on usage). Textual's CSS-class approach (`#progress.idle`) sets one
static idle color; reproducing Ruby's three-way dynamic recolor needs
either three CSS classes (`idle-ok`/`idle-warn`/`idle-alert`) swapped via
`add_class`/`remove_class` in `render_progress`, or an inline
`bar.styles.color = ...` set per render. Either works — pick whichever
reads cleaner in Textual; this is a mechanical detail, not a design
decision worth pausing on.

The `session_input_tokens`/`session_output_tokens` removal is a genuine
behavior change worth calling out: previously the idle/status bars showed
a *cumulative-since-launch* input-token counter that only reset on
process restart; now they show `context.current_tokens`, the size of the
*next* API call, which drops to near-zero right after `/clear` or a
compaction. This matches Ruby exactly and is the whole point of the step
(showing real context pressure instead of a monotonically-growing spend
counter) — not a regression to flag, just worth naming so it isn't
mistaken for a bug during review.

### Backends: the reasoning-block contract

Add to `backends/base.py` as a module or class docstring (ported from
Ruby's new comment, no code change):

```python
# Common base for all provider backends.
#
# Normalized response contract
# ----------------------------
# Every backend's parse_response returns:
#
#   {"stop_reason": "tool_use" | "end_turn",
#    "content": [<block>, <block>, ...]}
#
# where each block is one of:
#
#   {"type": "reasoning",
#    "text": "<human-readable reasoning, may be empty>",
#    "signature": "<opaque provider token, optional>",  # round-trip only
#    "redacted": True | False}                           # optional
#
#   {"type": "text", "text": "..."}
#
#   {"type": "tool_use", "id": ..., "name": ..., "input": {...}}
#
# Reasoning blocks come first in content, before text and tool_use
# (matching Anthropic's native ordering). `text` is what the viewer
# renders and may be empty (redacted/omitted reasoning). `signature`/
# `redacted` are opaque carry-through for providers that require the
# block echoed back unchanged (Anthropic thinking signatures, Gemini
# thoughtSignature) -- consumers never interpret them. Backends that
# don't accept reasoning back in a request drop these blocks when
# rebuilding assistant turns.
```

#### `backends/anthropic.py`

```python
MODELS = {
    "claude-haiku-4-5": {...},   # unchanged
    # "claude-haiku-4-5-20251001" entry DROPPED
    "claude-sonnet-4-6": {...},  # unchanged
    "claude-opus-4-8": {...},    # unchanged
}

def to_messages(self, messages):
    result = []
    for msg in messages:
        if msg.role == "tool_result":
            result.append({...})  # unchanged
        elif msg.role == "assistant":
            result.append({"role": "assistant", "content": self._assistant_content(msg.content)})
        else:
            result.append({"role": str(msg.role), "content": msg.content})
    return result

def parse_response(self, response):
    stop_reason = "tool_use" if response.get("stop_reason") == "tool_use" else "end_turn"
    content = [self._normalize_block(b) for b in (response.get("content") or [])]
    return {"stop_reason": stop_reason, "content": content}

def _normalize_block(self, block):
    if block.get("type") == "thinking":
        return {"type": "reasoning", "text": str(block.get("thinking") or ""), "signature": block.get("signature")}
    if block.get("type") == "redacted_thinking":
        return {"type": "reasoning", "text": "", "redacted": True, "signature": block.get("data")}
    return block

# Rebuilds Anthropic assistant content from normalized blocks (inverse of
# parse_response). Text-only turns are a bare string and pass through
# unchanged; "reasoning" blocks re-emit as native thinking/redacted_thinking
# so signatures round-trip intact.
def _assistant_content(self, content):
    if isinstance(content, str):
        return content
    return [self._denormalize_block(b) for b in content]

def _denormalize_block(self, block):
    if block.get("type") != "reasoning":
        return block
    if block.get("redacted"):
        return {"type": "redacted_thinking", "data": block.get("signature")}
    return {"type": "thinking", "thinking": str(block.get("text") or ""), "signature": block.get("signature")}
```

#### `backends/gemini.py`

```python
MODELS = {
    "gemini-3.5-flash": {...},       # unchanged
    "gemini-3.1-flash-lite": {...},  # unchanged
    # gemini-2.5-pro / gemini-2.5-flash / gemini-2.5-flash-lite DROPPED
}

def to_payload(self, context, max_output_tokens=1024, tools=None):
    return {
        "systemInstruction": {"parts": [{"text": context.system}]},
        "contents": self.to_messages(context.messages),
        "tools": self.to_tools(context.tools) if tools is None else tools,
        "generationConfig": {
            "maxOutputTokens": max_output_tokens,
            "thinkingConfig": self._thinking_config(),
        },
    }

def _thinking_config(self):
    # "gemini-3.1-pro-preview-customtools" doesn't appear in MODELS --
    # dead branch, ported as-is (see 12_context.md discrepancy note).
    if self.model == "gemini-3.1-pro-preview-customtools":
        return {"thinkingLevel": "LOW"}   # full disable not supported on this model
    return {"thinkingBudget": 0}          # gemini-3.5-flash, gemini-3.1-flash-lite

def parse_response(self, response):
    candidates = response.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []

    content = []
    tool_used = False
    for part in parts:
        if part.get("functionCall"):
            fc = part["functionCall"]
            content.append({
                "type": "tool_use", "id": fc.get("name"), "name": fc.get("name"),
                "input": fc.get("args") or {}, "signature": part.get("thoughtSignature"),
            })
            tool_used = True
        elif part.get("thought"):
            content.append({"type": "reasoning", "text": str(part.get("text") or ""),
                             "signature": part.get("thoughtSignature")})
        elif part.get("text"):
            content.append({"type": "text", "text": part["text"]})

    return {"stop_reason": "tool_use" if tool_used else "end_turn", "content": content}

def _assistant_parts(self, content):
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    parts = []
    for b in blocks:
        if b.get("type") == "tool_use":
            part = {"functionCall": {"name": b["name"], "args": b["input"]}}
            if b.get("signature"):
                part["thoughtSignature"] = b["signature"]
            parts.append(part)
        elif b.get("type") == "reasoning":
            part = {"text": str(b.get("text") or ""), "thought": True}
            if b.get("signature"):
                part["thoughtSignature"] = b["signature"]
            parts.append(part)
        else:
            parts.append({"text": b["text"]})
    return parts
```

#### `backends/ollama.py` / `backends/ollama_cloud.py`

Identical delta in both files:

```python
MODELS = {
    "gemma4:e4b": {...},  # ollama.py ONLY -- all other entries DROPPED
    # ollama_cloud.py's MODELS is unchanged (3 entries, same values)
}

def to_payload(self, context, max_output_tokens=1024, tools=None):
    return {
        "model": self.model,
        "stream": False,
        "messages": self.to_messages(context.system, context.messages),
        "tools": self.to_tools(context.tools) if tools is None else tools,
        "think": False,
    }

def parse_response(self, response):
    message = response.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    content = []
    if message.get("thinking"):
        content.append({"type": "reasoning", "text": message["thinking"]})
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for tc in tool_calls:
        ...  # unchanged
    return {"stop_reason": "end_turn" if not tool_calls else "tool_use", "content": content}
```

#### `backends/openai.py` (full rewrite — Responses API)

```python
import json

from .base import Base


class OpenAI(Base):
    BASE_URL = "https://api.openai.com/v1/responses"
    MODELS = {
        "gpt-5.5": {
            "context_window": 1_000_000,
            "cost_per_million": {"input": 5.0, "output": 30.0},
            "usage_unit": "tokens",
        },
        # "gpt-5.4" entry DROPPED
        "gpt-5.4-mini": {
            "context_window": 400_000,
            "cost_per_million": {"input": 0.75, "output": 4.5},
            "usage_unit": "tokens",
        },
        "gpt-5.4-nano": {   # NEW
            "context_window": 400_000,
            "cost_per_million": {"input": 0.2, "output": 1.25},
            "usage_unit": "tokens",
        },
    }

    def __init__(self, *, api_key, model):
        self.api_key = api_key
        self.configure_model(model)

    def to_input(self, messages):
        items = []
        for msg in messages:
            if msg.role == "tool_result":
                items.append({"type": "function_call_output", "call_id": msg.tool_use_id,
                              "output": str(msg.content)})
            elif msg.role == "assistant":
                items.extend(self._assistant_items(msg.content))
            else:
                items.append({"role": str(msg.role), "content": msg.content})
        return items

    def to_tools(self, tools):
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": list(tool.parameters.keys()),
                },
            }
            for tool in tools.values()
        ]

    def to_payload(self, context, max_output_tokens=1024, tools=None):
        return {
            "model": self.model,
            "instructions": context.system,
            "input": self.to_input(context.messages),
            "tools": self.to_tools(context.tools) if tools is None else tools,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"effort": "none"},
        }

    def headers(self):
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def url(self):
        return self.BASE_URL

    # Normalizes a Responses API output[] array into the common shape.
    def parse_response(self, response):
        function_calls = []
        content = []
        for item in response.get("output") or []:
            item_type = item.get("type")
            if item_type == "reasoning":
                text = "".join(s.get("text", "") for s in (item.get("summary") or []))
                content.append({"type": "reasoning", "text": text})
            elif item_type == "message":
                text = "".join(
                    c.get("text", "") for c in (item.get("content") or [])
                    if c.get("type") == "output_text"
                )
                if text:
                    content.append({"type": "text", "text": text})
            elif item_type == "function_call":
                function_calls.append(item)

        for fc in function_calls:
            content.append({
                "type": "tool_use",
                "id": fc.get("call_id"),
                "name": fc.get("name"),
                "input": json.loads(fc.get("arguments") or "{}"),
            })

        return {"stop_reason": "end_turn" if not function_calls else "tool_use", "content": content}

    # Rebuilds Responses input items from normalized content blocks
    # (inverse of parse_response). Reasoning blocks are dropped -- gpt-5.x
    # doesn't need them echoed back when reasoning effort is "none".
    def _assistant_items(self, content):
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content

        text = "".join(b["text"] for b in blocks if b.get("type") == "text")
        items = [] if not text else [{"role": "assistant", "content": text}]

        for b in blocks:
            if b.get("type") == "tool_use":
                items.append({
                    "type": "function_call",
                    "call_id": b["id"],
                    "name": b["name"],
                    "arguments": json.dumps(b["input"]),
                })
        return items
```

This is the largest single-file change in the step. `to_messages`
(system-prepended, `messages` key) is entirely replaced by `to_input`
(no system message — `instructions` is now a top-level payload field)
plus the `input`/`function_call_output`/`function_call` item vocabulary.
Whatever calls `OpenAI(...)` elsewhere (just `__init__.py`, unchanged
constructor signature) needs no changes — the payload/response shape is
fully encapsulated inside the backend class, matching how every other
backend already works.

### `boukensha/mcp_servers/file_system_server.py` (filled in)

Delete the `list_directory` and `search_files` `@mcp.tool()` functions
and their two lines in the module docstring's tool list. `pwd`,
`read_file`, `write_file`, `delete_file`, and the `_resolve`/`_oops`
helpers are untouched (Python already has the root-escape guard Ruby's
rewrite adds — confirmed via diff, nothing to change there).

## README plan

Mirror the Ruby README's step-12 structure:
- Lead with "context management" framing (the LLM-context-window problem,
  no auto-compacting without this step).
- A table of `Context`'s two token counts (`context_window` vs.
  `current_tokens`) and what each measures, noting the old TUI showed a
  cumulative session sum, not window pressure — that's fixed here.
- Colour-coding table (< 70% grey, 70–84% yellow, ≥ 85% red, `⚠` marker).
- Auto-compaction section: the 0.85 threshold, "drop oldest 40%, keep at
  least 2" policy, the compaction log line/event shape.
- `Context.compact_messages()` and `/compact` command sections with
  the same example transcripts as Ruby's README, adjusted for Python
  syntax (`context.compact_messages(target_fraction=0.60)`).
- `Logger.compaction` event JSON shape.
- `boukensha.run`/`boukensha.repl` gain a `context_window=` kwarg example.
- **New section not in Ruby's README** (Python-specific, since Ruby's
  README doesn't need to explain a reasoning feature that also shipped
  this same step): a short note on the new `reasoning` content-block
  contract and the `reasoning`/`plan` Logger events, since this plan
  treats it as in-scope for 12_context even though Ruby's own README text
  doesn't call it out explicitly (Ruby's README is entirely about the
  context feature; the reasoning-contract and OpenAI-rewrite work rode
  along in the same commit without README coverage — confirmed by
  reading the full README diff). Recommend documenting it anyway since
  it's real, user-visible behavior in this step's Python port.
- Keep the "Run the demo" section's gem-build steps out (no Python
  equivalent, same as every prior step) — just note
  `BOUKENSHA_DIR=... BOUKENSHA_PATH=.../python/12_context boukensha` isn't
  applicable either; use the existing `bin/python/12_context`-style
  launcher pattern established in `11_tui.md` if one is wired up, or
  `examples/example.py`/the TUI entry point already in place.

## Decisions to confirm before implementation

1. **Task-system removal** — fold `Tasks::Player`'s two behaviors into
   `Config` and **delete** `boukensha/tasks/base.py`/`player.py`
   (recommended, matches Ruby exactly), vs. leaving the files in place
   unused. See decision #1 above.
2. **MCP transport** — keep Python's MCP-subprocess transport for
   `file_system`/`shell` untouched (recommended — it predates and is
   independent of Ruby's own MCP experiment), porting only the
   tool-surface delta (drop `list_directory`/`search_files`) into the
   existing MCP server, vs. reverting Python to in-process closures to
   match Ruby's file structure exactly. See decision #2 above.
3. **The two-tables context-window discrepancy** (`Models.TABLE` vs. each
   backend's own `MODELS[...]​["context_window"]`) — port as-is
   (recommended, preserves a real and possibly-intentional-for-now Ruby
   inconsistency) vs. reconciling them in Python only.
4. **`_extract_text`'s join separator** (`""` → `"\n"`) and the
   **session-token-counter removal** in `tui.py` — both are real,
   intentional Ruby changes with no ambiguity, called out here only so
   they don't get flagged as bugs during review rather than because
   there's a choice to make.
