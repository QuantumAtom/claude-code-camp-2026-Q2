# 10 · A Standard Tool Library (Python)

Python port of [`week1_baseline/ruby/10_standard_tool_library`](../../ruby/10_standard_tool_library/README.md).

Boukensha now ships three built-in tool modules. Instead of manually
registering tools, a real coding harness gives the agent a standard library
of capabilities out of the box.

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/10_standard_tool_library/requirements.txt
```

One new third-party dependency: the official `mcp` SDK (`pip install mcp`,
already in `requirements.txt`) — it's what `file_system` and `shell` now run
on. `mud_manager` still needs nothing beyond the standard library
(`socket`, `threading`, `re`), the same as its Ruby counterpart.

## New files

| File | Description |
|---|---|
| `boukensha/tools/file_system.py` | Spawns `mcp_servers/file_system_server.py` and bridges its tools (`pwd`, `list_directory`, `read_file`, `write_file`, `delete_file`, `search_files`) into the Registry over MCP |
| `boukensha/tools/shell.py` | Spawns `mcp_servers/shell_server.py` and bridges `run_command` into the Registry over MCP |
| `boukensha/tools/mud.py` | 27 MUD-gameplay tools built on a live CircleMUD session — **not** MCP-based (see "Why file_system/shell but not mud" below) |
| `boukensha/mcp_client.py` | `McpClient` — a synchronous bridge to an MCP server over stdio, plus `register_mcp_tools()`, which discovers a server's tools and registers each into a boukensha `Registry` |
| `boukensha/mcp_servers/file_system_server.py` | The actual file-tool implementations, now living in a separate MCP server process |
| `boukensha/mcp_servers/shell_server.py` | The actual `run_command` implementation, now living in a separate MCP server process |
| `../../../week0_explore/mud_manager/python/mud_manager/` | Standalone `Session` (threaded telnet connection) + `primitives` (typed CircleMUD command builders) — Python's port of the Ruby `mud_manager` gem, since it has no PyPI package |

## Updated files

| File | Change |
|---|---|
| `boukensha/__init__.py` | `run()`/`repl()` gain `working_dir`, `allowed_commands`, `shell_timeout`, `mud` keyword arguments and auto-register the new tools |
| `boukensha/context.py` | Adds `working_dir` |
| `boukensha/repl.py` | Adds a `mud=` parameter and a `mud:` status line in the REPL banner |
| `boukensha/version.py` | `VERSION = "0.10.0"` |
| `examples/example.py` | Rewritten around a `boukensha.run(...)` MUD demo instead of the step 08 REPL/file-reading demo |

`boukensha/client.py` and `boukensha/config.py` are **not** touched by this
step — see "A note on parity with Ruby" below. Nor are `registry.py`,
`tool.py`, `agent.py`, or any file under `backends/` — see "MCP architecture"
directly below for why that's the point.

## MCP architecture

`file_system` and `shell` are MCP-based: each `register()` call spawns a
dedicated MCP server as a stdio subprocess (`mcp_servers/file_system_server.py`
/ `mcp_servers/shell_server.py`, built with the official SDK's `FastMCP`),
discovers its tools via `tools/list`, and registers each one into the
existing `Registry` — same `registry.tool(name, description, parameters,
block)` call every other tool in this codebase goes through, just with
`block` now calling out over MCP (`tools/call`) instead of running local
Python directly.

**Nothing about `Context`, `Registry`, `Tool`, `Agent`, `PromptBuilder`, or
any backend changed.** The Anthropic/OpenAI/Gemini/Ollama backends still
serialize `tool.parameters` into their API's tool schema exactly as before
— `mcp_client.register_mcp_tools()` is the one place that translates an
MCP tool's `inputSchema` (a full JSON Schema object) back into boukensha's
flat `{name: {"type":..., "description":...}}` shape, so nothing downstream
has to know or care that a tool's implementation now lives in a separate
process talking JSON-RPC over stdio instead of a local Python closure.

```
Agent.run() → Registry.dispatch("read_file", {...})
            → Tool.block(**args)                       # unchanged call shape
            → McpClient.call_tool("read_file", {...})  # NEW: bridges to...
            → mcp_servers/file_system_server.py          # ...a separate process
