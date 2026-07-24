# Python Port Plan — 05_agent_loop

## Goal

Port `week1_baseline/ruby/05_agent_loop` to
`week1_baseline/python/05_agent_loop`. Same behavior, same on-disk config
format, same loop/wind-down semantics, new language. No new features — this
is a straight port of the existing step. **Plan only — no source files are
touched by writing this document.**

**This plan only covers what changed between Ruby 04 and Ruby 05.**
Everything already ported correctly in `04_api_client` (client retry logic,
error handling, task config, backend model tables, dataclasses) stays
exactly as it is. Nothing gets rewritten from scratch and nothing that
already works gets touched or regenerated — this is additive, in the same
spirit as the earlier ports.

**Starting point: `week1_baseline/python/05_agent_loop` already exists as a
byte-for-byte copy of the finished `week1_baseline/python/04_api_client`
tree.** Confirmed via `diff -rq boukensha/` between the two directories —
zero output, every file identical. This is expected: per direct
confirmation, **Step 5 hasn't been started yet**, so this plan is a
from-scratch delta against Step 4, not a check for drift. Same shape as the
04 port: an **in-place edit of the copied tree**, not a from-scratch build.

## Source of truth (what changed, Ruby 04 → Ruby 05)

Verified with `diff -ru week1_baseline/ruby/04_api_client
week1_baseline/ruby/05_agent_loop` plus targeted diffs of every file the
README claims changed (`context.rb`, `tasks/player.rb`, `backends/base.rb`,
`message.rb`, `registry.rb`, `tool.rb`, `Gemfile`, `prompts/system.md` — all
confirmed **byte-identical** to 04 despite the Ruby README listing
`context.rb` as updated; that line in the Ruby README is stale/wrong,
follow the diff, not the prose).

| Ruby file | Change vs. 04 | Status |
|---|---|---|
| `lib/boukensha/agent.rb` | **NEW** — the `Agent` class: the loop itself | New — the core deliverable of this step |
| `lib/boukensha.rb` | Adds `require_relative "boukensha/agent"` | `__init__.py` needs the new export |
| `lib/boukensha/errors.rb` | Adds `LoopError < StandardError` | `errors.py` missing this — add it (see "dead code" note below) |
| `lib/boukensha/tasks/base.rb` | Adds `DEFAULT_MAX_ITERATIONS = 25`, `DEFAULT_MAX_OUTPUT_TOKENS = 1024`, `.max_iterations(settings)`, `.max_output_tokens(settings)`, private `integer_setting` helper | `tasks/base.py` needs all of this added |
| `lib/boukensha/client.rb` | `call(max_output_tokens:, tools: nil)` — new `tools:` kwarg threaded into `to_api_payload` | `client.py` needs the same `tools=None` param |
| `lib/boukensha/prompt_builder.rb` | `to_api_payload(max_output_tokens:, tools: nil)` threads `tools:` to the backend; new `parse_response(response)` delegates to `@backend.parse_response` | `prompt_builder.py` needs both |
| `lib/boukensha/backends/anthropic.rb` | `to_payload` gains `tools:` override param; new `parse_response` normalizes the response | Port both |
| `lib/boukensha/backends/openai.rb` | Same `tools:` param; new `parse_response`; new private `assistant_message` (rebuilds an OpenAI assistant turn from normalized content, used when replaying history) | Port all three |
| `lib/boukensha/backends/gemini.rb` | Same `tools:` param; new `parse_response`; new private `assistant_parts`; `to_messages` now calls `assistant_parts(msg.content)` instead of wrapping `msg.content` in a single text part | Port all four changes |
| `lib/boukensha/backends/ollama.rb` | Same `tools:` param; new `parse_response`; new private `assistant_message`; `to_messages` gains an explicit `:assistant` branch calling it | Port all four changes |
| `lib/boukensha/backends/ollama_cloud.rb` | Identical shape of changes to `ollama.rb` | Port all four changes |
| `lib/boukensha/config.rb` | Two `def foo = expr` one-liners replace equivalent multi-line `def foo; expr; end` bodies (`mud_host`, `mud_port`, `mud_username`, `mud_password`) | **Pure Ruby syntax sugar, no behavior change** — `config.py` needs **no change** |
| `prompts/system.md` | Unchanged from 04 (confirmed via diff) | No change |
| `examples/example.rb` | Rewrite: builds an `Agent` from `builder`/`client`/`registry`/`ctx`, registers `read_file`/`list_directory` tools anchored to `base_dir` (the step root, not cwd), seeds a summarization prompt instead of a directory-listing prompt, prints `Max iterations`/`Max output tokens`, calls `agent.run` instead of `client.call`, prints `FINAL RESPONSE` | Rewrite — see below |
| `README.md` | Full rewrite: Agent Loop design, normalized response shape, per-backend `parse_response`/`assistant_message` contract, task config additions, considerations | Rewrite — see below |
| `Gemfile` | Unchanged (confirmed via diff) — still just `dotenv` | `requirements.txt` needs **no new dependency** |
| `week1_baseline/bin/ruby/05_agent_loop` | Correct — `cd`s into `ruby/05_agent_loop` and runs `examples/example.rb` directly (unlike 04's launcher, this one isn't broken) | No fix needed, out of scope either way |
| `week1_baseline/bin/python/05_agent_loop` | **Confirmed broken** — same bug 04 had before its fix: sources `$ROOT/code/virtualenv/claude/bin/activate`, a path that doesn't exist in this repo, instead of `$ROOT/.venv/bin/activate` | **In scope, must fix** |

