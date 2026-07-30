# Ruby 11_tui → 12_context Delta Plan

## Goal

Identify what, if anything, needs to carry forward from
`week1_baseline/ruby/11_tui` into `week1_baseline/ruby/12_context` so that
12_context doesn't silently lose real capability that 11_tui had, while
leaving 12_context's own new material (context/token management, reasoning
support, the Responses-API migration, the simplified `Config`) untouched.
**Plan only — no source files are touched by writing this document.**

## Why this needed investigation, not assumption

12_context is **not** "11_tui plus a context-management feature" — it's a
separately-evolved baseline that both adds new things and drops things
11_tui had. Confirmed via `diff -rq` and full-file reads of every file that
differs (excluding `vendor/`, `.bundle/`, and the built `.gem` artifacts):

| Claim | Evidence |
|---|---|
| 12_context already has its own TUI, `Context`, `Agent`, `Config`, `Logger` — not missing, independently evolved | Every one of these files exists in both dirs and differs; none is "only in 11_tui" |
| 12_context's own new work this step: token/context tracking + compaction, reasoning/thinking blocks across all 4 backends, OpenAI moved to the Responses API, a new `Models` capability table | Read directly: `context.rb` gains `current_tokens`/`turn_tokens`/`compact_messages!`; `agent.rb` gains `compact_if_needed`/`record_usage`/`log_reasoning`; `backends/base.rb` documents a new `"reasoning"` content-block type; `backends/openai.rb`'s `BASE_URL` changed to `.../v1/responses`; `lib/boukensha/models.rb` is new, not present in 11_tui |
| Only in 11_tui (not in 12_context): `lib/boukensha/mcp_client.rb`, `lib/boukensha/mcp_servers/{file_system_server,shell_server}.rb`, `lib/boukensha/tasks/{base,player}.rb`, `prompts/system.md` | `diff -rq 11_tui 12_context` output |
| Only in 12_context (not in 11_tui): `lib/boukensha/models.rb` | Same `diff -rq` output |
| `mcp` gem dependency removed entirely | `Gemfile`/`boukensha.gemspec` diff — `gem "mcp"` / `spec.add_dependency "mcp", "~> 1.0"` both gone in 12_context |
| `Tasks::Base`/`Tasks::Player` removed, but the **settings.yaml schema they read is unchanged** | 12_context's `config.rb` reads `dig(:tasks, :player, :provider)`, `dig(:tasks, :player, :model)`, `dig(:tasks, :player, :prompt_override, :system)` — the exact same key paths `Tasks::Base#provider`/`#model`/`#prompt_override?` used to read via `fetch(settings, ...)`. Confirmed against the live `.boukensha/settings.yaml`, which still has `tasks: player: provider/model/prompt_override:` and works today. |
| `list_directory` and `search_files` tools are present in code but commented out in 12_context, not merely absent | Read `12_context/lib/boukensha/tools/file_system.rb` directly — full implementations exist inline as comments, with the note "leftover from when this app was a coding harness; the player agent has no use for them yet" |
| `mud_manager` and `mcp` are both already installed as regular system gems, not just resolved via a local path | `gem list mud_manager -a` → `mud_manager (0.1.0)`; `gem list mcp -a` → `mcp (1.0.0)` |
| 12_context has no `vendor/`, `.bundle/config` | `ls` of both directories — 11_tui has `vendor/` and `.bundle/config` (`BUNDLE_PATH: "vendor/bundle"`), 12_context has neither |

## Classification of every difference found

### A. Not a gap — 12_context's own new work this step (leave alone)

- `Context#current_tokens`/`turn_tokens`/`context_window`/`compact_messages!`/`needs_compaction?`, `Agent#compact_if_needed`/`record_usage`/`token_limit_reached?`, `Logger#compaction`/`#reasoning`/`#plan`, `Repl`'s `/compact` command, `Tui`'s context-usage color coding (`ctx_color`, `CTX_WARN_PCT`/`CTX_ALERT_PCT`) — this **is** step 12's subject matter.
- `lib/boukensha/models.rb` (new `Models.context_window(model)` table) — feeds `context_window:` into `Context.new`, used by both `Boukensha.run`/`.repl`.
- Reasoning/thinking-block support added to `Backends::Base`'s documented contract and to `anthropic.rb`/`gemini.rb`/`ollama.rb`/`ollama_cloud.rb` (native thinking blocks normalized to `{"type"=>"reasoning",...}`, round-tripped back on the next call).
- `backends/openai.rb` migrated from `/v1/chat/completions` to `/v1/responses` (comment explains why: gpt-5.x rejects `reasoning_effort` + tools on chat completions).
- `Config` replacing `Tasks::Base`/`Tasks::Player` with flat `provider_type`/`model`/`system_prompt`/`agent_max_iterations`/`agent_max_output_tokens`/`agent_max_turn_tokens`/`agent_compaction_threshold` — **verified backward-compatible** with the existing `settings.yaml` schema (see evidence table). `lib/boukensha/tasks/` should **not** be resurrected; it would be dead code duplicating what `Config` now does directly.
- TUI recolor (`ANSI_COLORS` palette change) and `@textarea.width` fix — cosmetic/bugfix, already present in 12_context, nothing to carry.