```

### The sync/async bridge

The official MCP SDK is asyncio-based (`ClientSession`, `stdio_client`);
`boukensha`'s `Agent`/`Registry` loop is fully synchronous. `McpClient` runs
the entire connect → serve → close lifetime as a single coroutine on a
dedicated background thread's event loop, and exposes plain blocking
`list_tools()`/`call_tool()`/`close()` methods that hand work to that loop
and wait for the result — conceptually the same "own the concurrency
internally, expose a synchronous interface" shape as `mud_manager.Session`'s
background reader thread, just built on `asyncio` instead of raw sockets.
(The whole session has to live in one coroutine because `anyio`'s cancel
scopes — which `ClientSession`/`stdio_client` use internally — require
`__aenter__`/`__aexit__` to happen in the same asyncio Task; entering and
exiting via two separately-scheduled coroutines raises a `RuntimeError` at
close time. Confirmed by hitting exactly that error against a throwaway
test server before settling on the single-coroutine-plus-stop-event design.)

### Why `file_system`/`shell` but not `mud`

MCP conversion here is scoped to `file_system` and `shell` only.
`tools/mud.py` stays a native Python registration: it wraps a single
long-lived, stateful `mud_manager.Session` (one login, one socket, shared
across every tool call for the life of the agent run) in a way that doesn't
map cleanly onto MCP's request/response tool-call model without either a
custom stateful MCP server of its own or significant redesign — and no
published MCP server for a custom CircleMUD exists to point at instead.
Converting it was considered and explicitly deferred, not overlooked.

## `boukensha.tools.file_system`

The evolution of the read/list tools every prior step registered manually —
same five, plus one new one. Registers automatically when `working_dir` is
set:

| Tool | Description |
|------|-------------|
| `pwd` | Return the working directory |
| `list_directory` | List files at a path (default `.`) |
| `read_file` | Read a file's contents |
| `write_file` | Write (or create) a file |
| `delete_file` | Delete a file |
| `search_files` | **New** — grep for a regex pattern across the working tree, returns `path:line:content` matches |

All paths are **relative to the working directory**. Absolute paths and `..`
traversals that escape the root are rejected with an `error: ...` string,
not an exception. The sandboxing logic (`_resolve`, the traversal check)
lives in `mcp_servers/file_system_server.py` now, not `tools/file_system.py`
— `tools/file_system.py` just spawns that server and passes it the root
directory via the `BOUKENSHA_MCP_FS_ROOT` environment variable.

## `boukensha.tools.shell`

Registers automatically when `working_dir` is set:

| Tool | Description |
|------|-------------|
| `run_command` | Run a shell command inside the working directory |

Commands run with a configurable timeout and an optional allow-list of
permitted executables. `run_command` runs the given string through a shell
(`subprocess.run(..., shell=True)`), the same as any shell prompt would —
the `allowed_commands` allow-list is the intended guardrail, not a sandbox;
it only checks the command's first whitespace-split token. Like
`file_system`, the actual logic lives in `mcp_servers/shell_server.py`,
configured via `BOUKENSHA_MCP_SHELL_ROOT`/`_TIMEOUT`/`_ALLOWED` environment
variables passed to the subprocess.

## `boukensha.tools.mud`

New module — the biggest addition in this step. Registers automatically
when `mud` connection details are available (explicitly passed, or read
from `.boukensha/settings.yaml`'s `mud:` block). A single session is opened
once and shared by every tool call.

| Tool | Description |
|------|-------------|
| `mud_connect` / `mud_disconnect` / `mud_status` | Manage the connection |
| `look` / `examine` / `check` | Perception — room, target detail, self-info (score, inventory, exits, ...) |
| `move` / `flee` / `set_position` / `track` | Movement |
| `attack` / `skill_strike` / `consider` | Combat |
| `say` / `tell` / `channel_say` | Communication |
| `get_item` / `drop_item` / `put_item` / `equip_item` / `consume_item` | Inventory & equipment |
| `cast_spell` / `use_magic_item` | Magic |
| `shop` / `practice` / `save_character` / `send_raw` | Utility (`send_raw` is an escape hatch for anything not covered by a structured tool) |

The session auto-connects at registration time so the agent doesn't waste a
turn calling `mud_connect` first; if the MUD server is unreachable at
startup, a warning is printed to stderr and every tool call returns
`"error: not connected — call mud_connect first"` until `mud_connect`
succeeds.

## New `boukensha.run` / `boukensha.repl` keyword arguments

```python
boukensha.run(
    task="...",
    working_dir="/my/project",
    allowed_commands=["python3", "git"],  # None = allow all (default)
    shell_timeout=30,                     # seconds, default 30
    mud={"host": "localhost", "port": 4000, "name": "...", "password": "..."},
)
```

- `working_dir` defaults to the caller's current working directory;
  `working_dir=False` disables `file_system`/`shell` registration entirely.
- `allowed_commands=None` permits any executable; pass a list to lock the
  agent down.
- `mud=None` (the default) falls back to `.boukensha/settings.yaml`'s
  `mud:` block if it has a `host` and `username`; `mud=False` disables MUD
  tooling entirely; an explicit dict overrides config.

## Direct registration

All three modules can be registered manually for finer control:

```python
from boukensha.tools import file_system, shell, mud

