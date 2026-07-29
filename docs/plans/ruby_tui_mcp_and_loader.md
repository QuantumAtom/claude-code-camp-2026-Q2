# Ruby TUI Delta Plan — MCP tool transport + self-locating loader discipline

## Goal

Bring `week1_baseline/ruby/11_tui` up to parity with the MCP-based tool
architecture that `week1_baseline/python/10_standard_tool_library` already
has, and make sure the subprocess-spawning that architecture requires is
resolved the same self-locating, cwd-independent way
`lib/boukensha_loader.rb` already resolves `BOUKENSHA_PATH`/`~/.boukensharc`.
**Plan only — no source files are touched by writing this document.**

**This plan only covers what's missing between Ruby 11_tui and the Python
MCP work.** Everything else in `11_tui` (the charm-ruby TUI itself, the
agent loop, backends, config, the MUD tool suite) stays exactly as it is.

## Why this is needed (source of truth)

Confirmed via direct inspection, not assumption:

| Claim | Evidence |
|---|---|
| Ruby has **no** MCP code anywhere, in `10_standard_tool_library` or `11_tui` | `grep -rli mcp week1_baseline/ruby/{10_standard_tool_library,11_tui}` — zero real hits (two `memcpy` false positives in the bubbletea C patch, not MCP) |
| Python's MCP work is real and already merged | `week1_baseline/python/10_standard_tool_library/boukensha/mcp_client.py` + `boukensha/mcp_servers/{file_system_server,shell_server}.py`, added in commit `3539a64` ("...made an MCP exclusively for the Python port") |
| MCP was **deliberately** kept Python-only up to now | Commit message says so explicitly; this plan is the first step in extending it to Ruby |
| `11_tui`'s loader is already correct and needs no functional change on its own | `diff week1_baseline/ruby/{10_standard_tool_library,11_tui}/lib/boukensha_loader.rb` — the only difference is the pre-existing `--no-tui` flag; `registry.rb`, `tool.rb` are byte-identical between the two steps |
| `tools/file_system.rb` and `tools/shell.rb` in `11_tui` are still the pre-MCP, in-process closure implementation | Read directly — same shape as Python's *pre-MCP* `tools/file_system.py`/`tools/shell.py`, which the Python plan's own comments describe as "identical... only the transport changed" |
| A Ruby MCP SDK gem exists and is a close mirror of Python's `mcp` package | `gem info mcp -r` → `mcp (1.0.0)`, "The official Ruby SDK for Model Context Protocol servers and clients," homepage `ruby.sdk.modelcontextprotocol.io`. Unpacked and inspected directly (see below) — it has both `MCP::Client` (with a **synchronous**, `Open3.popen3`-based `MCP::Client::Stdio` transport) and `MCP::Server` (with `MCP::Server::Transports::StdioTransport`) |

### Why this only touches `file_system`/`shell`, not `mud`

Python's own MCP plan only moved `tools/file_system.py` and `tools/shell.py`
behind MCP servers; `tools/mud.py` stayed an in-process wrapper around
`mud_manager`. This plan mirrors that scope exactly — `lib/boukensha/tools/mud.rb`
is **out of scope**, unchanged.

## Key finding: Ruby's MCP transport is synchronous — no asyncio-bridge needed

Python's `mcp_client.py` has to run a whole background thread with its own
`asyncio` event loop, because the official Python MCP SDK is asyncio-only
and boukensha's `Registry`/`Agent` loop is synchronous. That bridge
(`_session_main`, `_run`, `asyncio.run_coroutine_threadsafe`, a `Ready`/`Event`
handshake) is the most complex part of `mcp_client.py`.