## Dead code found while researching this plan (ported faithfully, flagged for awareness)

`Boukensha::LoopError` is defined in `errors.rb` but **never raised
anywhere** in this step's Ruby code — confirmed via `grep -rn LoopError`
across `05_agent_loop`, the only two hits are the class definition and the
README's file table. The actual "runaway agent" protection is
`Agent#wrap_up` (a graceful one-shot wind-down call), not an exception.
`LoopError` reads as scaffolding for a future step (or an abandoned
approach). **Port it anyway** — `errors.py` should still define
`LoopError(Exception): pass` for parity, since a later Ruby step may start
raising it and diverging here would just create a future gap to notice
again. Don't wire it up to anything Python-side either; that would be
inventing behavior Ruby doesn't have.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/agent.py` — `Agent` class (see below)

**FILL (small gaps/additions to existing files):**
- `boukensha/errors.py` — add `LoopError(Exception): pass`
- `boukensha/tasks/base.py` — add `DEFAULT_MAX_ITERATIONS`,
  `DEFAULT_MAX_OUTPUT_TOKENS`, `max_iterations(settings)`,
  `max_output_tokens(settings)`, `_integer_setting` helper
- `boukensha/client.py` — add `tools=None` param to `call()`, thread it
  into `to_api_payload`
- `boukensha/prompt_builder.py` — add `tools=None` param to
  `to_api_payload()`; add `parse_response(response)` delegating to
  `self.backend.parse_response(response)`
- `boukensha/backends/anthropic.py` — add `tools=None` to `to_payload`; add
  `parse_response`
- `boukensha/backends/openai.py` — add `tools=None` to `to_payload`; add
  `parse_response` and `_assistant_message`; add an `elif msg.role ==
  "assistant"` branch in `to_messages`
- `boukensha/backends/gemini.py` — add `tools=None` to `to_payload`; add
  `parse_response` and `_assistant_parts`; change the assistant branch in
  `to_messages` to call `self._assistant_parts(msg.content)`
- `boukensha/backends/ollama.py` — add `tools=None` to `to_payload`; add
  `parse_response` and `_assistant_message`; add an `elif msg.role ==
  "assistant"` branch in `to_messages`
- `boukensha/backends/ollama_cloud.py` — same four additions as `ollama.py`

**CHANGE (already present as 04's copy, must be rewritten for this step's topic):**
- `boukensha/__init__.py` — add `Agent` and `LoopError` to imports and
  `__all__`
