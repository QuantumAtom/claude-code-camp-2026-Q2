# 03b_subagent_sdk — plan

## Goal

Compare two ways of getting a `tbamud-player` subagent in front of an
orchestrator:

- **03a_subagent_sdk** — Claude Code's filesystem convention. Drop
  frontmatter + prompt at `.claude/agents/tbamud-player.md` and the CLI
  auto-discovers it (`name`, `description`, `tools`, `model` in
  frontmatter, prompt body below).
- **03b_subagent_sdk** (this folder) — the Claude Agent SDK's
  `AgentDefinition`. Same subagent, defined in Python code and passed to
  `ClaudeAgentOptions(agents={...})`, with `setting_sources=[]` so the
  process never falls back to filesystem discovery.

Both variants share the same subagent support bundle
(`.claude/agents/tbamud-player/scripts/mud_client.py`,
`references/commands.md`) and the same `data/player.md` /
`data/world.md` memory files — only *how the orchestrator learns the
subagent exists* differs.

## Status

- [x] Stand up `.claude/agents/tbamud-player.md` (filesystem baseline,
      lives in 03a; also existed here until this step).
- [x] Port that definition into `main.py` via `AgentDefinition`
      (description/prompt/tools/model carried over verbatim).
- [x] Remove `03b_subagent_sdk/.claude/agents/tbamud-player.md` — now
      redundant, since `main.py` is the source of truth here.
- [x] Add `requirements.txt` (`claude-agent-sdk`) and a local `.venv`.
- [x] Sanity-check `main.py` compiles and `build_options()` produces the
      expected `AgentDefinition` (name, tools, model, `setting_sources=[]`).
- [x] Run `main.py` against the live MUD server end-to-end and confirm
      the orchestrator actually delegates via the `Agent` tool — 2026-07-23:
      confirmed. Orchestrator called `Agent(subagent_type: "tbamud-player", ...)`,
      the subagent logged in, found the character at a new room ("The
      Tournament And Practice Yard"), reported hungry/thirsty and 0
      practice sessions remaining, disconnected cleanly, and updated
      `data/player.md`/`data/world.md`. 2 turns, 168s, ~$0.60.
- [x] Switch `main.py` from one-shot `query()` to `ClaudeSDKClient` so the
      orchestrator conversation (and the subagent's own MUD daemon
      connection) survives across multiple turns without restarting the
      process — now an interactive loop (`client.query()` +
      `client.receive_response()` per turn), with an optional argv
      message sent as the first turn before dropping into the prompt.
- [ ] Diff behavior against 03a for the same prompt (does the SDK
      variant delegate as reliably? any difference in latency/cost from
      skipping filesystem settings discovery?).
- [ ] Decide whether `setting_sources=[]` is too blunt (it also
      suppresses `CLAUDE.md`/`.claude/settings.json` if this project ever
      grows one) vs. scoping it more narrowly.

## Open questions

- Is there a meaningful behavioral difference between CLI auto-discovery
  and SDK-registered agents, or is this purely a "where does the
  definition live" distinction?
- Worth porting the `tbamud-player/` support bundle's `evals/` (see
  `02_agent_skills`) to score 03a vs 03b head-to-head?

## How to run

```
.venv/bin/python main.py                    # straight into interactive mode
.venv/bin/python main.py "go kill some rats" # sends this as the first turn, then interactive
```

Type `exit`/`quit` or Ctrl-D to end the session. `ClaudeSDKClient` keeps the
process (and the subagent's MUD daemon connection) alive across turns.
