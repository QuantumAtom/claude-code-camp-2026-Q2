# 12 · Context Management (Python)

Python port of [`week1_baseline/ruby/12_context`](../../ruby/12_context/README.md).

When you call an LLM directly you are responsible for the context window.
There is no auto-compacting. This step adds proper token tracking, visual
warnings, and automatic compaction so the agent never silently blows past
the limit.

## What's new

### Accurate context tracking

`Context` now maintains two distinct token counts:

| Attribute | What it measures |
|-----------|-------------------|
| `context_window` | The model's maximum input token capacity (default 200,000; looked up per-model via `Models.context_window`) |
| `current_tokens` | Tokens actually used in the most recent API call (`usage.input_tokens` from the response) |

Previously the TUI showed a *cumulative-since-launch* input-token sum,
which only reset on process restart and had no relationship to the actual
context window. That's fixed here: the display now reflects
`context.current_tokens`, the size of the *next* API call, which drops to
near-zero right after `/clear` or a compaction. The Agent updates
`current_tokens` after every API response (including mid-turn tool-use
calls), so the display always reflects what the next call will actually
send.

### Context colour coding

The progress and status lines in the TUI now colour the context
indicator based on how full the window is:

| Usage | Colour | Meaning |
|-------|--------|---------|
| < 70% | Grey | Normal |
| 70–84% | Yellow | Approaching limit |
| ≥ 85% | Red | Compaction imminent |

A `⚠` symbol also appears in the status bar at 85%+.

### Auto-compaction

At the start of each agent turn, if `current_tokens / context_window ≥
0.85` (configurable via `Config.agent_compaction_threshold`), the Agent
automatically compacts the context before making any API call:

```
[context compacted — 12 messages dropped to free space]
```

Compaction drops the oldest 40% of messages (keeping at least 2) and
resets `current_tokens` to 0. The first API call after compaction will
report the true new size.

### `Context.compact_messages()`

```python
dropped = context.compact_messages(target_fraction=0.60)
# => 12  (number of messages dropped)
```

### `/compact` command

Manual compaction from the REPL or TUI:

```
boukensha> /compact
(compacted context — 12 messages dropped)
```

### `Logger.compaction` event

```json
{"phase": "compaction", "before": 172000, "dropped": 12, "context_window": 200000}
```

Emitted whenever auto- or manual compaction runs. The TUI subscribes to
this event to display the compaction notice in the conversation view.

### `boukensha.run()` / `boukensha.repl()` — `context_window` now model-derived

`Context(context_window=...)` defaults to `Models.context_window(model)`
instead of a fixed value — pass a `Context` with an explicit
`context_window` directly if you need to override it for a non-catalog
model.

### Per-turn token spend limit

Alongside the existing `max_iterations` ceiling, the Agent now also
stops (and wraps up the turn in character) once a turn's cumulative
input+output tokens reach `max_turn_tokens` (default 60,000, configurable
via `Config.agent_max_turn_tokens` / `settings.yaml`'s `agent.max_turn_tokens`).
Both limits are trigger thresholds, not hard caps — whichever trips
first ends the work loop and makes one final tools-disabled call so the
agent finishes its answer instead of aborting mid-thought.

### Reasoning content blocks

Every backend now normalizes provider "thinking"/reasoning output into a
common `{"type": "reasoning", "text": ..., "signature": ..., "redacted":
...}` content block (see `boukensha/backends/base.py`'s docstring for
the full contract):

| Provider | Native representation |
|----------|------------------------|
| Anthropic | `thinking` / `redacted_thinking` content blocks (signature round-trips for continued turns) |
| Gemini | `part["thought"]` / `thoughtSignature` |
| Ollama / Ollama Cloud | `message["thinking"]` (thinking explicitly disabled via `think: false` in the request — reasoning is only surfaced if present) |
| OpenAI (Responses API) | `output[]` items of type `"reasoning"` (dropped when rebuilding assistant turns — not needed with `reasoning.effort: "none"`) |

Two new `Logger` events surface this: `reasoning(text, redacted)` for
each reasoning block emitted mid-turn, and `plan(text)` for any preamble
text that accompanies a tool call.

Note: `Logger.response()` no longer accepts `task`/`backend` and no
longer computes `cost_usd`/`provider`/`usage_unit`/`model` metadata — that
computation was removed in this step. `Backends::Base.estimate_cost`/
`usage_unit`/`usage_level` still exist on every backend, just unused by
the logger now.

### OpenAI backend — now targets the Responses API

`gpt-5.x` rejects `reasoning_effort` + tools on `/v1/chat/completions`
("Please use /v1/responses"), so `boukensha/backends/openai.py` now
targets `POST /v1/responses` instead: the system prompt becomes a
top-level `instructions` string, messages become `input` items, tool
defs are flat (no `function:` wrapper), and tool results round-trip via
`function_call_output` items matched by `call_id`.

### Task abstraction removed

`boukensha/tasks/` (the `Player` task class) has been removed. Its two
responsibilities — resolving the system prompt and picking a
provider/model — are now plain `Config` properties:

| Old | New |
|-----|-----|
| `Player.system_prompt(task_settings, ...)` | `Config.system_prompt` |
| `Player.model(task_settings)` | `Config.model` (defaults to `"claude-haiku-4-5"` if unset — no longer raises) |
| `Player.provider(task_settings)` | `Config.provider_type` (defaults to `"anthropic"` if unset — no longer raises) |
| `Player.max_iterations`/`.max_output_tokens` | `Config.agent_max_iterations`/`.agent_max_output_tokens` |

`Config.system_prompt` also gains a new middle tier: previously, a
non-overridden prompt always read the shipped default and never
consulted anything under `.boukensha`. Now it checks, in order:

1. If `tasks.player.prompt_override.system: true` in `settings.yaml`:
   `.boukensha/prompts/player/system.md`
2. `.boukensha/prompts/system.md` (flat user override — new, works
   without setting the override flag)
3. The shipped default (`prompts/system.md` in this package)

### File-system tool surface trimmed

`list_directory` and `search_files` have been dropped from the
file-system MCP server (`boukensha/mcp_servers/file_system_server.py`) —
leftover from when this app was a coding harness; the player agent
operates on paths it's already told about. `pwd`, `read_file`,
`write_file`, and `delete_file` are unchanged, including the existing
root-escape guard.

The MCP subprocess transport itself (`mcp_client.py`,
`mcp_servers/*.py`) is unchanged — it predates this step and isn't
touched by it.

## Run the demo

```bash
python3 examples/example.py

# interactive TUI:
./week1_baseline/bin/python/12_context
```

Requires the same `.boukensha/settings.yaml` + API key setup as every
prior step, plus `pip install -r week1_baseline/python/12_context/requirements.txt`
(shared venv, same as every other step).