- `examples/example.py` — rewrite per Ruby's `examples/example.rb` (see below)
- `README.md` — full rewrite (see below)

**LEAVE AS-IS (confirmed identical to Ruby 04, and no behavior change for these on the Ruby side either):**
- `boukensha/tool.py`, `boukensha/message.py`, `boukensha/context.py`,
  `boukensha/registry.py`
- `boukensha/tasks/player.py`
- `boukensha/backends/base.py` (model-table validation helpers — untouched
  by this step)
- `boukensha/config.py` — Ruby's `config.rb` change here is a no-op
  refactor (endless-method syntax sugar), not a behavior change; nothing to
  port
- `prompts/system.md` (confirmed identical to 04)
- `requirements.txt` (`PyYAML`, `python-dotenv` — no new dependency; the
  loop uses the same stdlib-only `Client` from Step 4)

**FIX outside the step dir:**
- `bin/python/05_agent_loop` — replace the bogus
  `$ROOT/code/virtualenv/claude/bin/activate` line with
  `$ROOT/.venv/bin/activate`, matching every other `bin/python/*` launcher
  and mirroring the exact fix already applied to `bin/python/04_api_client`

**CLEANUP (opportunistic, same as every prior step):**
- Delete any stray `__pycache__/` directories in the copied tree (gitignored,
  harmless, but no reason to keep them)

## Target structure

```
week1_baseline/python/05_agent_loop/
  README.md
  requirements.txt
  prompts/
    system.md
  boukensha/
    __init__.py
    config.py
    tool.py
    message.py
    context.py
    registry.py
    errors.py
    prompt_builder.py
    client.py
    agent.py            <- NEW
    tasks/
      __init__.py
      base.py
      player.py
    backends/
      __init__.py
      base.py
      anthropic.py
      gemini.py
      openai.py
      ollama.py
      ollama_cloud.py
  examples/
    example.py
```

Identical shape to `04_api_client`, plus `agent.py`. No new top-level files,
no `pyproject.toml` (unchanged decision).

## Python environment setup

Same shared-venv / per-step-manifest model as 00–04.

- Venv path: `<repo root>/.venv`.
- `requirements.txt`: unchanged from 04 (`PyYAML`, `python-dotenv`) — the
  agent loop reuses `Client` as-is, no new HTTP or JSON dependency.
- `bin/python/05_agent_loop` needs its venv-source line fixed (see above)
  before it will run at all.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add `Agent`, `LoopError` to exports |
| `lib/boukensha/agent.rb` | `boukensha/agent.py` | NEW — see below |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | Add `LoopError` |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` | Add `max_iterations`/`max_output_tokens` + defaults |
| `lib/boukensha/client.rb` | `boukensha/client.py` | Add `tools=None` param |
| `lib/boukensha/prompt_builder.rb` | `boukensha/prompt_builder.py` | Add `tools=None` param + `parse_response` |
| `lib/boukensha/backends/anthropic.rb` | `boukensha/backends/anthropic.py` | Add `tools` param + `parse_response` |
| `lib/boukensha/backends/openai.rb` | `boukensha/backends/openai.py` | Add `tools` param + `parse_response` + `_assistant_message` |
| `lib/boukensha/backends/gemini.rb` | `boukensha/backends/gemini.py` | Add `tools` param + `parse_response` + `_assistant_parts` |
| `lib/boukensha/backends/ollama.rb` | `boukensha/backends/ollama.py` | Add `tools` param + `parse_response` + `_assistant_message` |
| `lib/boukensha/backends/ollama_cloud.rb` | `boukensha/backends/ollama_cloud.py` | Same as `ollama.py` |
| `lib/boukensha/config.rb` | `boukensha/config.py` | No change (Ruby's diff here is syntax-only) |
| `lib/boukensha/tool.rb`, `message.rb`, `context.rb`, `registry.rb`, `tasks/player.rb`, `backends/base.rb` (all unchanged) | matching `.py` files | No change |
| `examples/example.rb` | `examples/example.py` | Rewrite for the agent-loop demo |
| `Gemfile` (unchanged) | `requirements.txt` (unchanged) | No new dependency either side |
| `README.md` | `README.md` | Full rewrite — loop design, normalized shape, per-backend contract |
| `bin/ruby/05_agent_loop` (already correct) | `bin/python/05_agent_loop` (broken, **in scope**) | Fix the venv source path |

## New class behavior (the actual porting work)

### `LoopError` (`errors.rb` → `errors.py`)

Bare exception, same shape as the existing three, unused for now (see "dead
code" note above):
```python
class LoopError(Exception):
    pass
