# 05 · The Agent Loop (Python)

Python port of [`week1_baseline/ruby/05_agent_loop`](../../ruby/05_agent_loop/README.md).

The Agent Loop is the heart of BOUKENSHA. Everything built before this — the
structs, the registry, the prompt builder, the client — was setup. The loop
is where the agent actually does work.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/05_agent_loop/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/agent.py` | The agent loop — sends requests, dispatches tools, and knows when to stop |

## Updated files

| File | Change |
|---|---|
| `boukensha/errors.py` | Added `LoopError` (unused for now — see "Considerations" below) |
| `boukensha/tasks/base.py` | Added `max_iterations`/`max_output_tokens` settings helpers, with `DEFAULT_MAX_ITERATIONS = 25` and `DEFAULT_MAX_OUTPUT_TOKENS = 1024` |
| `boukensha/client.py` | `call()` gains a `tools=None` param, threaded into the payload |
| `boukensha/prompt_builder.py` | `to_api_payload()` gains `tools=None`; added `parse_response()`, delegating to the backend |
| `boukensha/backends/*.py` | Every backend gains a `tools=None` override on `to_payload` and a new `parse_response()`; every backend but Anthropic also gains a private `_assistant_message`/`_assistant_parts` rebuild helper |

## How it works

```
send messages to API
        ↓
stop_reason == "tool_use"?
    yes → extract tool calls
        → dispatch each tool via Registry
        → inject results as tool_result messages
        → go back to top
    no  → return final text response
```

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
for later logging steps.

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
=== BOUKENSHA Step 5: Agent Loop ===

Config: #<Boukensha::Config dir=/path/to/repo/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Max iterations: 25
Max output tokens: 1024

[iteration 1/25]
  tool call → list_directory({'path': '.'})
  tool result → README.md, examples, boukensha, prompts, requirements.txt

[iteration 2/25]
  tool call → read_file({'path': 'README.md'})
  tool result → # 05 · The Agent Loop (Python)...

=== FINAL RESPONSE ===
This is BOUKENSHA, a MUD player assistant framework. It can...
```

## Considerations

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

**`LoopError` is defined but unused.** It's carried over from the Ruby port
for parity — a future step may start raising it, and this keeps the two
codebases in sync in the meantime. The actual "runaway agent" protection
today is `_wrap_up`, not an exception.

## Considerations (carried over)

- Settings files must use `.yaml`, not `.yml`.
- No persistent memory or context compaction — the loop keeps appending
  messages for the whole turn; long-running turns grow the context
  unbounded within the `max_iterations` ceiling. That's a later step.
- No cost/usage logging wired into the loop yet, even though backends
  already expose `estimate_cost`/`context_window`.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader; also exposes `PROMPTS_DIR` |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container |
| `boukensha/registry.py` | `Registry` — registers and dispatches tools |
| `boukensha/errors.py` | `UnknownToolError`, `UnsupportedModelError`, `ApiError`, `LoopError` |
| `boukensha/tasks/` | Stateless task classes |
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization/parsing to a backend |
| `boukensha/backends/` | Per-provider payload/message/tool serialization and response normalization |
| `boukensha/client.py` | `Client` — sends the payload and parses the response |
| `boukensha/agent.py` | `Agent` — the tool-calling loop |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable smoke test — makes real, potentially multiple API calls |

## Run example

```bash
./week1_baseline/bin/python/05_agent_loop
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml` and makes **real, potentially multiple** network requests —
one per loop iteration — so it requires that provider's API key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or
`OLLAMA_API_KEY`) to be set in the environment or in `~/.boukensha/.env` —
`ollama` is the only provider that needs no key and no network access
beyond `localhost`.
