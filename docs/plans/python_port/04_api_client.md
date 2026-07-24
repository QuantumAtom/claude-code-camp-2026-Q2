# Python Port Plan — 04_api_client

## Goal

Port `week1_baseline/ruby/04_api_client` to
`week1_baseline/python/04_api_client`. Same behavior, same on-disk config
format, same retry/error semantics, new language. No new features — this is
a straight port of the existing step. **Plan only — no source files are
touched by writing this document.**

**Starting point: `week1_baseline/python/04_api_client` already exists as a
byte-for-byte copy of the finished `week1_baseline/python/03_prompt_builder`
tree.** Confirmed via `diff -rq` against every file: `config.py`,
`context.py`, `tool.py`, `message.py`, `registry.py`, `prompt_builder.py`,
`tasks/base.py`, `tasks/player.py`, and the entire `backends/` package are
**identical**, and Ruby 04's equivalents are identical to Ruby 03's too
(confirmed the same way) — this step adds a client on top, it doesn't touch
serialization. `README.md`, `examples/example.py`, and `requirements.txt`
are also still exactly Step 3's content and need rewriting/checking for this
step's topic. `prompts/system.md`, however, **is not** identical between
Ruby 03 and Ruby 04 (see below) — the copied Python file still has the old
Step‑3 wording and needs updating. So, same shape as the 03 port: this is an
**in-place edit of the copied tree**, not a from-scratch build.

## Source of truth (what to port)