```

### `tasks/base.py` additions

```python
DEFAULT_MAX_ITERATIONS = 25
DEFAULT_MAX_OUTPUT_TOKENS = 1024

class Base:
    ...
    @classmethod
    def max_iterations(cls, settings):
        return cls._integer_setting(settings, "max_iterations", DEFAULT_MAX_ITERATIONS)

    @classmethod
    def max_output_tokens(cls, settings):
        return cls._integer_setting(settings, "max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)

    @classmethod
    def _integer_setting(cls, settings, key, default):
        value = cls._fetch(settings, key)
        return default if value is None else int(value)
```
Mirrors Ruby's `integer_setting` (`Integer(value)` → Python's `int(value)`;
both raise on a non-numeric string, which is the desired behavior — a
malformed `max_iterations: "abc"` in `settings.yaml` should fail loudly,
not silently fall back to the default).

### `client.py` — add `tools`

```python
def call(self, max_output_tokens=1024, tools=None):
    ...
    body = json.dumps(
        self.builder.to_api_payload(max_output_tokens=max_output_tokens, tools=tools)
    )
    ...
```
Everything else in `Client` (retry loop, backoff, `ApiError`) is untouched
— Ruby's diff here is the one-line `tools:` passthrough only.

### `prompt_builder.py` — add `tools` + `parse_response`

```python
def to_api_payload(self, max_output_tokens=1024, tools=None):
    return self.backend.to_payload(self.context, max_output_tokens=max_output_tokens, tools=tools)

def parse_response(self, response):
    return self.backend.parse_response(response)
```

### Backends — the normalized response shape

Every backend implements `parse_response(response)`, converting its raw
provider response into one common shape so `Agent` never has to know which
provider it's talking to:

```python
{
    "stop_reason": "tool_use" | "end_turn",
    "content": [
        {"type": "text", "text": "..."},
        {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
    ],
}
```

`to_payload` also grows a `tools=None` override param on every backend —
`None` means "use `to_tools(context.tools)` as before" (the default,
exercised on every normal turn); a non-`None` value (`[]` specifically) is
how `Agent.wrap_up` disables tool calls for the final wind-down request.
Pattern, identical across all five backends:
```python
def to_payload(self, context, max_output_tokens=1024, tools=None):
    return {
        ...,
        "tools": self.to_tools(context.tools) if tools is None else tools,
        ...
    }
```

**`assistant_message`/`assistant_parts` is the inverse of `parse_response`.**
When conversation history is replayed on the next request, a backend needs
to rebuild its own wire-format assistant turn from the normalized `content`
blocks `Agent` stored via `context.add_message("assistant", content)`.
Anthropic's `content` array already doubles as both the normalized shape
*and* the wire format, so `to_messages` needs no new branch for it — it
already does `{"role": str(msg.role), "content": msg.content}` for
non-tool_result messages, which is correct as-is. Every other backend needs
a new `elif msg.role == "assistant"` branch calling its rebuild helper.

**Tool call IDs aren't universal**, same as Ruby: Anthropic and OpenAI
assign every tool call a unique `id`; Ollama, Ollama Cloud, and Gemini
don't, so those three backends reuse the tool's `name` as its `id` and
match `tool_result` back to the call by name.

#### `anthropic.py`

```python
def parse_response(self, response):
    stop_reason = "tool_use" if response.get("stop_reason") == "tool_use" else "end_turn"
    return {"stop_reason": stop_reason, "content": response.get("content") or []}
```
No `assistant_message` needed — see above.

#### `openai.py`

```python
import json
...

def to_messages(self, system, messages):
    system_message = [{"role": "system", "content": system}]
    conversation = []
    for msg in messages:
        if msg.role == "tool_result":
            conversation.append({"role": "tool", "tool_call_id": msg.tool_use_id, "content": msg.content})
        elif msg.role == "assistant":
            conversation.append(self._assistant_message(msg.content))
        else:
            conversation.append({"role": str(msg.role), "content": msg.content})
    return system_message + conversation

def parse_response(self, response):
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    tool_calls = message.get("tool_calls") or []

    content = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for tc in tool_calls:
        function = tc.get("function", {})
        content.append({
            "type": "tool_use",
            "id": tc.get("id"),
            "name": function.get("name"),
            "input": json.loads(function.get("arguments") or "{}"),
        })

    return {"stop_reason": "tool_use" if tool_calls else "end_turn", "content": content}

def _assistant_message(self, content):
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    text_blocks = [b for b in blocks if b.get("type") == "text"]
    tool_blocks = [b for b in blocks if b.get("type") == "tool_use"]

    message = {"role": "assistant", "content": "".join(b["text"] for b in text_blocks)}
    if tool_blocks:
        message["tool_calls"] = [
            {
                "id": b["id"],
                "type": "function",
                "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
            }
            for b in tool_blocks
        ]
    return message
```

#### `ollama.py` / `ollama_cloud.py` (identical shape in both)

```python
def to_messages(self, system, messages):
    system_message = [{"role": "system", "content": system}]
    conversation = []
    for msg in messages:
        if msg.role == "tool_result":
            conversation.append({"role": "tool", "tool_name": msg.tool_use_id, "content": msg.content})
        elif msg.role == "assistant":
            conversation.append(self._assistant_message(msg.content))
        else:
            conversation.append({"role": str(msg.role), "content": msg.content})
    return system_message + conversation

def parse_response(self, response):
    message = response.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    content = []
    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})
    for tc in tool_calls:
        fn = tc.get("function", {})
        content.append({
            "type": "tool_use",
            "id": fn.get("name"),
            "name": fn.get("name"),
            "input": fn.get("arguments") or {},
        })

    return {"stop_reason": "end_turn" if not tool_calls else "tool_use", "content": content}

