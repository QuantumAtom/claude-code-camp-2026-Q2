# 07 · The boukensha.run DSL (Python)

Python port of [`week1_baseline/ruby/07_the_run_dsl`](../../ruby/07_the_run_dsl/README.md).

## What this step adds

A single top-level entry point: `boukensha.run(...)`.

Every previous step required you to manually create and wire together a
`Context`, `Registry`, backend, `PromptBuilder`, `Client`, `Logger`, and
`Agent`. This step hides all of that behind one function call.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/07_the_run_dsl/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/run_dsl.py` | `RunDSL` — the tiny object passed into your `configure` callback so it can register tools |

## Updated files

| File | Change |
|---|---|
| `boukensha/__init__.py` | Adds `run()`, the top-level entry point; exports `RunDSL`; re-adds `LoopError` (removed in step 06, reinstated here for parity with the Ruby source) |
| `boukensha/config.py` | Re-adds `mud_host`/`mud_port`/`mud_username`/`mud_password` (removed in step 06, reinstated here — still unused) |
| `boukensha/errors.py` | Re-adds `LoopError` (still never raised) |
| `boukensha/logger.py` | Adds `turn(n=)` and `subscribe(callback)` — both unused by anything in this step |
| `examples/example.py` | Rewritten around `boukensha.run(...)` instead of manual wiring |

## The `configure` callback

Ruby's `Boukensha.run(task: ...) { ... }` passes a block that gets
`instance_eval`'d against a `RunDSL` — inside the block, `self` becomes the
`RunDSL`, so bare `tool "name", ...` calls resolve to `RunDSL#tool`. Python
has no equivalent to `instance_eval` — a closure's implicit `self` can't be
rebound.

The Python port's `boukensha.run(...)` instead takes a `configure` keyword
argument: an optional callback that receives the `RunDSL` instance
explicitly. Call `dsl.tool(...)` on it to register tools before the agent
runs:

```python
def register_tools(dsl):
    dsl.tool(
        "read_file",
        "Read a file from disk",
        {"path": {"type": "string", "description": "File path"}},
        lambda path: open(path).read(),
    )

result = boukensha.run(task="Read lib/boukensha.rb", configure=register_tools)
```

This mirrors the codebase's own existing convention for "blocks" —
`Registry.tool(name, description, parameters=None, block=None)` already
takes a plain callable rather than any DSL magic — so `RunDSL.tool` just
forwards to it:

```python
class RunDSL:
    def __init__(self, registry):
        self.registry = registry

    def tool(self, name, description, parameters=None, block=None):
        return self.registry.tool(name, description, parameters, block)
```

## `boukensha.run(...)`

Accepts keyword arguments that describe *what* to do. All plumbing is
handled internally.

| Option | Default | Description |
|---|---|---|
| `task` | *(required)* | The user message handed to the agent |
| `system` | task's system prompt (`prompts/system.md` or override) | System prompt |
| `model` | from `tasks.player.model` in `settings.yaml` | Model name |
| `backend` | from `tasks.player.provider` in `settings.yaml` | `"anthropic"`, `"openai"`, `"gemini"`, `"ollama"`, or `"ollama_cloud"` |
| `api_key` | matching `*_API_KEY` env var | Not needed for `"ollama"` |
| `ollama_host` | `"http://localhost:11434"` | Ollama base URL |
| `log` | `None` | Optional JSONL path override; default is `.boukensha/sessions/<session-id>.jsonl` |
| `max_output_tokens` | from `tasks.player.max_output_tokens` | Per-reply output cap |
| `configure` | `None` | Callback receiving a `RunDSL` — call `dsl.tool(...)` inside it to register tools |

## Before and after

**Step 06 — manual plumbing:**

```python
ctx = Context(task=Player, system=system_prompt)
registry = Registry(ctx)
backend = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model="claude-haiku-4-5")
builder = PromptBuilder(ctx, backend)
client = Client(builder)
logger = Logger()
agent = Agent(context=ctx, registry=registry, builder=builder, client=client, logger=logger)

registry.tool(
    "read_file", "Read a file",
    {"path": {"type": "string"}},
    lambda path: open(path).read(),
)

ctx.add_message("user", "Read lib/boukensha.rb")
agent.run()
```

