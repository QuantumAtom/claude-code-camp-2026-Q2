# 03 · The Prompt Builder (Python)

Python port of [`week1_baseline/ruby/03_prompt_builder`](../../ruby/03_prompt_builder/README.md).

Because LLM access, cost, and quality are constantly changing, we want to be
able to switch between multiple LLMs that will drive the agent loop.

There are several SDKs that provide access to many LLMs but in practice we
only really need to focus on top-tier models:
- anthropic family
- openai family
- gemini family
- ollama cloud eg. kimi, minimax, llama

The Prompt Builder serializes `Context` into the exact format each API
expects. `PromptBuilder` delegates to whichever backend you pass in.

`PromptBuilder` does not call the API — it only prepares the payload, headers,
and URL for the eventual HTTP call. (An API-calling module comes in a later
step.)

Configuration is task-based here, carried forward from the registry step. The
`player` task owns its provider, model, and prompt override settings, and the
context records the task that the prompt is being built for.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/03_prompt_builder/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/prompt_builder.py` | Delegates serialization to the active backend |
| `prompts/system.md` | Default system prompt used when a task does not override it |
| `boukensha/backends/base.py` | Shared backend contract for model validation and model metadata |
| `boukensha/backends/anthropic.py` | Serializes context into the Anthropic API format |
| `boukensha/backends/ollama.py` | Serializes context into the Ollama API format |
| `boukensha/backends/ollama_cloud.py` | Serializes context into the Ollama Cloud API format |
| `boukensha/backends/openai.py` | Serializes context into the OpenAI Chat Completions format |
| `boukensha/backends/gemini.py` | Serializes context into the Gemini `generateContent` format |

## How it works

```
Context (Python objects)
        ↓
PromptBuilder
        ↓
Backend (Anthropic, OpenAI, Gemini, or Ollama)
        ↓
API payload (plain dicts and lists)
        ↓
POST to API
```

## `PromptBuilder`

| Method | Description |
|---|---|
| `to_messages()` | Delegates message serialization to the backend |
| `to_tools()` | Delegates tool serialization to the backend |
| `to_api_payload(max_output_tokens=1024)` | Assembles the complete payload ready to POST |
| `headers()` | Returns the correct headers for the backend |
| `url()` | Returns the correct endpoint URL for the backend |

## Backends

Each API has its own conventions for how data is expected. Anthropic and
Gemini are the most alike (system prompt as a top-level field), while OpenAI
and Ollama share the same `function`-wrapped tool schema.

Backends also own their supported model table. A backend refuses to
initialize with an unknown model, so `settings.yaml` cannot silently select
an unsupported or misspelled model, raising `UnsupportedModelError` instead.
Each model entry carries:

| Key | Meaning |
|---|---|
| `context_window` | The model's known token context window |
| `cost_per_million["input"]` | USD input token price per million tokens, when known |
| `cost_per_million["output"]` | USD output token price per million tokens, when known |
| `usage_unit` | `"tokens"`, `"local_compute"`, or `"ollama_cloud_usage"` |
| `usage_level` | Ollama Cloud usage tier, when applicable |

Backend instances expose `context_window`, `input_token_cost_per_million`,
`output_token_cost_per_million`, `usage_unit`, `usage_level`, and
`estimate_cost(input_tokens, output_tokens)`. For local Ollama models, token
API cost is `0.0`. For Ollama Cloud, public pricing is plan/usage based
rather than token based, so `estimate_cost` returns `None`.

The prices in this step are static tutorial data, current as of June 16,
2026, and should be reviewed whenever the selected model set changes.

### `Anthropic`

Talks to `https://api.anthropic.com/v1/messages`.
Requires an `ANTHROPIC_API_KEY`. Supported models are listed in
`Anthropic.MODELS`.

### `Ollama`

Talks to `http://localhost:11434/api/chat`.
Requires `ollama serve` running locally. No API key needed. Supported models
are listed in `Ollama.MODELS`.

### `OllamaCloud`

Talks to `https://ollama.com/api/chat`. Requires an `OLLAMA_API_KEY`.
Supported models are listed in `OllamaCloud.MODELS`.

### `OpenAI`

Talks to `https://api.openai.com/v1/chat/completions`.
Requires an `OPENAI_API_KEY`. Supported models are listed in
`OpenAI.MODELS`.

### `Gemini`

Talks to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
Requires a `GEMINI_API_KEY`. Supported models are listed in `Gemini.MODELS`.

### System prompt

Anthropic and Gemini send the system prompt as a top-level field, separate
from the messages array. Ollama and OpenAI put it inside the messages array
as a `role: system` message.

```json
// Anthropic
{ "system": "You are a MUD player assistant.", "messages": [ ... ] }

// Gemini
{ "systemInstruction": { "parts": [{ "text": "You are a MUD player assistant." }] }, "contents": [ ... ] }

// Ollama / OpenAI
{ "messages": [ { "role": "system", "content": "You are a MUD player assistant." }, ... ] }
```

### Tool results

Anthropic wraps tool results in a user message. Ollama and OpenAI use their
own `role: tool` message type (with slightly different identifier fields).
Gemini wraps results in a `functionResponse` part on a `user` message.