def _assistant_message(self, content):
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    text_blocks = [b for b in blocks if b.get("type") == "text"]
    tool_blocks = [b for b in blocks if b.get("type") == "tool_use"]

    message = {"role": "assistant", "content": "".join(b["text"] for b in text_blocks)}
    if tool_blocks:
        message["tool_calls"] = [
            {"function": {"name": b["name"], "arguments": b["input"]}}
            for b in tool_blocks
        ]
    return message
```

#### `gemini.py`

```python
def to_messages(self, messages):
    result = []
    for msg in messages:
        if msg.role == "assistant":
            result.append({"role": "model", "parts": self._assistant_parts(msg.content)})
        elif msg.role == "tool_result":
            result.append({
                "role": "user",
                "parts": [{"functionResponse": {"name": msg.tool_use_id, "response": {"content": msg.content}}}],
            })
        else:
            result.append({"role": str(msg.role), "parts": [{"text": msg.content}]})
    return result

def parse_response(self, response):
    candidates = response.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []

    content = []
    tool_used = False
    for part in parts:
        if part.get("functionCall"):
            fc = part["functionCall"]
            content.append({"type": "tool_use", "id": fc.get("name"), "name": fc.get("name"), "input": fc.get("args") or {}})
            tool_used = True
        elif part.get("text"):
            content.append({"type": "text", "text": part["text"]})

    return {"stop_reason": "tool_use" if tool_used else "end_turn", "content": content}

def _assistant_parts(self, content):
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
    parts = []
    for b in blocks:
        if b.get("type") == "tool_use":
            parts.append({"functionCall": {"name": b["name"], "args": b["input"]}})
        else:
            parts.append({"text": b["text"]})
    return parts