file_system.register(registry, working_dir="/my/project")
shell.register(registry, working_dir="/my/project", timeout=10, allowed_commands=["python3"])
mud.register(registry, host="localhost", port=4000, name="...", password="...")
```

`file_system.register()`/`shell.register()` each spawn a subprocess and
return the `McpClient` handle for it (`mud.register()` doesn't — it's not
MCP-based, and returns `None`). Every `McpClient` registers an `atexit`
handler that closes its session and subprocess, so a normal process exit
cleans up automatically; hang on to the returned handle and call
`.close()` yourself if you need the subprocess gone sooner (e.g. a
long-running REPL where you want to free the process without exiting).

## A note on parity with Ruby

Ruby's own history between step 08 and step 10 includes an intermediate
step (`09_global_executable`, packaging the framework as an installed gem)
that Python has no counterpart for. That step accidentally **reverted** two
fixes Ruby step 08 had already made — the 401-specific `ApiError` message
in `Client.call`, and the 3-step `.boukensha` directory lookup in
`Config#resolve_dir` — and Ruby step 10 never restored them. Python's
`client.py` and `config.py` already have both fixes correctly (ported in
step 08) and are **not** regressed to match Ruby 10's current state — this
step makes no changes to either file.

## Considerations

- Settings files must use `.yaml`, not `.yml`.
- No persistent memory or context compaction across turns.
- `run_command`'s `allowed_commands` allow-list checks only the first
  whitespace-split token, not shell syntax — a compound command that
  starts with an allowed executable can still do anything after a `;`,
  `&&`, or subshell. This is the documented threat model for this tool
  (matches Ruby exactly), not a Python-specific weakness.
- `file_system`'s path-traversal check is lexical only (mirrors Ruby's
  `File.expand_path`, which does not resolve symlinks) — a symlink inside
  the working directory pointing outside it is not blocked.
- The `mud_manager` Python package has no reconnect/retry logic beyond what
  `Session.login()` does for the CircleMUD menu dance.
- Each `boukensha.run(...)`/`boukensha.repl(...)` call with `working_dir`
  set spawns two subprocesses (the file-system and shell MCP servers) that
  live for the duration of that call and are cleaned up via `atexit` on
  normal exit. A process that calls `run()` many times in a loop (rather
  than once, or via the REPL, which registers tools once for the whole
  session) will accumulate one pair of subprocesses per call unless it
  captures and closes the returned `McpClient` handles itself.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader; also exposes `PROMPTS_DIR` and `mud_*` accessors |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container (now also holds `working_dir`) |
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
| `boukensha/tools/file_system.py` | Spawns the file-system MCP server and bridges its tools into the Registry |
| `boukensha/tools/shell.py` | Spawns the shell MCP server and bridges `run_command` into the Registry |
| `boukensha/tools/mud.py` | MUD gameplay tools (native Python, not MCP-based) |
| `boukensha/mcp_client.py` | `McpClient` — sync bridge to an MCP server over stdio; `register_mcp_tools()` |
| `boukensha/mcp_servers/file_system_server.py` | The file tool implementations, as an MCP server |
| `boukensha/mcp_servers/shell_server.py` | The `run_command` implementation, as an MCP server |
| `boukensha/version.py` | `VERSION` |
| `boukensha/__init__.py` | Module-level state plus `run()` and `repl()`, the top-level entry points |
| `prompts/system.md` | Default system prompt |
| `examples/example.py` | Runnable MUD demo — makes real, potentially multiple API calls, and connects to a live CircleMUD server |

## Run the demo

```bash
./week1_baseline/bin/python/10_standard_tool_library
```

Requires a reachable CircleMUD server at the `mud:` host/port configured in
`.boukensha/settings.yaml`, and (like every prior step) the API key for
whichever provider `tasks.player.provider` names.

## Technical considerations

- `mud_manager` has no PyPI package, so `boukensha/tools/mud.py` resolves
  it via a `sys.path` insert pointing at the sibling
  `week0_explore/mud_manager/python/` directory rather than a
  package-manager dependency — Ruby's equivalent hardcodes a `path:` gem
  dependency in its `Gemfile` for the same reason.
- Porting the threaded `Session` (background reader thread, telnet IAC
  stripping, condition-variable-based prompt waiting) is the highest-risk
  part of this step — it was verified against a live server, not just
  read through, since concurrency bugs here would be timing-dependent and
  easy to miss in a casual test.
- Ruby's own `examples/example.rb` for this step calls `Boukensha.run(...)`
  but never prints its return value, so running it as-is shows nothing of
  the actual MUD interaction. Every other one-shot Python demo in this
  series (`07_the_run_dsl`, etc.) prints `result` after the call — Python's
  `example.py` restores that and prints the final response, rather than
  copying the upstream omission.
