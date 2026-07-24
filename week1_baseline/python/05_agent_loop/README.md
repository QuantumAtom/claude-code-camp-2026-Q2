# 04 · The API Client (Python)

Python port of [`week1_baseline/ruby/04_api_client`](../../ruby/04_api_client/README.md).

The API Client takes the payload assembled by `PromptBuilder` and sends it to
the API. One HTTP POST, one response. No tool loop yet — just proving the
round trip works.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/04_api_client/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/client.py` | Makes the HTTP request and parses the response |
| `boukensha/backends/base.py` | Shared backend model validation and model metadata helpers |
| `boukensha/tasks/base.py` | Shared task configuration helpers for provider, model, and prompts |
| `boukensha/tasks/player.py` | Player task definition |
| `prompts/system.md` | Default system prompt used when the player task does not override it |

## Updated files

| File | Change |
|---|---|
| `boukensha/errors.py` | Added `ApiError` for failed HTTP requests |
| `boukensha/tasks/base.py` | Error messages now say `settings.yaml` (not `settings.yml`); `_fetch` guards against non-dict `settings` |
| `prompts/system.md` | New default prompt text (CircleMUD framing, was the earlier "MUD player assistant" wording) |
| `boukensha/backends/*.py` | Unchanged from Step 3 — already own supported model tables with context windows and cost metadata |

## How it works

```
PromptBuilder
      ↓
Client
      ↓
POST to API endpoint
      ↓
Raw JSON response
```

## `Client`

| Method | Description |
|---|---|
| `call(max_output_tokens=1024)` | POSTs the payload and returns the parsed JSON response |

`Client` retries transient network failures and a fixed set of retryable
HTTP status codes (`408, 409, 429, 500, 502, 503, 504`) with exponential
backoff (`0.5s, 1s, 2s`), up to 3 retries (4 attempts total). If every
attempt fails — or the final response still isn't 2xx — it raises
`ApiError` with the attempt count and either the underlying exception or the
response status/body.

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
```

When `prompt_override.system` is true, Boukensha reads
`.boukensha/prompts/player/system.md`. Otherwise it falls back to this
step's shipped `prompts/system.md`, located via `Config.PROMPTS_DIR`.

Each backend validates the configured model at construction time.
Unsupported model names raise `UnsupportedModelError`, and supported models
expose backend-owned metadata such as `context_window`, `usage_unit`, and
token cost estimates for later logging steps.

## No dependencies

`Client` uses Python's standard `http.client` module — no `requests`, no
new entry in `requirements.txt`. This mirrors the Ruby implementation's
deliberate choice to use `net/http` instead of a gem: the HTTP call itself
is trivial and should stay visible, not hidden behind a library.

`http.client` was chosen over `urllib.request` specifically because
`urlopen` raises an exception on any non-2xx response by default, which
would fight against `Client`'s own status-code-based retry/error logic.
`http.client.HTTPConnection`/`HTTPSConnection` behave like Ruby's
`Net::HTTP`: they hand back a response object regardless of status code and
let the caller decide what to do with it.

### SSL and timeouts — two small, deliberate differences from Ruby

The Ruby README warns that hardcoding
`OpenSSL::X509::DEFAULT_CERT_FILE` for the SSL certificate broke on
Linux/WSL2, and tells the reader to work around it manually for their own
machine. **The Python port has no equivalent problem to work around** —
`ssl.create_default_context()` locates the platform's trust store
automatically everywhere Python runs, so there's nothing to configure.

Separately, `Client` sets an explicit 60-second timeout on every
connection. Ruby gets a 60-second open/read timeout "for free" from
`Net::HTTP`'s defaults without ever writing the number down; Python's
`http.client` has no default timeout at all (it will block forever), so
the port makes the equivalent value explicit instead of silently
inheriting an infinite wait.

## Known Ruby-side quirk this port does *not* reproduce

Ruby 04's `Config::PROMPTS_DIR` is computed with one extra `../` compared
to Step 3 and resolves to a directory that doesn't exist on disk (one level
above the project root). It's silently masked today because the shipped
`settings.yaml` always sets `prompt_override.system: true`, so the default
prompt path never actually gets exercised — but if that override were ever
turned off, Ruby's default system prompt would fail to load.

Python's `Config.PROMPTS_DIR` is computed from `Path(__file__).resolve()`
rather than a hand-counted relative-path string, so it already resolves
correctly to this package's own `prompts/` directory with no changes
needed. This is a deliberate, favorable divergence — not a bug to go
"fix" into matching Ruby.

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
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization to a backend |
| `boukensha/backends/` | Per-provider payload/message/tool serialization |
| `boukensha/client.py` | `Client` — sends the payload and parses the response |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable smoke test — makes a real API call |

## Run example

```bash
./week1_baseline/bin/python/04_api_client
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml` and makes a **real** network request, so it requires that
provider's API key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`, or `OLLAMA_API_KEY`) to be set in the environment or in
`~/.boukensha/.env` — `ollama` is the only provider that needs no key and
no network access beyond `localhost`.

Example output shape (the exact response content depends on the live model
call and will vary run to run):

```text
=== BOUKENSHA Step 4: API Client ===

Config: #<Boukensha::Config dir=/path/to/repo/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Sending request to https://api.anthropic.com/v1/messages...

Raw response:
{
  "id": "msg_01XY",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "text", "text": "..." }
  ],
  "stop_reason": "end_turn",
  "usage": { "input_tokens": 42, "output_tokens": 18 }
}
```

## What the response looks like

The raw response shape differs between backends. This is what you get back
from `client.call()` before any processing:

### Anthropic
```json
{
  "id": "msg_01XY",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "text", "text": "Sure, let me read that file." }
  ],
  "stop_reason": "end_turn",
  "usage": { "input_tokens": 42, "output_tokens": 18 }
}
```

### Ollama
```json
{
  "model": "llama3.2",
  "message": {
    "role": "assistant",
    "content": "Sure, let me read that file."
  },
  "done_reason": "stop",
  "done": true
}
```

When the model wants to call a tool the response looks different. Anthropic
uses `stop_reason: "tool_use"` and adds a `tool_use` block to `content`.
Ollama adds a `tool_calls` array to `message`. Handling those differences is
the job of Step 5 — the Agent Loop.

## Considerations

**The client raises `ApiError` on failure.** A non-2xx response means
something went wrong — bad API key, malformed payload, server error.
BOUKENSHA surfaces this explicitly rather than returning a confusing `None`
or partial response.

**Transient failures get a few retries, not infinite ones.** Connection
resets, DNS hiccups, and a handful of well-known "try again" HTTP status
codes get retried with exponential backoff; anything else — including any
non-retryable 4xx — fails immediately.

## Considerations (carried over)

- Still no tool-call loop — the response may say the model wants to use a
  tool, but nothing here reads that and actually dispatches it. That's
  Step 5.
- `Client` performs one POST and returns the raw parsed JSON; no streaming,
  no multi-turn orchestration yet.
- Settings files must use `.yaml`, not `.yml`.
- The default prompt is scoped per task via `Config.PROMPTS_DIR` and
  `user_prompts_dir`, resolved through `Tasks::Base.system_prompt`.