```

### `Agent` (`agent.rb` → `agent.py`) — the core piece

Ruby's implementation, precisely — the loop control flow, iteration
counting, and wind-down semantics must match:

```python
class Agent:
    MAX_ITERATIONS = 25
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = (
        "You have reached your action limit for this turn. Do not call any more tools.\n"
        "Briefly summarize what you accomplished, what is still unfinished, and the\n"
        "single next action you would take."
    )

    def __init__(self, *, context, registry, builder, client,
                 task_settings=None, max_iterations=None, max_output_tokens=None):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        self.max_iterations = self._resolve_max_iterations(task_settings, max_iterations)
        self.max_output_tokens = self._resolve_max_output_tokens(task_settings, max_output_tokens)
        self.iteration = 0

    def run(self):
        while True:
            # Limits are *trigger thresholds*, not hard caps: once reached we
            # stop starting new work iterations and make exactly one terminal
            # wind-down call instead of raising.
            if self._iteration_limit_reached():
                return self._wrap_up("max_iterations")

            self.iteration += 1
            print(f"[iteration {self.iteration}/{self.max_iterations}]")

            response = self.client.call(**self._call_opts())
            parsed = self.builder.parse_response(response)

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"])
            else:
                return self._extract_text(parsed["content"])

    def _resolve_max_iterations(self, task_settings, explicit):
        if explicit is not None:
            return int(explicit)
        if task_settings and hasattr(self.context.task, "max_iterations"):
            return self.context.task.max_iterations(task_settings)
        return self.MAX_ITERATIONS

    def _resolve_max_output_tokens(self, task_settings, explicit):
        if explicit is not None:
            return explicit
        if task_settings and hasattr(self.context.task, "max_output_tokens"):
            return self.context.task.max_output_tokens(task_settings)
        return None

    def _iteration_limit_reached(self):
        return self.max_iterations > 0 and self.iteration >= self.max_iterations

    def _call_opts(self):
        return {"max_output_tokens": self.max_output_tokens} if self.max_output_tokens else {}

    # One final, tools-disabled model call so the agent ends the turn in
    # character rather than aborting. Runs *outside* the counted loop: it
    # never re-checks the limits (so it cannot re-trigger) and does not
    # increment self.iteration. Falls back to a deterministic message if the
    # call fails.
    def _wrap_up(self, reason):
        self.context.add_message("user", self.WRAP_UP_DIRECTIVE)
        try:
            response = self.client.call(tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS)
            text = self._extract_text(self.builder.parse_response(response)["content"])
            return text if text.strip() else self._fallback_message(reason)
        except ApiError:
            return self._fallback_message(reason)

    def _fallback_message(self, reason):
        return (
            f"I reached my {self.max_iterations}-action limit for this turn before "
            f"finishing ({reason}). Ask me to continue and I'll pick up from here."
        )

    @staticmethod
    def _extract_text(content):
        return "".join(b["text"] for b in content if b.get("type") == "text")

    def _handle_tool_calls(self, content):
        self.context.add_message("assistant", content)

        for block in content:
            if block.get("type") != "tool_use":
                continue

            name = block["name"]
            args = block["input"]
            use_id = block["id"]

            print(f"  tool call → {name}({args})")
            result = self.registry.dispatch(name, args)
            result_str = str(result)
            print(f"  tool result → {result_str[:61]}")

            self.context.add_message("tool_result", result_str, tool_use_id=use_id)
