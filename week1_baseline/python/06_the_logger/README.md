# 06 · The Logger (Python)

Python port of [`week1_baseline/ruby/06_the_logger`](../../ruby/06_the_logger/README.md).

`Logger` records each agent run as structured JSON Lines. It is a file
logger, not user-facing display output — every phase of the agent loop
(iterations, prompts, tool calls, responses) is written to a session file
under `.boukensha/sessions/`.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/06_the_logger/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/logger.py` | `Logger` — writes structured JSONL events for each agent run |

## Updated files

| File | Change |
|---|---|
| `boukensha/agent.py` | Logs every loop phase via `self.logger`; a raising tool no longer crashes the turn — it's caught, logged as a `tool_result` with `ok=False`, and surfaced to the model as an `"ERROR: ..."` result |
| `boukensha/__init__.py` | Added `config()`, `quiet()`, `loud()`, `is_quiet()`, `debug()`, `is_debug()` module-level functions |
| `boukensha/errors.py` | `LoopError` removed |
| `boukensha/config.py` | `mud_*` properties removed |
| `examples/example.py` | Wires up a `Logger` and passes it into `Agent` |

## How the loop works

```
send messages to API
        ↓
stop_reason == "tool_use"?
    yes → extract tool calls
        → dispatch each tool via Registry (errors caught, logged, and
          surfaced to the model instead of raising)
        → inject results as tool_result messages
        → go back to top
    no  → return final text response
```

Every step of this — the iteration count, the outgoing prompt, each tool
call/result, and each model response — is now written to the session log
as it happens. See "Session logs" below.

## `Agent`

| Method | Description |
|---|---|
| `run()` | Starts the loop and returns the final text response when the agent is done |

## Every backend speaks the same normalized shape

Five providers means five different response formats — Anthropic nests tool
calls inside `content`, Ollama puts them in `message.tool_calls`, OpenAI
nests them under `choices[0].message.tool_calls`, and Gemini calls them
`functionCall` parts. Rather than teach the agent loop about each of these,
every backend implements `parse_response(response)`, converting its raw
response into one common shape:

```python
{
    "stop_reason": "tool_use" | "end_turn",
    "content": [
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
    ],
}
```

`Agent` only ever sees this shape — it calls `self.builder.parse_response(response)`,
which delegates to the backend, and never inspects a raw provider response.

The conversion also runs in reverse. When the conversation history is
replayed on the next request, Ollama, Ollama Cloud, OpenAI, and Gemini each
rebuild a provider-specific assistant message from the normalized `content`
blocks via a private `_assistant_message` (or `_assistant_parts`) method —
the inverse of `parse_response`. Anthropic's `content` array doubles as both
the normalized shape and the wire format, so it needs no extra conversion.

**Tool call IDs aren't universal.** Anthropic and OpenAI assign every tool
call a unique `id`, echoed back in the `tool_result`. Ollama, Ollama Cloud,
and Gemini don't assign call ids at all — those backends reuse the tool's
`name` as its `id` and match the `tool_result` back to the call by name.

## Session logs

Each `Logger` instance creates a session id and writes one log file for that session:

```text
.boukensha/sessions/<session-id>.jsonl
```

Every line is a complete JSON object with `session_id`, `at`, and `phase` fields, plus phase-specific data. This keeps logs grep/tail friendly and machine readable.

```json
{"phase":"session_start","session_id":"20260528T143011Z-a1b2c3d4","at":"2026-05-28T10:30:11-04:00"}
{"phase":"iteration","n":1,"max":25,"session_id":"20260528T143011Z-a1b2c3d4","at":"2026-05-28T10:30:11-04:00"}
```

`response`-phase lines include the active task, provider, model, normalized token counts, and estimated USD cost when the backend has token pricing data:

```json
{"phase":"response","task":"player","provider":"anthropic","model":"claude-haiku-4-5","input_tokens":1000,"output_tokens":100,"cost_usd":0.0015}
```

A run's `phase` sequence looks like: `session_start`, then per iteration
`iteration` → `prompt` → (`raw`, if debug is enabled) → `response` →
(`tool_call`/`tool_result` pairs, if the model called tools) → ... →
final `response` → `turn_end`.

## `Logger`

| Method | Phase | Logs |
|---|---|---|
| `iteration(n=, max=)` | `iteration` | loop counter |
| `limit_reached(kind=, n=, max=)` | `limit_reached` | iteration ceiling hit |
| `prompt(messages=, tools=)` | `prompt` | messages, tool names |
| `tool_call(name=, args=)` | `tool_call` | tool name and arguments |
| `tool_result(name=, result=, ok=, error=)` | `tool_result` | tool result, success/failure |
| `response(text=, usage=, stop_reason=, task=, backend=)` | `response` | response text, token usage, task/provider/model, estimated cost |
| `raw(data=)` | `raw` | raw provider response, only when `boukensha.debug()` is enabled |
| `turn_end(reason=, iterations=, tokens=)` | `turn_end` | why/when the turn ended |
| `close()` | — | closes the underlying file handle |

Default usage:

```python
logger = Logger()
agent = Agent(context=ctx, registry=registry, builder=builder,
              client=client, logger=logger, task_settings=player_settings)