```json
// Anthropic
{ "role": "user", "content": [{ "type": "tool_result", "tool_use_id": "toolu_01X", "content": "A damp stone corridor stretches north. Torches flicker on the walls." }] }

// Ollama
{ "role": "tool", "tool_name": "look", "content": "A damp stone corridor stretches north. Torches flicker on the walls." }

// OpenAI
{ "role": "tool", "tool_call_id": "toolu_01X", "content": "A damp stone corridor stretches north. Torches flicker on the walls." }

// Gemini
{ "role": "user", "parts": [{ "functionResponse": { "name": "toolu_01X", "response": { "content": "A damp stone corridor stretches north. Torches flicker on the walls." } } }] }
```

### Tool definitions

Anthropic uses `input_schema`. Ollama and OpenAI wrap everything in a
`function` envelope with `parameters`. Gemini wraps tools in a
`functionDeclarations` array.

```json
// Anthropic
{ "name": "move", "description": "Move the player in a direction (north, south, east, west, up, down)", "input_schema": { "type": "object", "properties": { "direction": { "type": "string", "description": "The direction to move" } }, "required": ["direction"] } }

// Ollama / OpenAI
{ "type": "function", "function": { "name": "move", "description": "Move the player in a direction (north, south, east, west, up, down)", "parameters": { "type": "object", "properties": { "direction": { "type": "string", "description": "The direction to move" } }, "required": ["direction"] } } }

// Gemini
{ "functionDeclarations": [ { "name": "move", "description": "Move the player in a direction (north, south, east, west, up, down)", "parameters": { "type": "object", "properties": { "direction": { "type": "string", "description": "The direction to move" } }, "required": ["direction"] } } ] }
```

### Message roles

Anthropic, Ollama, and OpenAI all use `assistant` for the model's turn.
Gemini calls it `model`.

```json
// Anthropic / Ollama / OpenAI
{ "role": "assistant", "content": "Let me take a look around first." }

// Gemini
{ "role": "model", "parts": [{ "text": "Let me take a look around first." }] }
```

## Configuration compatibility

The Python and Ruby implementations read the same `.boukensha/` directory.
Resolution order is:

1. `BOUKENSHA_DIR`
2. `~/.boukensha`

The shared directory supports the same `settings.yaml`, `.env`, and
`prompts/<task>/system.md` override layout. `Config.PROMPTS_DIR` points at
this package's own shipped `prompts/` directory, used as the fallback when a
task doesn't override its prompt.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader; also exposes `PROMPTS_DIR` |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container |
| `boukensha/registry.py` | `Registry` — registers and dispatches tools |
| `boukensha/errors.py` | `UnknownToolError`, `UnsupportedModelError` |
| `boukensha/tasks/` | Stateless task classes |
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization to a backend |
| `boukensha/backends/` | Per-provider payload/message/tool serialization |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable smoke test |

## Run example

```bash
./week1_baseline/bin/python/03_prompt_builder
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml`, so it requires that provider's API key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or
`OLLAMA_API_KEY`) to be set in the environment or in `~/.boukensha/.env` —
`ollama` is the only provider that needs no key. A missing key raises
immediately when the backend is constructed, before any payload is built.

Expected output shape, with the config directory and exact payload
depending on the configured provider/model:

```text
=== BOUKENSHA Step 3: Prompt Builder ===

Config: #<Boukensha::Config dir=/path/to/repo/.boukensha tasks=player>
Provider: gemini
Model: gemini-3.1-flash-lite
{
  "systemInstruction": { "parts": [{ "text": "..." }] },
  "contents": [ ... ],
  "tools": [ { "functionDeclarations": [ ... ] } ],
  "generationConfig": { "maxOutputTokens": 1024 }
}
```

## Considerations

**The conversation is stateless.** The model has no memory between turns.
Every API call includes the entire history from the beginning. BOUKENSHA is
responsible for carrying that state.

**Tool results are user messages on Anthropic.** This feels
counterintuitive — the result came from BOUKENSHA, not the human — but it
reflects how the Anthropic API models the conversation. Ollama, OpenAI, and
Gemini all handle this with dedicated message/part types instead.

**The agent only sees schemas.** The `description` field on each tool is the
only thing the agent uses to decide which tool to call. The actual block
never leaves BOUKENSHA.

**Ollama's payload ignores `max_output_tokens`.** Both `Ollama` and
`OllamaCloud` accept the argument (for a consistent `to_payload` signature
across backends) but never include it in the request body — this matches
the Ruby backend exactly, not an oversight in the port.

## Considerations (carried over)

- The default prompt is now scoped per task via `Config.PROMPTS_DIR` and
  `user_prompts_dir`, resolved through `Tasks::Base.system_prompt`.
- Settings files must use `.yaml`, not `.yml`.
- There's still no real agent decision loop — `example.py` hand-picks the
  backend and hand-seeds the conversation to simulate what an agent would
  eventually decide to do.
- `PromptBuilder`/backends only serialize payloads; nothing in this step
  performs an actual HTTP request. That wiring is a later step.