```

Needs `from .errors import ApiError` at the top.

Notes on the port, matched line-for-line against Ruby:

- **`parsed[:stop_reason]`/`parsed[:content]` (Ruby symbol keys) become
  `parsed["stop_reason"]`/`parsed["content"]` (Python string keys)** — this
  matches every existing backend's JSON-shaped dicts (`"type"`, `"text"`,
  etc. are already string keys throughout this codebase), so
  `parse_response` returning string keys is the consistent choice, not a
  deviation.
- **`result.to_s[0..60]` → `result_str[:61]`** — Ruby's inclusive range
  `0..60` is 61 characters; Python's `[:61]` slice matches exactly.
- **`respond_to?(:max_iterations)` → `hasattr(self.context.task,
  "max_iterations")`** — duck-typing check preserved. In practice this is
  always true once `tasks/base.py` gets the new classmethods (every task
  subclasses `Base`), same as Ruby, but the guard stays for parity and for
  safety if `context.task` is ever `None`.
- **`@iteration.positive?` → `self.max_iterations > 0`** — Ruby's
  `Integer#positive?` has no single-method Python equivalent; a plain
  comparison is the idiomatic substitute.
- **Private-method naming**: this codebase already prefixes internal
  helpers with `_` (`Client._open_connection`, `Base._fetch`) rather than
  relying on Ruby's `private` keyword — `Agent`'s helper methods follow
  that existing convention (`_resolve_max_iterations`, `_wrap_up`, etc.)
  rather than introducing name-mangling or a different pattern.

## `examples/example.py`

Rewrite per Ruby's `examples/example.rb`, reusing Step 4's existing
scaffolding (`sys.path` insert, `BOUKENSHA_DIR` setdefault, `Config()`,
provider/backend-construction branch) but building an `Agent` instead of
calling `Client` directly, and anchoring tool paths to the step directory
instead of the process's cwd:

1. Same `Config`/`system_prompt`/`Context`/`Registry` setup as Step 4's
   example.
2. `base_dir = Path(__file__).resolve().parents[1]` — the step root
   (`05_agent_loop/`), mirroring Ruby's `File.expand_path("..", __dir__)`
   from inside `examples/`.
3. Resolve `provider`/`model` and build the backend — same five-way branch
   as Step 4, unchanged.
4. `builder = PromptBuilder(ctx, backend)`; `client = Client(builder)`;
   `agent = Agent(context=ctx, registry=registry, builder=builder,
   client=client, task_settings=player_settings)` — built **before** the
   tools are registered, matching Ruby's ordering (the agent holds
   references to `registry`/`context`, not snapshots, so registration order
   relative to agent construction doesn't matter functionally, but the port
   preserves it for a literal match).