```

You can also provide a session id or override the destination directory:

```python
Logger(session_id="manual-session")
Logger(dir="/tmp/boukensha-sessions")
```

For compatibility, `log=` still accepts an explicit file path, but normal
iteration usage should write under `.boukensha/sessions`.

If no `logger=` is passed to `Agent`, it constructs its own default
`Logger()` — `Agent.__init__` deliberately uses `logger=None` rather than a
literal `logger=Logger()` default, since a literal default is evaluated
once at class-definition time and would share a single `Logger` (and its
open file) across every `Agent` instance.

## Debug events

Call `boukensha.debug()` before constructing/running the agent to include
raw provider responses in the log:

```python
import boukensha
boukensha.debug()
```

## Task configuration

This step uses the task-based configuration introduced in the earlier
steps:

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    prompt_override:
      system: true
    max_iterations: 25
    max_output_tokens: 1024
```

When `prompt_override.system` is true, Boukensha reads
`.boukensha/prompts/player/system.md`. Otherwise it falls back to this
step's shipped `prompts/system.md`. `max_iterations` controls model
round-trips per turn before wind-down, and `max_output_tokens` is passed to
each model reply.

Every backend still takes a `model=` keyword argument; `examples/example.py`
gets both provider and model from `tasks.player`, then builds the matching
backend. The backend validates the model at construction time and exposes
metadata such as `context_window`, `usage_unit`, and token cost estimates
used by the logger's cost estimation.

| Provider | Backend | Requires |
|---|---|---|
| `anthropic` | `boukensha.backends.anthropic.Anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `boukensha.backends.openai.OpenAI` | `OPENAI_API_KEY` |
| `gemini` | `boukensha.backends.gemini.Gemini` | `GEMINI_API_KEY` |
| `ollama` | `boukensha.backends.ollama.Ollama` | a local Ollama server (`host=` defaults to `http://localhost:11434`) |
| `ollama_cloud` | `boukensha.backends.ollama_cloud.OllamaCloud` | `OLLAMA_API_KEY` |

```python
# Anthropic
backend = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model="claude-sonnet-4-6")

# Ollama running locally
backend = Ollama(model="gemma4")

# Ollama Cloud
backend = OllamaCloud(api_key=os.environ["OLLAMA_API_KEY"], model="kimi-k2.5:cloud")
```

## What the loop looks like

Running the example produces output like this:

```
=== BOUKENSHA Step 6: The Logger ===

Config: #<Boukensha::Config dir=/path/to/repo/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Max iterations: 25
Max output tokens: 1024

=== FINAL RESPONSE ===
This is BOUKENSHA, a MUD player assistant framework. It can...
```

...while `.boukensha/sessions/<session-id>.jsonl` fills in with the
`iteration`/`prompt`/`response`/`tool_call`/`tool_result`/`turn_end`
sequence for the run — see "Session logs" above for the exact shape.

## Considerations

**A raising tool no longer crashes the turn.** `Agent._handle_tool_calls`
wraps each tool dispatch in a `try`/`except`; a raising tool is logged as a
`tool_result` with `ok=False` and `error` set, and the model sees an
`"ERROR: ..."` string as the result instead of the turn aborting.

**The assistant message must be stored before the tool result.** The
Anthropic API requires the assistant's tool_use block to appear in the
message history before its corresponding tool_result. `Agent._handle_tool_calls`
handles this ordering — get it wrong and the API rejects the request.

**The model can call multiple tools in one turn.** The loop handles this by
iterating over all tool_use blocks in a single response before making the
next API call.

**`MAX_ITERATIONS` is a turn ceiling, not a hard cap.** A poorly prompted
agent can loop forever if the model keeps calling tools. `Agent` stops
starting new work after 25 iterations by default (or `tasks.player.max_iterations`)
and makes one short wind-down call with tools disabled (`_wrap_up`). This
keeps the turn bounded while still returning a useful final response,
instead of raising.

**The agent has no way to stop itself.** The model signals it is done via
`stop_reason: "end_turn"`. `Agent` watches for that signal and exits the
loop. The agent never decides unilaterally to stop.

## Considerations (carried over)

- Settings files must use `.yaml`, not `.yml`.
- No persistent memory or context compaction — the loop keeps appending
  messages for the whole turn; long-running turns grow the context
  unbounded within the `max_iterations` ceiling. That's a later step.
- `quiet()`/`loud()`/`is_quiet()` are wired up but nothing reads them yet —
  ported for parity with Ruby, not used until a later step.
- The logger's file handle is never closed automatically (no
  context-manager protocol) — `close()` exists but nothing calls it.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader; also exposes `PROMPTS_DIR` |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container |
| `boukensha/registry.py` | `Registry` — registers and dispatches tools |
| `boukensha/errors.py` | `UnknownToolError`, `UnsupportedModelError`, `ApiError` |
| `boukensha/tasks/` | Stateless task classes |
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization/parsing to a backend |
| `boukensha/backends/` | Per-provider payload/message/tool serialization and response normalization |
| `boukensha/client.py` | `Client` — sends the payload and parses the response |
| `boukensha/agent.py` | `Agent` — the tool-calling loop |
| `boukensha/logger.py` | `Logger` — structured JSONL session logging |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable smoke test — makes real, potentially multiple API calls |

## Run example

```bash
./week1_baseline/bin/python/06_the_logger
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml` and makes **real, potentially multiple** network requests —
one per loop iteration — so it requires that provider's API key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or
`OLLAMA_API_KEY`) to be set in the environment or in `~/.boukensha/.env` —
`ollama` is the only provider that needs no key and no network access
beyond `localhost`.
