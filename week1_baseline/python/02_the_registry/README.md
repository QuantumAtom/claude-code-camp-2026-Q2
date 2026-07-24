# 02 · The Tool Registry (Python)

Python port of [`week1_baseline/ruby/02_the_registry`](../../ruby/02_the_registry/README.md).

The Tool Registry is how BOUKENSHA manages what capabilities the agent can
use. It has two jobs:

1. storing tools
2. dispatching tools when asked

## Environment setup

This repo uses one shared virtual environment at the repository root. Create it
once, then install this step's dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r week1_baseline/python/02_the_registry/requirements.txt
```

## New files

| File | Description |
|---|---|
| `boukensha/registry.py` | The `Registry` class — registers tools and dispatches calls |
| `boukensha/errors.py` | BOUKENSHA-specific error classes |

## How it works

The agent NEVER calls a tool directly. It emits a structured request (name
and args) and the Registry looks up the tool and runs it.

```
Agent:    "Hey registry call move with direction='north'"
Registry: "looking up 'move' in the tool table"
Registry: "Found it, now calling the block with the provided args"
Registry: "Here's the result"
Agent:    "Thanks buddy"
Registry: "That's why you pay me the big tokens"
```

## `Registry`

| Method | Description |
|---|---|
| `tool(name, description, parameters=None, block=None)` | Registers a new tool on the context |
| `dispatch(name, args=None)` | Looks up a tool by name and calls it with the provided args |

```python
registry = Registry(ctx)
registry.tool(
    "move",
    "Move the player in a direction (north, south, east, west, up, down)",
    {"direction": {"type": "string"}},
    lambda direction: f"You move {direction} into a torch-lit corridor.",
)
registry.dispatch("move", {"direction": "north"})
```

## `UnknownToolError`

Raised when `dispatch` is called with a name that has no registered tool. A
harness needs explicit error boundaries — an unrecognised tool name should
never silently fail.

**Example:**
```
UnknownToolError: No tool registered as 'flee'
```

## Considerations

Ruby's `dispatch` has to convert string-keyed args to symbol-keyed kwargs
before calling the block (`args.transform_keys(&:to_sym)`), because the API
returns arguments as string-keyed JSON but Ruby blocks expect symbol
keywords. That translation is a real gotcha in production harnesses, and the
Ruby version makes it visible for learning purposes.

Python has no string/symbol split for keyword arguments — `**args` already
unpacks a string-keyed dict straight into keyword arguments — so this
port's `dispatch` has no equivalent conversion step to perform. It's a
genuine simplification from switching languages, not a corner that got cut.

## Configuration compatibility

The Python and Ruby implementations read the same `.boukensha/` directory.
Resolution order is:

1. `BOUKENSHA_DIR`
2. `~/.boukensha`

The shared directory supports the same `settings.yaml`, `.env`, and
`prompts/<task>/system.md` override layout.

## Files

| File | Purpose |
|---|---|
| `boukensha/config.py` | Shared configuration loader |
| `boukensha/tool.py` | `Tool` dataclass |
| `boukensha/message.py` | `Message` dataclass |
| `boukensha/context.py` | `Context` container |
| `boukensha/registry.py` | `Registry` — registers and dispatches tools |
| `boukensha/errors.py` | `UnknownToolError` |
| `boukensha/tasks/` | Stateless task classes |
| `examples/example.py` | Runnable smoke test |

## Run example

```bash
./week1_baseline/bin/python/02_the_registry
```

Expected output, with the config directory varying by machine:

```text
=== Boukensha Step 2: Tool Registry ===

Config:  #<Boukensha::Config dir=/path/to/repo/.boukensha tasks=player>
Context: #<Context task=player turns=0 tools=2>
Tools:
  #<Tool name=move description=Move the player in a direction (north, so params=['direction']>
  #<Tool name=shout description=Shout a message so everyone in the zone c params=['message']>

Dispatching 'shout' with message='dragon spotted'...
Result: DRAGON SPOTTED

Dispatching 'move' with direction='north'...
Result: You move north into a torch-lit corridor.

UnknownToolError caught: No tool registered as 'flee'
```

Python uses string dictionary keys, so tool parameters display as
`['direction']` rather than Ruby's `[:direction]`.

## Considerations (carried over)

- The default prompt is not scoped per task.
- Settings files must use `.yaml`, not `.yml`.
- There's still no real agent decision loop — `dispatch` is called by hand
  in `example.py` to simulate what an agent would eventually decide to do.