**Ruby's `MCP::Client::Stdio` (in the `mcp` gem) is already synchronous** —
it's built directly on `Open3.popen3` + blocking `IO#gets`, with a single
background thread only to drain the child's stderr pipe (so it can't fill up
and deadlock the child). There is no event loop to bridge. `lib/boukensha/mcp_client.rb`
is therefore **simpler** than its Python counterpart, not a line-for-line
port of the asyncio bridge — it's a thin wrapper around `MCP::Client.new(transport:)`.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `lib/boukensha/mcp_client.rb` — spawns an MCP server over stdio, discovers
  its tools, registers each into a boukensha `Registry` (mirrors
  `mcp_client.py`'s `register_mcp_tools`, without the asyncio bridge)
- `lib/boukensha/mcp_servers/file_system_server.rb` — `MCP::Server` exposing
  `pwd`/`list_directory`/`read_file`/`write_file`/`delete_file`/`search_files`,
  sandboxed to a root read from `BOUKENSHA_MCP_FS_ROOT`
- `lib/boukensha/mcp_servers/shell_server.rb` — `MCP::Server` exposing
  `run_command`, configured from `BOUKENSHA_MCP_SHELL_ROOT`/`_TIMEOUT`/`_ALLOWED`

**CHANGE (rewrite for this step's topic — transport only, tool behavior unchanged):**
- `lib/boukensha/tools/file_system.rb` — becomes a thin `register(registry, working_dir:)`
  that spawns `mcp_servers/file_system_server.rb` and bridges it in, instead of
  registering local closures directly
- `lib/boukensha/tools/shell.rb` — same idea for `run_command`
- `Gemfile` / `boukensha.gemspec` — add `gem "mcp", "~> 1.0"`
- `README.md` — document the new MCP-backed transport for these two tool
  modules (behavior/parameters unchanged, so this is a small addition, not
  a rewrite)

**LEAVE AS-IS:**
- `lib/boukensha/tools/mud.rb` — out of scope (see above)
- `lib/boukensha/registry.rb`, `tool.rb`, `agent.rb`, `client.rb`, `context.rb`,
  `repl.rb`, `tui.rb`, `run_dsl.rb`, `errors.rb`, `message.rb`,
  `prompt_builder.rb`, `logger.rb`, `backends/*.rb`, `tasks/*.rb` — the
  `Registry#tool(name, description:, parameters:, &block)` call shape at
  every tool-registration site is unchanged, exactly like Python's plan kept
  `registry.py`, `tool.py`, `agent.py` untouched
- `lib/boukensha_loader.rb` — no functional change (see "Loader" section
  below for why, not "we forgot")
- `lib/boukensha.rb`'s `run`/`repl` signatures — `working_dir:`,
  `allowed_commands:`, `shell_timeout:`, `mud:` keywords and the
  `Tools::FileSystem.register(...)` / `Tools::Shell.register(...)` call
  sites stay exactly as they are; only what those two `register` methods do
  internally changes

## Target structure (new/changed files only)

```
week1_baseline/ruby/11_tui/
  Gemfile                                    <- add gem "mcp"
  boukensha.gemspec                          <- add spec.add_dependency "mcp"
  lib/
    boukensha/
      mcp_client.rb                          <- NEW
      mcp_servers/                           <- NEW
        file_system_server.rb
        shell_server.rb
      tools/
        file_system.rb                       <- CHANGE (transport only)
        shell.rb                              <- CHANGE (transport only)
        mud.rb                                <- unchanged
```

`boukensha.gemspec`'s existing `spec.files = Dir["lib/**/*.rb"]` already
sweeps up `mcp_client.rb` and `mcp_servers/*.rb` with no glob change needed.

## Ruby ↔ Python file mapping

| Python | Ruby | Notes |
|---|---|---|
| `boukensha/mcp_client.py` | `lib/boukensha/mcp_client.rb` | Ruby version has no asyncio bridge — see above |
| `boukensha/mcp_servers/file_system_server.py` | `lib/boukensha/mcp_servers/file_system_server.rb` | Same env-var-configured, stdio-spawned design |
| `boukensha/mcp_servers/shell_server.py` | `lib/boukensha/mcp_servers/shell_server.rb` | Same |
| `boukensha/tools/file_system.py` | `lib/boukensha/tools/file_system.rb` | Both become thin MCP-spawning wrappers |
| `boukensha/tools/shell.py` | `lib/boukensha/tools/shell.rb` | Same |
| `mcp` (PyPI, `mcp>=1.28.1`) | `mcp` (RubyGems, `~> 1.0`) | Both are the official MCP SDK for their language; Ruby's also bundles server+client in one gem, same as Python's |
| `fastmcp` (`from mcp.server.fastmcp import FastMCP`) | `MCP::Server` + `MCP::Server::Transports::StdioTransport` (same `mcp` gem) | No separate `fast-mcp` gem needed — the official `mcp` gem already has an equally terse `server.define_tool(name:, description:, input_schema:) { |args, server_context:| ... }` block API |

## New/changed class behavior

### `lib/boukensha/mcp_client.rb` (new)

```ruby
require "mcp"

module Boukensha
  # Synchronous bridge to an MCP server run as a stdio subprocess.
  #
  # Unlike the Python port's mcp_client.py, no event-loop bridge is needed
  # here: the mcp gem's MCP::Client::Stdio transport is already built on
  # Open3.popen3 + blocking IO#gets, so this is a thin wrapper, not a
  # concurrency primitive in its own right.
  module McpClient
    # Spawn an MCP server, discover its tools, and register each one into
    # a boukensha Registry — a bridge, not a replacement, for the existing
    # Tool/Registry/Agent/backends architecture.
    #
    # Each MCP tool's inputSchema (a JSON Schema object, string keys) is
    # unpacked back into boukensha's flat parameters shape
    # ({ name: { type:, description: } }), matching what backends/*.rb
    # already expects — this is the layer that lets the rest of the
    # framework stay exactly as it was.
    def self.register_mcp_tools(registry, command:, args: [], env: nil)
      transport = MCP::Client::Stdio.new(command: command, args: args, env: env)
      client    = MCP::Client.new(transport: transport)
      client.connect

      client.tools.each do |tool|
        properties = (tool.input_schema || {})["properties"] || {}

        registry.tool tool.name,
          description: tool.description || "",
          parameters:  properties do |**kwargs|
          response = client.call_tool(name: tool.name, arguments: kwargs)
          content  = response.dig("result", "content") || []
          text     = content.filter_map { |block| block["text"] }.join("\n")

          if response.dig("result", "isError")
            text.empty? ? "error: tool call failed" : "error: #{text}"
          else
            text
          end
        end
      end

      client
    end
  end
end
```

Notes:
- `MCP::Client::Stdio#connect` performs the `initialize` handshake and is
  idempotent; called once here, eagerly, matching Python's eager `ready.wait`
  in `McpClient.__init__`.
- `client.tools` (not `list_tools`) auto-paginates — matches Python's
  `client.list_tools()` call, which for these two servers never actually
  paginates (five and one tools respectively) but using the auto-paginating
  method is the more correct default and costs nothing.
- No explicit `client.transport.close`/subprocess-reap call is wired up
  here deliberately in this plan — see "Open question: subprocess
  lifecycle" below.

### `lib/boukensha/mcp_servers/file_system_server.rb` (new)

Direct translation of `file_system_server.py`'s tool logic onto
`MCP::Server`/`MCP::Server::Transports::StdioTransport`:

```ruby
#!/usr/bin/env ruby
# frozen_string_literal: true

# MCP server exposing the standard file-system tools, sandboxed to a single
# root directory. Run as a stdio subprocess by
# lib/boukensha/tools/file_system.rb — the root directory is passed via the
# BOUKENSHA_MCP_FS_ROOT environment variable, since that's how the parent
# process (mcp_client.rb) launches it.
#
# Tool logic here is identical to the pre-MCP tools/file_system.rb
# implementation — only the transport changed (local closures -> an MCP
# server the framework talks to over stdio).

require "bundler/setup" if ENV["BUNDLE_GEMFILE"]
require "mcp"
require "fileutils"

ROOT = File.expand_path(ENV.fetch("BOUKENSHA_MCP_FS_ROOT"))

def resolve(path)
  absolute = File.expand_path(path.to_s, ROOT)
  if absolute == ROOT || absolute.start_with?("#{ROOT}/")
    absolute
  else
    "error: path '#{path}' escapes the working directory"
  end
end

def oops(msg) = "error: #{msg}"

def text_response(str, error: false)
  MCP::Tool::Response.new([{ type: "text", text: str }], error: error)
end

server = MCP::Server.new(name: "boukensha-file-system")

server.define_tool(
  name: "pwd",
  description: "Return the working directory — the root that all file paths are relative to."
) do |_args, server_context:|
  text_response(ROOT)
end

server.define_tool(
  name: "list_directory",
  description: "List files and subdirectories at a path relative to the working directory. Defaults to the working directory itself.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to list (default '.')" } } }
) do |args, server_context:|
  path   = args[:path] || "."
  target = resolve(path)
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{path}' is not a directory")) unless File.directory?(target)

  entries = Dir.entries(target)
               .reject { |e| e == "." || e == ".." }
               .sort
               .map { |name| File.directory?(File.join(target, name)) ? "#{name}/" : name }

  text_response(entries.empty? ? "(empty)" : entries.join("\n"))
end

server.define_tool(
  name: "read_file",
  description: "Read and return the full contents of a file. Path is relative to the working directory.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to the file" } }, required: ["path"] }
) do |args, server_context:|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{args[:path]}' is not a file")) unless File.file?(target)

  begin
    text_response(File.read(target))
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "write_file",
  description: "Write content to a file, creating it (and any missing parent directories) if needed, overwriting if it exists. Path is relative to the working directory.",
  input_schema: {
    properties: {
      path:    { type: "string", description: "Relative path to the file" },
      content: { type: "string", description: "Text content to write" }
    },
    required: ["path", "content"]
  }
) do |args, server_context:|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")

  begin
    FileUtils.mkdir_p(File.dirname(target))
    File.write(target, args[:content])
    rel = target.delete_prefix("#{ROOT}/")
    text_response("ok: wrote #{args[:content].bytesize} bytes to #{rel}")
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "delete_file",
  description: "Delete a file. Directories are not deleted. Path is relative to the working directory.",
  input_schema: { properties: { path: { type: "string", description: "Relative path to the file to delete" } }, required: ["path"] }
) do |args, server_context:|
  target = resolve(args[:path])
  next text_response(target) if target.start_with?("error:")
  next text_response(oops("'#{args[:path]}' is not a file")) unless File.file?(target)

  begin
    File.delete(target)
    text_response("ok: deleted #{args[:path]}")
  rescue => e
    text_response(oops(e.message))
  end
end

server.define_tool(
  name: "search_files",
  description: "Search for a text pattern (literal string or Ruby regex) across all files in the working directory tree. Returns matching lines in 'path:line_number:content' format.",
  input_schema: {
    properties: {
      pattern: { type: "string", description: "The text or regex pattern to search for" },
      path:    { type: "string", description: "Subdirectory or file to search within (default '.' = entire working directory)" },
      glob:    { type: "string", description: "File glob to restrict which files are searched, e.g. '*.rb' (default '*')" }
    },
    required: ["pattern"]
  }
) do |args, server_context:|
  path, glob = args[:path] || ".", args[:glob] || "*"
  target = resolve(path)
  next text_response(target) if target.start_with?("error:")

  file_glob = File.file?(target) ? target : File.join(target, "**", glob)

  begin
    regex = Regexp.new(args[:pattern])
  rescue RegexpError => e
    next text_response(oops("invalid pattern: #{e.message}"))
  end

  matches = []
  Dir.glob(file_glob).sort.each do |file|
    next unless File.file?(file)
    rel = file.delete_prefix("#{ROOT}/")
    begin
      File.foreach(file).with_index(1) do |line, lineno|
        matches << "#{rel}:#{lineno}:#{line.chomp}" if line.match?(regex)
      end
    rescue => e
      matches << "#{rel}: error reading file: #{e.message}"
    end
  end

  text_response(matches.empty? ? "no matches" : matches.join("\n"))
end

MCP::Server::Transports::StdioTransport.new(server).open
```

Notes:
- **Tool arguments arrive with symbol keys** (`args[:path]`, not
  `args["path"]`) — per the `mcp` gem README, transports parse incoming
  JSON with `symbolize_names: true`. This is the opposite of Python, where
  `@mcp.tool()` binds arguments straight to keyword parameters — Ruby's
  block-based `define_tool` gets a single `args` Hash instead, so every
  tool body here reads `args[:key]` rather than a `key:` kwarg. This is a
  real, easy-to-get-wrong translation detail, called out explicitly.
- **`next text_response(...)` inside a `define_tool` block** — Ruby blocks
  support `next` as an early-return, same role as the original
  `tools/file_system.rb`'s `next target if target.start_with?("error:")`
  pattern already used before MCP; behavior-preserving, not a new idiom.
- **`search_files`' Ruby regex vs. Python's `re`**: kept as `Regexp.new`
  (the same engine the pre-MCP `tools/file_system.rb` already used) —
  no behavior change, this server is a straight transport move of
  Ruby's own existing tool, not a re-port from Python's `re`-flavored
  version.
- Same defensive `File.expand_path`-only (no symlink resolution) path
  containment as the pre-MCP version and as Python's — unchanged from
  what's already in `tools/file_system.rb` today.

### `lib/boukensha/mcp_servers/shell_server.rb` (new)

Same shape, direct move of the existing `tools/shell.rb` logic behind
`MCP::Server`:

```ruby
#!/usr/bin/env ruby
# frozen_string_literal: true

require "bundler/setup" if ENV["BUNDLE_GEMFILE"]
require "mcp"
require "open3"
require "timeout"

ROOT    = File.expand_path(ENV.fetch("BOUKENSHA_MCP_SHELL_ROOT"))
TIMEOUT = Integer(ENV.fetch("BOUKENSHA_MCP_SHELL_TIMEOUT", "30"))

# Same three-state env-var convention as Python's shell_server.py: unset =
# allow all; set-but-empty = empty list (reject everything); "a,b,c" = that
# allow-list.
raw_allowed      = ENV["BOUKENSHA_MCP_SHELL_ALLOWED"]
ALLOWED_COMMANDS = raw_allowed.nil? ? nil : raw_allowed.split(",").reject(&:empty?)

allowed_note = ALLOWED_COMMANDS ? " Allowed executables: #{ALLOWED_COMMANDS.join(', ')}." : ""

server = MCP::Server.new(name: "boukensha-shell")

server.define_tool(
  name: "run_command",
  description: "Run a shell command inside the working directory and return its combined stdout+stderr output. " \
               "Commands run with a #{TIMEOUT}-second timeout.#{allowed_note}",
  input_schema: { properties: { command: { type: "string", description: "The shell command to execute (e.g. 'ruby script.rb', 'ls -la', 'git status')" } }, required: ["command"] }
) do |args, server_context:|
  command = args[:command]

  if ALLOWED_COMMANDS
    executable = command.to_s.strip.split(/\s+/).first.to_s
    unless ALLOWED_COMMANDS.include?(executable)
      next MCP::Tool::Response.new([{ type: "text", text: "error: '#{executable}' is not in the allowed-commands list (#{ALLOWED_COMMANDS.join(', ')})" }])
    end
  end

  stdout_err, status = nil, nil
  begin
    Timeout.timeout(TIMEOUT) { stdout_err, status = Open3.capture2e(command, chdir: ROOT) }
  rescue Errno::ENOENT => e
    next MCP::Tool::Response.new([{ type: "text", text: "error: command not found: #{e.message}" }])
  rescue Timeout::Error
    next MCP::Tool::Response.new([{ type: "text", text: "error: command timed out after #{TIMEOUT}s: #{command}" }])
  end

  exit_note = status.success? ? "" : "\n[exit #{status.exitstatus}]"
  output    = stdout_err.to_s.strip
  text      = output.empty? ? "(no output)#{exit_note}" : "#{output}#{exit_note}"
  MCP::Tool::Response.new([{ type: "text", text: text }])
end

MCP::Server::Transports::StdioTransport.new(server).open
```

### `lib/boukensha/tools/file_system.rb` (rewritten)

```ruby
require_relative "../mcp_client"

module Boukensha
  module Tools
    module FileSystem
      SERVER_SCRIPT = File.expand_path("../mcp_servers/file_system_server.rb", __dir__)

      # Tools registered: pwd, list_directory, read_file, write_file,
      # delete_file, search_files — all sandboxed to working_dir.
      #
      # The tools themselves now run inside a separate MCP server process
      # (mcp_servers/file_system_server.rb), spawned over stdio and bridged
      # into this Registry via McpClient.register_mcp_tools — the
      # Registry/Tool/Agent call sites here are unchanged from the pre-MCP
      # version; only where the tool logic actually executes has moved.
      def self.register(registry, working_dir:)
        McpClient.register_mcp_tools(
          registry,
          command: RbConfig.ruby,
          args:    [SERVER_SCRIPT],
          env:     mcp_env(working_dir)
        )
      end

      def self.mcp_env(working_dir)
        env = { "BOUKENSHA_MCP_FS_ROOT" => File.expand_path(working_dir) }
        # Propagate the Gemfile this step's own bundle resolved to, so the
        # spawned server subprocess activates the same "mcp" gem regardless
        # of the *caller's* cwd — see the "Loader" section below.
        env["BUNDLE_GEMFILE"] = ENV["BUNDLE_GEMFILE"] if ENV["BUNDLE_GEMFILE"]
        env
      end
      private_class_method :mcp_env
    end
  end
end
```

`lib/boukensha/tools/shell.rb` gets the mirror-image change (same
`SERVER_SCRIPT`/`mcp_env` pattern, plus forwarding `timeout:` and
`allowed_commands:` into `BOUKENSHA_MCP_SHELL_TIMEOUT`/`_ALLOWED`, exactly
as `shell.py` already does).

## Loader: why no functional change, but one env var must flow through

`lib/boukensha_loader.rb` resolves **which step's `lib/boukensha.rb` to
require** (`BOUKENSHA_PATH` → `~/.boukensharc` → the bundled gem). That
resolution is a one-time, in-process `require`, and it's already correct —
nothing about adding MCP changes *what* gets loaded.

What MCP *does* introduce is a **second** self-location problem, one level
down: `tools/file_system.rb` needs to find its own sibling
`mcp_servers/file_system_server.rb` on disk to spawn it, **and** that
spawned subprocess needs to activate the same `mcp` gem the parent process
already has active — regardless of whether the parent was itself loaded via
the bundled gem, a `BOUKENSHA_PATH` override, or a bare dev checkout run
with `bundle exec`.

The first half is solved the same way Python's `mcp.py` solved it
(`Path(__file__).resolve().parent.parent`) — `File.expand_path(...,
__dir__)` in `tools/file_system.rb` is never affected by `Dir.pwd` or which
step got loaded, so it needs no extra plan work.

The second half is new: a bare `ruby mcp_servers/file_system_server.rb`
subprocess does **not** inherit Bundler's resolved gem set unless it either
(a) is itself run via `bundle exec`, or (b) explicitly does `require
"bundler/setup"` against the right `Gemfile`. Since `Open3.popen3` spawns
with the *caller's* `Dir.pwd`, not the gem's install directory, `BUNDLE_GEMFILE`
can't be left to default — it has to be forwarded explicitly. This plan's
fix (propagate `ENV["BUNDLE_GEMFILE"]` into the subprocess env in
`tools/file_system.rb`/`tools/shell.rb`, and have each `mcp_servers/*.rb`
script call `require "bundler/setup" if ENV["BUNDLE_GEMFILE"]` before
`require "mcp"`) is the direct extension of the same "resolve paths
relative to where this code actually lives, not the caller's cwd"
discipline `BoukenshaLoader` already established — that discipline is the
"loader improvement" this plan carries into the TUI, not a change to
`boukensha_loader.rb`'s own code.

## Verified non-issue: TUI thread safety

`lib/boukensha/tui.rb` already runs each agent turn on a dedicated
`@turn_thread` (confirmed at `tui.rb:250`), separate from the bubbletea
event loop that owns the real terminal. The MCP subprocess communicates
over `Open3.popen3` pipes — distinct file descriptors from the terminal —
so a blocking `IO#gets` inside a tool call on `@turn_thread` cannot starve
or conflict with the TUI's own terminal I/O. No TUI-specific change needed
beyond the tool-transport rewrite above.

## Open question: subprocess lifecycle

Python's `McpClient` registers `atexit.register(self.close)` so the spawned
server process is reaped when the parent exits. This plan's `mcp_client.rb`
sketch above does not yet wire up an equivalent — worth deciding before
implementation:
- `at_exit { client.transport.close }` in `register_mcp_tools`, mirroring
  Python exactly, or
- Rely on `MCP::Client::Stdio#close`'s existing `TERM`-then-`KILL` escalation
  being invoked explicitly wherever the REPL/TUI already tears down its
  `Registry` (if such a teardown hook exists — needs a quick check of
  `repl.rb`'s shutdown path, which this plan hasn't audited since it's
  outside the tool-transport delta).

## Decisions to confirm before implementation

- Gem choice: `mcp` (official SDK, ships both client and server) rather
  than pulling in the separate `fast-mcp` gem as well — `fast-mcp` would
  duplicate server functionality the `mcp` gem already provides under a
  different namespace (`MCP::Tool`/`MCP::Server` in both, confusingly, so
  mixing them is actively worth avoiding).
- Version pin: `~> 1.0`, matching the currently-published `mcp-1.0.0` — no
  reason found to pin tighter.
- Scope: `file_system` + `shell` only, `mud` explicitly excluded, matching
  Python's own precedent exactly (see "Why this only touches..." above).
