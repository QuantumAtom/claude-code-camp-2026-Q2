# 08 · The REPL Loop (Python)

Python port of [`week1_baseline/ruby/08_the_repl_loop`](../../ruby/08_the_repl_loop/README.md).

## What this step adds

| | Step 07 | Step 08 |
|---|---|---|
| Entry point | `boukensha.run(task=...)` | `boukensha.repl(...)` |
| Turns | one | many |
| History | discarded | accumulates across turns |
| User interaction | none | stdin prompt |

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/08_the_repl_loop/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/repl.py` | `Repl` — the interactive session loop |
| `boukensha/version.py` | `VERSION` — shown in the REPL banner |

## Updated files

| File | Change |
|---|---|
| `boukensha/__init__.py` | Adds `repl()`, the interactive entry point; exports `VERSION` and `Repl` |
| `boukensha/agent.py` | `Agent.run()` now persists the final reply to `Context` before returning (see below) |
| `boukensha/client.py` | A `401` response now raises `ApiError("authentication failed (401) — check your API key")` instead of the generic failure message |
| `boukensha/config.py` | `Config._resolve_dir` gains a step: a `.boukensha/` directory in the current working directory is now checked before falling back to `~/.boukensha` |
| `boukensha/context.py` | Adds `clear_messages()` — wipes conversation history, keeps tools registered |
| `examples/example.py` | Rewritten around `boukensha.repl(...)` instead of a single `boukensha.run(...)` call |

## `Repl`

The interactive session loop. Built-in commands:

| Command | Effect |
|---|---|
| `/quiet` | Suppress logging output |
| `/loud` | Re-enable logging output |
| `/clear` | Wipe conversation history (tools stay registered) |
| `/help` | Print the command list |
| `/exit` / `/quit` | Leave the REPL |
| Ctrl-D | EOF — leave the REPL |
| Ctrl-C | Interrupt — leave the REPL gracefully |

## `boukensha.repl(...)`

Same signature as `boukensha.run(...)`, minus `task`. Register tools via
`configure`; then the REPL loop takes over and reads tasks from stdin.

```python
def register_tools(dsl):
    dsl.tool(
        "read_file",
        "Read a file from disk",
        {"path": {"type": "string", "description": "File path"}},
        lambda path: open(path).read(),
    )

boukensha.repl(model="claude-haiku-4-5", configure=register_tools)
```

## Changes from step 07

### `Context.clear_messages()`

Wipes `self.messages` while keeping tools registered. Used by the REPL's
`/clear` command.

### `Agent.run()` — persists the final reply

Before step 08, the agent returned the final text without adding it to the
context. That was fine for one-shot `run()` calls (the context is thrown
away afterward anyway), but a REPL reuses the same `Context` across every
turn, so it needs the full transcript — including the model's own prior
replies — or each new turn's prompt would only contain the user's messages
and tool-call/tool-result pairs, never what the assistant actually said.

```python
# step 07 — final text returned but NOT added to context
return text

# step 08 — final text added to context, then returned
self.context.add_message("assistant", text)
return text
```

This applies at all three exit points of `Agent.run()`: the normal
completion path, and both branches (success and `ApiError`) of the
iteration-limit `_wrap_up`.

### `Logger.turn(n=)` is now actually called

`turn()` has existed since step 07 as unused scaffolding. `Repl._run_turn`
now calls it once per REPL turn, logging a `phase: "turn"` JSONL event —
this only writes to the session log, it does not print anything to the
console.

### `Client.call` — specific 401 error

A `401` response now raises
`ApiError("authentication failed (401) — check your API key")` instead of
falling through to the generic `"API request failed..."` message —
easier to diagnose a bad/missing API key at a glance.

### `Config._resolve_dir` — checks the working directory

The `.boukensha` config directory is now resolved in three steps instead
of two:

1. `BOUKENSHA_DIR` environment variable (unchanged)
2. **New:** `.boukensha/` in the current working directory, if it exists as a directory
3. `~/.boukensha` (default, unchanged)

This applies to every entry point that calls `boukensha.config()`
internally (`run()`, `repl()`, or a bare `boukensha.config()` call), not
just the REPL — running from a directory that happens to have its own
`.boukensha/` subfolder now picks that up automatically.

## Considerations

- Settings files must use `.yaml`, not `.yml`.
- No persistent memory or context compaction — a long-running interactive
  session keeps appending messages to `Context.messages` for as long as
  the REPL stays open (until `/clear` is used); nothing summarizes or
  trims older turns. That's a later step.
- `quiet()`/`loud()`/`is_quiet()` can now be toggled interactively via
  `/quiet` and `/loud`, but nothing in this step actually branches on
  `is_quiet()` to suppress output — same situation as steps 06–07, just
  now reachable from the REPL prompt.
- `Logger.subscribe()` is still never called by anything in this step.
- The logger's file handle has no context-manager protocol; `boukensha.repl()`
  closes it in a `finally`, but a caller building an `Agent`/`Repl` by
  hand (bypassing `boukensha.repl()`) still owns closing it themselves.
- An unknown `backend` still raises before any `Logger` is constructed, so
  no stray session file is created — same `logger = None` + `try/finally`
  nil-safety as `run()`.

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
| `boukensha/repl.py` | `Repl` — the interactive session loop |
| `boukensha/version.py` | `VERSION` |
| `boukensha/__init__.py` | Module-level state plus `run()` and `repl()`, the top-level entry points |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable interactive session — makes real, potentially multiple API calls |

## Run example

```bash
./week1_baseline/bin/python/08_the_repl_loop
```

This builds the backend named by `tasks.player.provider` in
`settings.yaml` and makes **real** network requests, one per agent
iteration per turn — so it requires that provider's API key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, or
`OLLAMA_API_KEY`) to be set in the environment or in `~/.boukensha/.env` —
`ollama` is the only provider that needs no key and no network access
beyond `localhost`.

```
╔══════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v0.8.0)    ║
╚══════════════════════════════════════╝
  config:    /home/you/.boukensha
  provider:  anthropic (claude-haiku-4-5)  ✓ API key set

  /quiet or /loud   toggle logging
  /clear           reset conversation history
  /exit or /quit    leave the REPL

boukensha> list the files in the lib directory
…
boukensha> now read boukensha/agent.py and explain the loop
…
boukensha> /quiet
(logging suppressed — type /loud to re-enable)
boukensha> what was the first file I asked you about?
…
boukensha> /exit
Goodbye.
```

The last question demonstrates persistent history: the agent answers from
the accumulated transcript, not just the last message.