**Step 07 — just describe what you want:**

```python
def register_tools(dsl):
    dsl.tool(
        "read_file", "Read a file",
        {"path": {"type": "string"}},
        lambda path: open(path).read(),
    )

result = boukensha.run(task="Read lib/boukensha.rb", configure=register_tools)
```

## `Logger`

| Method | Phase | Logs |
|---|---|---|
| `turn(n=)` | `turn` | *(new, unused by anything in this step — scaffolding)* |
| `iteration(n=, max=)` | `iteration` | loop counter |
| `limit_reached(kind=, n=, max=)` | `limit_reached` | iteration ceiling hit |
| `prompt(messages=, tools=)` | `prompt` | messages, tool names |
| `tool_call(name=, args=)` | `tool_call` | tool name and arguments |
| `tool_result(name=, result=, ok=, error=)` | `tool_result` | tool result, success/failure |
| `response(text=, usage=, stop_reason=, task=, backend=)` | `response` | response text, token usage, task/provider/model, estimated cost |
| `raw(data=)` | `raw` | raw provider response, only when `boukensha.debug()` is enabled |
| `turn_end(reason=, iterations=, tokens=)` | `turn_end` | why/when the turn ended |
| `subscribe(callback)` | — | registers a callback invoked with every logged event dict |
| `close()` | — | closes the underlying file handle |

`boukensha.run()` passes a `snapshot` into the `Logger` it constructs, so
every session's `session_start` line now also carries `task`,
`max_iterations`, `max_output_tokens`, `model`, and `provider` — previously
only set via the `Agent`'s own defaults, now visible from the very first
log line.

## Considerations

**`turn()`, `subscribe()`, `LoopError`, and `mud_*` are all present but
unused.** Same situation `quiet()`/`loud()`/`is_quiet()` were in at step
06 — ported for parity with the Ruby source, not yet exercised by anything
in this step. A later step will likely start using them.

**An unknown `backend` raises before any `Logger` is constructed**, so no
stray session file is created — `boukensha.run()` builds the backend
before constructing the `Logger`, and the function's `logger = None` +
`try/finally` only closes a logger that was actually opened.

## Considerations (carried over)

- Settings files must use `.yaml`, not `.yml`.
- No persistent memory or context compaction — the loop keeps appending
  messages for the whole turn; long-running turns grow the context
  unbounded within the `max_iterations` ceiling. That's a later step.
- `quiet()`/`loud()`/`is_quiet()` are still wired up but nothing reads
  them yet.
- The logger's file handle has no context-manager protocol; `boukensha.run()`
  closes it in a `finally`, but a caller building an `Agent` by hand
  (bypassing `boukensha.run()`) still owns closing it themselves.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader; also exposes `PROMPTS_DIR` |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container |
| `boukensha/registry.py` | `Registry` — registers and dispatches tools |
| `boukensha/errors.py` | `UnknownToolError`, `ApiError`, `LoopError`, `UnsupportedModelError` |
| `boukensha/tasks/` | Stateless task classes |
| `boukensha/prompt_builder.py` | `PromptBuilder` — delegates serialization/parsing to a backend |
| `boukensha/backends/` | Per-provider payload/message/tool serialization and response normalization |
| `boukensha/client.py` | `Client` — sends the payload and parses the response |
| `boukensha/agent.py` | `Agent` — the tool-calling loop |
| `boukensha/logger.py` | `Logger` — structured JSONL session logging |
| `boukensha/run_dsl.py` | `RunDSL` — the object passed into a `configure` callback |
| `boukensha/__init__.py` | Module-level state plus `run()`, the top-level entry point |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable smoke test — makes real, potentially multiple API calls |

## Run example

```bash
./week1_baseline/bin/python/07_the_run_dsl
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml` and makes **real, potentially multiple** network requests —
one per loop iteration — so it requires that provider's API key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or
`OLLAMA_API_KEY`) to be set in the environment or in `~/.boukensha/.env` —
`ollama` is the only provider that needs no key and no network access
beyond `localhost`.