5. Register `"read_file"` — description `"Read the contents of a file from
   disk"`, `parameters={"path": {"type": "string", "description": "The
   file path to read"}}`, block
   `lambda path: (base_dir / path).read_text()` — anchored to `base_dir`,
   **not** the bare `Path(path)` Step 4 used (Ruby 05 changed this from
   `File.read(path)` to `File.read(File.expand_path(path, base_dir))`,
   because the agent now genuinely walks the filesystem across multiple
   tool calls and needs a stable anchor independent of the caller's cwd).
6. Register `"list_directory"` — description `"List the files in a
   directory"`, `parameters={"path": {"type": "string", "description":
   "The directory path to list"}}`, block
   `lambda path: ", ".join(f for f in os.listdir(base_dir / path) if not f.startswith("."))`
   — note the join separator changed from `"\n"` (Step 4) to `", "` (Ruby
   05's `.join(", ")`).
7. `ctx.add_message("user", "Read the README.md file and summarise what
   this MUD player assistant framework can do.")` — replaces Step 4's
   `"What files are in the current directory?"` prompt; this one requires
   the model to actually chain both tools (list or infer the file, read
   it, summarize), which is the point of demoing a loop instead of a
   single round-trip.
8. Print header `=== BOUKENSHA Step 5: Agent Loop ===`, then `Config:`,
   `Provider:`, `Model:`, `f"Max iterations: {Player.max_iterations(player_settings)}"`,
   `f"Max output tokens: {Player.max_output_tokens(player_settings)}"`.
9. `result = agent.run()`; print blank line, `=== FINAL RESPONSE ===`,
   then `result`.

This example makes **real, potentially multiple** network calls (one per
loop iteration) and will actually hit whichever provider
`tasks.player.provider` resolves to.

## `bin/python/05_agent_loop` fix

Change the broken venv-source line to match every other launcher in
`bin/python/` (identical fix already applied to `bin/python/04_api_client`):
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/05_agent_loop"
python3 examples/example.py
```
(`bin/ruby/05_agent_loop` is already correct and needs no change.)

## Expected output / how to verify parity

Same situation as Step 4 — this makes real HTTP calls, so "expected
output" isn't a fixed transcript. Verify parity by:

1. Confirming both languages resolve the same provider/model from
   `settings.yaml` (the duplicate-key bug flagged in the 04 plan may still
   be relevant here — check `.boukensha/settings.yaml` at run time).
2. Running `bundle exec ruby examples/example.rb` under
   `ruby/05_agent_loop` and `./week1_baseline/bin/python/05_agent_loop`
   (once fixed) or `python3 examples/example.py` directly under
   `python/05_agent_loop`.
3. Confirming both print the same header/config/provider/model/
   max-iterations/max-output-tokens lines, then a per-iteration trace
   (`[iteration N/M]`, `tool call → ...`, `tool result → ...`) that
   converges on a final summary of `README.md`'s contents. Exact wording
   will differ (live model call) but tool-call sequence and structure
   should be comparable.
4. Deliberately setting a very low `max_iterations` (e.g. `1`) in a scratch
   `settings.yaml` to confirm both languages hit the wrap-up path and
   return a graceful summary rather than raising or looping forever.
5. Deliberately breaking the API key to confirm the wrap-up path's
   `rescue ApiError` / `except ApiError` fallback message fires in both
   languages when the wind-down call itself fails.

## Carried-over known gaps (not fixed in this port, for parity)

Same items the Ruby README already flags as deliberately unfixed at this
step:
- No persistent memory or context compaction — the loop keeps appending
  messages for the whole turn; long-running turns grow the context
  unbounded within the `max_iterations` ceiling. That's a later step.
- No cost/usage logging wired into the loop yet, even though backends
  already expose `estimate_cost`/`context_window` from Step 3/4.
- `LoopError` exists but is unused (see "dead code" note above) — carried
  forward, not fixed.
- Settings file must be exactly `.yaml`, not `.yml` (carried from 00).

## Decisions already made (from the 00–04 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories; this step needs
  `bin/python/05_agent_loop` fixed (see above), `bin/ruby/05_agent_loop`
  needs no change.
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+ (unchanged; this step adds no new
  version-sensitive stdlib usage).
- Output parity: exact field-for-field match where behavior is
  deterministic (config/provider/model/max-iteration lines); the model's
  actual responses and tool-call sequence remain inherently
  non-deterministic, same caveat as Step 4.
- `requirements.txt`: unchanged, no new dependency.
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: everything from `04_api_client` carries
  over unchanged except the additions listed above — no regeneration of
  working files, honoring the "only port what actually changed" instruction
  this plan was written under.
- README vs. actual Ruby implementation: follow the executable code, not
  aspirational README text — directly relevant here since Ruby 05's own
  README claims `context.rb` was updated when the file is actually
  byte-identical to Step 4's; the Python README should describe the
  *current* Ruby behavior, verified against the diff, not copy that claim.

## Remaining cosmetic decisions

- **String keys (`"stop_reason"`/`"content"`) vs. Ruby's symbol keys
  (`:stop_reason`/`:content`) for `parse_response`'s return value.** Chosen
  to match this codebase's existing convention of JSON-shaped string-keyed
  dicts everywhere else (`"type"`, `"text"`, `"name"`, `"input"`, etc.).
  Revisit only if a later step wants stricter typing (e.g. a `TypedDict` or
  dataclass for the normalized shape) — not needed yet, Ruby doesn't do
  that either.
- **Leading-underscore convention for `Agent`'s private helpers.** Matches
  existing precedent (`Client._open_connection`, `Base._fetch`) rather than
  introducing name-mangled double-underscore methods or a different style.
- **Not wiring up `LoopError`.** Ported for parity since Ruby defines it,
  but left unraised since Ruby never raises it either — inventing a raise
  site would be adding behavior Ruby doesn't have, not porting.