| Ruby file | Purpose | Status |
|---|---|---|
| `ruby/04_api_client/README.md` | Design spec — Client role, retry/error semantics, "no dependencies" philosophy, per-backend raw response shapes | Rewrite (new topic) |
| `ruby/04_api_client/lib/boukensha.rb` | Adds `require_relative "boukensha/client"` vs 03 | `__init__.py` needs the new export |
| `ruby/04_api_client/lib/boukensha/client.rb` | **NEW** — `Client#call`: builds the HTTP request from `PromptBuilder`, retries transient errors and retryable status codes with exponential backoff, raises `ApiError` on final failure, else returns parsed JSON | New — the core deliverable of this step |
| `ruby/04_api_client/lib/boukensha/errors.rb` | Adds `ApiError < StandardError` vs 03 | `errors.py` missing this — **gap to fill** |
| `ruby/04_api_client/lib/boukensha/config.rb` | `PROMPTS_DIR` computed with **one extra `../`** vs 03 — see "Ruby bug" note below | **Do not port the bug** — Python's existing formula already lands correctly, see below |
| `ruby/04_api_client/lib/boukensha/tasks/base.rb` | Two small fixes vs 03: error-message text now says `settings.yaml` (was `settings.yml`, a typo fix), and the private `fetch` helper now guards `return nil unless settings.is_a?(Hash)` before indexing | `tasks/base.py` needs both fixes ported — legitimate small bugfixes, not new behavior |
| `ruby/04_api_client/prompts/system.md` | Rewritten prompt text: `"You are Boukensha, an autonomous player exploring a CircleMUD world. Use available tools to observe the world, act deliberately, and explain only what matters for the current turn."` (was the Step‑3 "MUD player assistant" wording) | `prompts/system.md` still has the **old** Step‑3 text — must be updated |
| `ruby/04_api_client/lib/boukensha/tool.rb`, `message.rb`, `context.rb`, `registry.rb`, `prompt_builder.rb`, `tasks/player.rb`, `backends/*.rb` | Byte-identical to Ruby 03 (confirmed via `diff -rq`) | Already correct in the Python copy, leave unchanged |
| `ruby/04_api_client/examples/example.rb` | Rewritten: registers `read_file`/`list_directory` tools that touch the **real filesystem** (not canned strings), seeds a single user message, builds a `Client` from the `PromptBuilder`, and prints the raw parsed JSON response | Rewrite — Python's `example.py` is currently Step 3's `look`/`move` prompt-serialization demo |
| `ruby/04_api_client/Gemfile` | Still only `dotenv` — **no new gem** for HTTP (Ruby deliberately uses stdlib `net/http`, per the README's "No Dependencies" section) | `requirements.txt` needs **no new dependency**; Python side should mirror the stdlib-only philosophy (see "New class behavior" below) |
| `week1_baseline/bin/ruby/04_api_client` | Bash wrapper — **confirmed broken**: still `cd`s into `ruby/03_prompt_builder` and runs *that* example, not 04's | Out of scope to fix (Ruby side), but flagged — see "Known pre-existing bugs" below; verify parity by calling `ruby/04_api_client/examples/example.rb` directly, not this launcher |
| `week1_baseline/bin/python/04_api_client` | Bash wrapper — **confirmed broken**: sources `$ROOT/code/virtualenv/claude/bin/activate`, a path that doesn't exist in this repo, instead of `$ROOT/.venv/bin/activate` | **In scope, must fix** — this is the Python launcher for the step we're building |

Also relevant for context (not ported, background only):
`docs/plans/python_port/03_prompt_builder.md` (the plan template this doc
follows), `.boukensha/settings.yaml` at the repo root (currently has a
duplicate-key bug you already found — `tasks.player` defines `provider`/
`model`/`prompt_override` twice, and YAML silently keeps only the last
occurrence, so it currently resolves to `provider: anthropic`, not
`gemini` — this affects what you'll actually see when *running* the ported
example, not the port itself; not something this plan fixes unless you ask).

## Known pre-existing bugs found while researching this plan (not fixed by porting, flagged for awareness)

1. **`ruby/04_api_client/lib/boukensha/config.rb`'s `PROMPTS_DIR` is wrong.**
   It's defined as `File.expand_path("../../../prompts", __dir__)` — one
   more `../` than Step 3's (correct) `"../../prompts"`. From
   `lib/boukensha/config.rb`, two `../` lands at the project root
   (`04_api_client/`); three lands **one level above it**, at
   `ruby/prompts`, which doesn't exist. I verified this in a real Ruby
   process: `Config::PROMPTS_DIR` currently resolves to
   `week1_baseline/ruby/prompts`, not
   `week1_baseline/ruby/04_api_client/prompts`. It's silently masked today
   because the live `settings.yaml` sets `prompt_override.system: true`,
   so the code path that would read from `PROMPTS_DIR` never actually
   triggers — but if prompt override were ever turned off, Ruby's default
   system prompt would fail to load.
   **Plan decision: do not reproduce this in Python.** Python's
   `Config.PROMPTS_DIR` (already shipped in `03_prompt_builder`, and
   already copied unchanged into this step's tree) is computed as
   `Path(__file__).resolve().parent.parent / "prompts"` — a
   filesystem-relative calculation, not a hand-counted `../` string — so it
   already lands correctly at `04_api_client/prompts` with **zero changes**
   needed. This is a deliberate, favorable divergence from the Ruby source,
   not an oversight; the README should say so explicitly (see below) so
   nobody "fixes" Python to match Ruby's bug later.
2. **`bin/ruby/04_api_client` runs the wrong example** (`cd`s into
   `03_prompt_builder`). Ruby-side, out of scope for a Python port, but
   worth fixing separately since it currently makes the "reference"
   behavior impossible to reproduce via the documented launcher.
3. **`bin/python/04_api_client` sources a venv path that doesn't exist**
   (`$ROOT/code/virtualenv/claude/bin/activate`). This one *is* in scope —
   it's the launcher for the code this plan ports — see the fix below.
4. **`.boukensha/settings.yaml` has a duplicate-key bug** (already reported
   to you separately): `tasks.player` sets `provider`/`model`/
   `prompt_override` twice in the same mapping; YAML keeps only the last
   occurrence, so the live config currently resolves to `anthropic`/
   `claude-sonnet-4-6`, not the `gemini` values that appear first (and are
   dead). Not part of this port's scope, but it means a live test run of
   the ported example will hit Anthropic, not Gemini, until that file is
   fixed — worth knowing before comparing Ruby vs. Python output side by
   side.

## Concrete delta (the actual work)

**ADD (net-new files):**
- `boukensha/client.py` — `Client` class (see below)

**FILL (small gaps/fixes):**
- `boukensha/errors.py` — add `ApiError(Exception): pass`
- `boukensha/tasks/base.py` — fix the two error-message strings to say
  `settings.yaml` (currently already correct in the Python copy? — **check
  at implementation time**; Ruby's messages were `settings.yml` in Step 3
  and are fixed to `settings.yaml` in Step 4, so confirm which the current
  Python copy has and correct it to `settings.yaml` if needed) and add a
  `isinstance(settings, dict)` guard to `_fetch` before calling
  `settings.get(key)`, matching Ruby's new `return nil unless
  settings.is_a?(Hash)` line
- `prompts/system.md` — replace the Step‑3 "MUD player assistant" text with
  Ruby 04's new wording (the CircleMUD/"observe the world, act
  deliberately" prompt)

**CHANGE (already present as 03's copy, must be rewritten for this step's topic):**
- `boukensha/__init__.py` — add `Client` and `ApiError` to the imports and
  `__all__` list
- `examples/example.py` — currently Step 3's `look`/`move` demo that only
  builds a payload. Rewrite per Ruby's `examples/example.rb`: register
  `read_file` (reads a real file from disk) and `list_directory` (lists a
  real directory, hiding dotfiles) tools, seed one `"user"` message
  (`"What files are in the current directory?"` — no simulated
  assistant/tool-result turns this time, unlike Step 3's three-message
  seed), resolve provider/model and build the backend exactly as Step 3's
  example already does, then wrap in `Client` and print the **raw JSON
  response** instead of the payload
- `README.md` — full rewrite: Client's role and one-method API, the retry/
  backoff/error model, "no dependencies" framing (translate to Python's own
  stdlib-only story — see below), per-backend raw response shape examples,
  and the PROMPTS_DIR divergence note from above

**LEAVE AS-IS (confirmed identical to Ruby 03, and Ruby 03 == Ruby 04 for these):**
- `boukensha/tool.py`, `boukensha/message.py`, `boukensha/context.py`,
  `boukensha/registry.py`, `boukensha/prompt_builder.py`
- `boukensha/tasks/player.py`
- `boukensha/backends/` (all six files)
- `boukensha/config.py` (see PROMPTS_DIR note — no change needed, it's
  already correct)
- `requirements.txt` (`PyYAML`, `python-dotenv` — **no HTTP dependency
  added**, matching Ruby's deliberate stdlib-only choice)

**FIX outside the step dir:**
- `bin/python/04_api_client` — replace the bogus
  `$ROOT/code/virtualenv/claude/bin/activate` line with
  `$ROOT/.venv/bin/activate`, matching every other `bin/python/*` launcher
  in this repo

**CLEANUP (opportunistic):**
- Delete the stray `boukensha/__pycache__/`, `boukensha/backends/__pycache__/`,
  and `boukensha/tasks/__pycache__/` directories already present in the
  copied tree (gitignored, harmless, but no reason to keep them)

## Target structure

```
week1_baseline/python/04_api_client/
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

Identical shape to `03_prompt_builder`, plus `client.py`. No `pyproject.toml`
(unchanged decision).

## Python environment setup

Same shared-venv / per-step-manifest model as 00–03.

- Venv path: `<repo root>/.venv`.
- `requirements.txt`: unchanged from 03 (`PyYAML`, `python-dotenv`) —
  `client.py` uses only the standard library (see below), so no
  `pip install` beyond what's already there.
- `bin/python/04_api_client` needs its venv-source line fixed (see above)
  before it will run at all.

## Ruby → Python file mapping

| Ruby | Python | Notes |
|---|---|---|
| `lib/boukensha.rb` | `boukensha/__init__.py` | Add `Client`, `ApiError` to exports |
| `lib/boukensha/client.rb` | `boukensha/client.py` | NEW — see below |
| `lib/boukensha/errors.rb` | `boukensha/errors.py` | Add `ApiError` |
| `lib/boukensha/config.rb` | `boukensha/config.py` | No change (Ruby's bug doesn't reproduce in Python's path-based formula) |
| `lib/boukensha/tasks/base.rb` | `boukensha/tasks/base.py` | Port the `settings.yaml` message-text fix + `isinstance(settings, dict)` guard |
| `prompts/system.md` | `prompts/system.md` | Update text to match Ruby 04 |
| `lib/boukensha/tool.rb` etc. (unchanged files) | matching `.py` files | No change |
| `examples/example.rb` | `examples/example.py` | Rewrite for the API-client demo |
| `Gemfile` (`dotenv` only) | `requirements.txt` (unchanged) | Both stay dependency-free for HTTP |
| `README.md` | `README.md` | Port Client API table, retry model, response-shape examples |
| `bin/ruby/04_api_client` (broken, out of scope) | `bin/python/04_api_client` (broken, **in scope**) | Fix the venv source path |

## New class behavior (the actual porting work)

### `ApiError` (`errors.rb` → `errors.py`)

Bare exception, same shape as the existing two:
```python
class ApiError(Exception):
    pass
```

### `tasks/base.py` fixes

```python
@classmethod
def _fetch(cls, settings, key):
    if not isinstance(settings, dict):
        return None
    return settings.get(key)
```
Plus updating the two `ValueError` messages in `provider`/`model` to read
`"tasks.{task_name}.provider is required in settings.yaml"` /
`"...model is required in settings.yaml"` (confirm the current Python
copy's exact wording at implementation time and correct only if it still
says `.yml`).

### `Client` (`client.rb` → `client.py`) — the core piece

Ruby's implementation, precisely, since the retry/backoff arithmetic must
match:

- Constants: `RETRYABLE_STATUS_CODES = [408, 409, 429, 500, 502, 503, 504]`,
  `MAX_RETRIES = 3`, `BASE_RETRY_DELAY = 0.5`
- `TRANSIENT_ERRORS` — a fixed list of exception classes that trigger a
  retry when raised *during the request itself* (as opposed to a bad status
  code, which is handled separately): `EOFError`, `Errno::ECONNRESET`,
  `Errno::ECONNREFUSED`, `Net::OpenTimeout`, `Net::ReadTimeout`,
  `OpenSSL::SSL::SSLError`, `SocketError`, `Timeout::Error`
- `initialize(builder)` — stores the `PromptBuilder`
- `call(max_output_tokens: 1024)`:
  1. Parse `builder.url`, open an `http.use_ssl = (scheme == "https")`
     connection, `verify_mode = VERIFY_PEER` (no explicit `ca_file` — the
     Ruby README explicitly calls out that hardcoding
     `OpenSSL::X509::DEFAULT_CERT_FILE` broke on Linux/WSL2, so it's
     deliberately omitted to let the platform default resolve certs)
  2. Build a `Net::HTTP::Post` with `builder.headers` and a JSON-encoded
     body from `builder.to_api_payload(max_output_tokens:)`
  3. Retry loop: increment `attempts`; on a transient exception, raise
     `ApiError` once `attempts > MAX_RETRIES` (i.e. after 1 initial try + 3
     retries = 4 total attempts), otherwise sleep
     `BASE_RETRY_DELAY * 2**(attempt - 1)` and retry; on a **retryable
     status code** (one of `RETRYABLE_STATUS_CODES`) with
     `attempts <= MAX_RETRIES`, sleep the same backoff and retry; otherwise
     break out of the loop
  4. After the loop, if the final response isn't 2xx, raise `ApiError`
     with the attempt count (pluralized: `"attempt"` vs `"attempts"`) and
     the response code/body
  5. Otherwise `JSON.parse(response.body)` and return it

Python port — using **`http.client`**, not `requests` and not
`urllib.request`. Rationale: Ruby deliberately avoids third-party HTTP gems
to keep the request visible (README: *"This is intentional — the HTTP call
itself is trivial and should be visible, not hidden behind a library"*), so
adding `requests` to `requirements.txt` would contradict the step's own
stated point. `urllib.request.urlopen` was also considered and rejected: it
**raises `HTTPError` for any non-2xx status by default**, which would force
working around `urlopen`'s control flow just to inspect `response.code`/
`response.body` on failure — the opposite of Ruby's `Net::HTTP`, which
returns a plain response object regardless of status and lets the caller
decide. `http.client.HTTPConnection`/`HTTPSConnection` matches Ruby's
`Net::HTTP` behavior directly: it never raises on status code, and
`response.status`/`response.read()` are always available.

```python
import http.client
import json
import socket
import ssl
import time
from urllib.parse import urlparse

from .errors import ApiError

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
TRANSIENT_ERRORS = (
    http.client.HTTPException,
    ConnectionResetError,
    ConnectionRefusedError,
    ssl.SSLError,
    socket.gaierror,
    socket.timeout,
    TimeoutError,
)
MAX_RETRIES = 3
BASE_RETRY_DELAY = 0.5


class Client:
    def __init__(self, builder):
        self.builder = builder

    def call(self, max_output_tokens=1024):
        parsed = urlparse(self.builder.url())
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        headers = self.builder.headers()
        body = json.dumps(self.builder.to_api_payload(max_output_tokens=max_output_tokens))

        attempts = 0
        response = None
        response_body = None

        while True:
            attempts += 1
            conn = self._open_connection(parsed)
            try:
                try:
                    conn.request("POST", path, body=body, headers=headers)
                    response = conn.getresponse()
                    response_body = response.read()
                except TRANSIENT_ERRORS as e:
                    if attempts > MAX_RETRIES:
                        raise ApiError(
                            f"API request failed after {attempts} attempts: {type(e).__name__}: {e}"
                        ) from e
                    time.sleep(self._retry_delay(attempts))
                    continue
            finally:
                conn.close()

            if response.status in RETRYABLE_STATUS_CODES and attempts <= MAX_RETRIES:
                time.sleep(self._retry_delay(attempts))
                continue

            break

        if not (200 <= response.status < 300):
            suffix = "" if attempts == 1 else "s"
            raise ApiError(
                f"API request failed after {attempts} attempt{suffix} "
                f"({response.status}): {response_body.decode('utf-8', errors='replace')}"
            )

        return json.loads(response_body)

    @staticmethod
    def _open_connection(parsed):
        # 60s matches Net::HTTP's default open_timeout/read_timeout, which
        # Ruby never overrides — Python's http.client has no timeout by
        # default (blocks forever), so this is set explicitly for parity.
        if parsed.scheme == "https":
            context = ssl.create_default_context()
            return http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=60, context=context)
        return http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=60)

    @staticmethod
    def _retry_delay(attempt):
        return BASE_RETRY_DELAY * (2 ** (attempt - 1))
```

Two deliberate, documented divergences from Ruby, both **favorable** and
both worth a callout in the README so they don't look like accidental
drift:

1. **No SSL certificate workaround needed.** `ssl.create_default_context()`
   locates the system trust store automatically on every platform Python
   supports — the macOS/Linux/WSL2 `DEFAULT_CERT_FILE` pitfall the Ruby
   README warns about (and tells the reader to work around manually) simply
   doesn't exist in the Python port.
2. **Explicit 60s timeout.** Ruby gets a 60s open/read timeout "for free"
   from `Net::HTTP`'s defaults, without ever writing the number down.
   Python's `http.client` has no default timeout (it blocks forever), so
   the port makes the equivalent value explicit rather than silently
   inheriting an infinite wait — same effective behavior, more honest code.

`TRANSIENT_ERRORS` is a best-effort mapping, not a 1:1 translation (Ruby and
Python don't share an exception hierarchy): `http.client.HTTPException`
covers protocol-level failures (Ruby's `EOFError`/malformed-response
cases), `ConnectionResetError`/`ConnectionRefusedError` cover Ruby's
`Errno::ECONNRESET`/`Errno::ECONNREFUSED`, `socket.gaierror` covers DNS
failures (Ruby's `SocketError`), `ssl.SSLError` covers
`OpenSSL::SSL::SSLError`, and `socket.timeout`/`TimeoutError` cover both of
Ruby's `Net::OpenTimeout`/`Net::ReadTimeout`/`Timeout::Error` (note:
`socket.timeout` is an alias of `TimeoutError` as of Python 3.10, but both
are listed for clarity and for correctness on 3.9, this repo's stated
minimum version).

## `examples/example.py`

Rewrite per Ruby's `examples/example.rb`, reusing Step 3's existing
scaffolding (`sys.path` insert, `BOUKENSHA_DIR` setdefault, `Config()`,
provider/backend-construction branch — that part is untouched) but with a
new tool set and a real network call at the end:

1. Same `Config`/`system_prompt`/`Context`/`Registry` setup as Step 3's
   example (including `default_prompts_dir=Config.PROMPTS_DIR`).
2. Register `"read_file"` — description `"Read the contents of a file from
   disk"`, `parameters={"path": {"type": "string", "description": "The file
   path to read"}}`, block `lambda path: Path(path).read_text()`.
3. Register `"list_directory"` — description `"List files in a directory"`,
   `parameters={"path": {"type": "string", "description": "The directory
   path to list"}}`, block
   `lambda path: "\n".join(f for f in os.listdir(path) if not f.startswith("."))`.
4. `ctx.add_message("user", "What files are in the current directory?")` —
   **only one** seeded message this time (Ruby 04's example drops Step 3's
   simulated assistant/tool-result turns).
5. Resolve `provider`/`model` and build the backend exactly as Step 3's
   example does (same five-way branch, same env-var-per-provider pattern,
   same `ValueError` on an unrecognized provider) — this part carries over
   unchanged.
6. `builder = PromptBuilder(ctx, backend)`; `client = Client(builder)`.
7. Print header `=== BOUKENSHA Step 4: API Client ===`, then `Config:`,
   `Provider:`, `Model:`, `f"Sending request to {builder.url()}..."`.
8. `response = client.call()`; print `"Raw response:"` then
   `json.dumps(response, indent=2)`.

This example makes a **real** network call and will actually hit whichever
provider `tasks.player.provider` resolves to — given the live
`settings.yaml` bug noted above, that's currently Anthropic, and needs a
valid `ANTHROPIC_API_KEY` in `.boukensha/.env` to succeed.

## `bin/python/04_api_client` fix

Change the broken venv-source line to match every other launcher in
`bin/python/`:
```bash
#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$ROOT/.venv/bin/activate"
cd "$(dirname "$0")/../../python/04_api_client"
python3 examples/example.py
```
(`bin/ruby/04_api_client` is left untouched — fixing it is a Ruby-side bug
fix outside this port's scope, flagged above for your awareness.)

## Expected output / how to verify parity

Because this step makes a real HTTP call, "expected output" isn't a fixed
JSON blob the way Steps 2–3 were — the raw response depends on the live
provider/model and what the model actually says. Verify parity by:

1. Fixing (or working around) the `settings.yaml` duplicate-key bug so both
   implementations resolve the same provider/model, or exporting a
   scratch `BOUKENSHA_DIR` with a clean single-provider config for testing.
2. Running `bundle exec ruby examples/example.rb` under
   `ruby/04_api_client` directly (not via `bin/ruby/04_api_client`, which
   is broken) and `./week1_baseline/bin/python/04_api_client` (once fixed)
   or `python3 examples/example.py` directly under `python/04_api_client`.
3. Confirming both print the same header/config/provider/model lines, hit
   the same URL, and get back a response shaped like the provider's real
   API — content will differ turn to turn (it's a live model call) but the
   **shape** (top-level keys, `content`/`message` field names) should
   match the README's documented examples for that backend.
4. Deliberately breaking something (bad API key, or a bogus
   `BOUKENSHA_DIR`) to confirm `ApiError` fires in both languages with a
   non-2xx status.

## Carried-over known gaps (not fixed in this port, for parity)

Same items the Ruby README already flags as deliberately unfixed:
- Still no tool-call loop — the API response may say `stop_reason:
  "tool_use"` (Anthropic) or add a `tool_calls` array (Ollama/OpenAI-style),
  but nothing in this step reads that and actually dispatches the tool.
  That's Step 5 (the Agent Loop).
- `Client` only performs one POST and returns the raw parsed JSON; no
  streaming, no multi-turn orchestration.
- Settings file must be exactly `.yaml`, not `.yml` (carried from 00,
  reinforced by this step's error-message fix).

## Decisions already made (from the 00–03 ports, carried forward)

- Tooling: plain `pip` + `requirements.txt`, no `uv`/`pyproject.toml`.
- `bin/` split into per-language subdirectories; this step needs
  `bin/python/04_api_client` fixed (see above), `bin/ruby/04_api_client` is
  a pre-existing bug out of scope.
- Tests: parity with Ruby, i.e. `examples/example.py` smoke test only, no
  pytest suite.
- Minimum Python version: 3.9+ (relevant here specifically because of the
  `socket.timeout`/`TimeoutError` aliasing change in 3.10 — the port lists
  both explicitly rather than assuming 3.10+).
- Output parity: exact field-for-field match where the behavior is
  deterministic (config/provider/model lines, URL, error paths); the raw
  model response itself is inherently non-deterministic once this step
  starts making real network calls, which is new for this step.
- `requirements.txt`: unchanged, no HTTP library added — matches Ruby's
  explicit "no dependencies" stance for the client.
- One shared venv at the repo root; per-step manifests.
- Reuse of already-ported code: everything from `03_prompt_builder` carries
  over unchanged except the two small `tasks/base.py` fixes and the
  `prompts/system.md` text update.
- README vs. actual Ruby implementation: follow the executable code, not
  aspirational README text — directly relevant here, since Ruby 04's own
  README shows a stale example run from an old `03_api_client/examples/
  step3.rb` path (an earlier, renumbered version of this tutorial) and has
  a typo (`## Output eaxmple`) — the Python README should describe the
  *current* Ruby behavior, not copy that stale transcript verbatim.

## Remaining cosmetic decisions

- **`http.client` vs. `requests` vs. `urllib.request`.** This plan picks
  `http.client` (stdlib, no new dependency, doesn't raise on non-2xx
  status) as the closest behavioral match to Ruby's `Net::HTTP`. Revisit
  only if a later step's needs (e.g. streaming responses) make `http.client`
  awkward enough that introducing `requests` becomes clearly worth
  breaking the "no dependencies" parity with Ruby.
- **Explicit `timeout=60`.** Chosen to match Ruby's actual (implicit)
  `Net::HTTP` default rather than leaving Python's connection to block
  forever. Revisit only if a later step wants configurable timeouts.
- **Not reproducing the `PROMPTS_DIR` off-by-one bug.** Python's
  `Path`-based formula is correct as already written; deliberately not
  "fixing" it to match Ruby's broken one. Flagged prominently in the README
  so a future contributor doesn't "helpfully" break it to match Ruby.