### B. Real gaps — confirm before deciding, then act

**B1. No shipped default system prompt.**
11_tui ships `prompts/system.md` at the repo root and `config.rb` resolves it
via `PROMPTS_DIR = File.expand_path("../../../prompts", __dir__)` as a
fallback when the user hasn't set up an override. 12_context has **no**
`prompts/` directory at all, and its `Config#load_system_prompt` only ever
reads from the user's config dir (`~/.boukensha/prompts/player/system.md` or
`~/.boukensha/prompts/system.md`) — there is no shipped fallback. A fresh
user with no `~/.boukensha/prompts/` files gets `system: nil`. Today's local
`.boukensha/settings.yaml` happens to have `prompt_override: system: true`
and a matching file, which is why it currently works — that's incidental,
not evidence the gap is harmless for a new user.

**B2. `list_directory`/`search_files` disabled.**
Both existed and worked (via MCP) in 11_tui. In 12_context they're fully
implemented but commented out with a rationale that the "player" (MUD-game)
agent doesn't need coding-style tools. This may well be the right call for
this app's actual use case — but it's a functional narrowing, not a
transport change, and should be a conscious decision, not something that
silently rode along with the MCP removal.

**B3. MCP stdio tool transport removed.**
11_tui ran `file_system`/`shell` tools behind real MCP servers
(`mcp_client.rb` + `mcp_servers/*.rb`), matching the Python port's
architecture (see `docs/plans/ruby_tui_mcp_and_loader.md`, which put that
transport into 11_tui in the first place). 12_context reverted both tools to
plain in-process registry closures — behaviorally identical for the 4 tools
it kept, but the process-boundary/JSON-RPC transport, and the
Gemfile/gemspec `mcp` dependency, are gone.

## Recommended concrete delta

**ADD:**
- `12_context/prompts/system.md` — copy 11_tui's shipped default system
  prompt over, so a fresh install still has *something* sensible without
  requiring `~/.boukensha` setup first (fixes B1).
- Restore a `PROMPTS_DIR`-style fallback in `12_context/lib/boukensha/config.rb#load_system_prompt`, checked after the user-override checks, mirroring 11_tui's `Tasks::Base#prompt`/`#read_default_prompt` fallback order (user override → shipped default → nil).

**DECIDE, THEN ACT (do not silently pick one):**
- B2 — either uncomment `list_directory`/`search_files` in
  `12_context/lib/boukensha/tools/file_system.rb` (no MCP needed either way —
  they'd just become two more in-process closures, same pattern as
  `read_file`/`write_file`/`delete_file` already there), or leave them
  disabled and delete the dead code instead of leaving it commented out.
- B3 — either accept the in-process transport as 12_context's (and future
  steps') new baseline and drop `mcp_client.rb`/`mcp_servers/` from 11_tui for
  good, or port them forward exactly as `ruby_tui_mcp_and_loader.md` already
  did once (re-add `gem "mcp"`, `mcp_client.rb`, `mcp_servers/*.rb`, and swap
  `tools/file_system.rb`/`tools/shell.rb` back to the MCP-bridging versions).

**LEAVE AS-IS (confirmed intentional, not a regression):**
- `lib/boukensha/tasks/` — do not resurrect; `Config` already covers the same
  settings.yaml keys directly.
- All context/token/compaction/reasoning/Responses-API work — this step's
  actual subject matter.
- `vendor/`/`.bundle/config` absence — `mud_manager` (and, if B3 restores it,
  `mcp`) are already installed as ordinary system gems (`gem list` confirms
  both), so `bundle install` resolves without vendoring. Only worth
  revisiting if reproducible/offline installs are a goal independent of this
  delta.

## Decisions to confirm before implementation

1. Should `12_context/prompts/system.md` exist (ship a default), or is
   requiring `~/.boukensha/prompts/...` setup now the intended UX for step
   12 onward? 
2. Should `list_directory`/`search_files` come back for the player agent, or
   is narrowing the tool surface to file read/write/delete + shell
   deliberate for this and later steps? 
3. Should the MCP stdio transport for `file_system`/`shell` be preserved
   going forward (matching the Python port's architecture), or was
   `11_tui`'s MCP work a one-step detour that later steps are meant to drop?
