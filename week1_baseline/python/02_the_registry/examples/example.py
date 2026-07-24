import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha.config import Config
from boukensha.tasks.player import Player
from boukensha.context import Context
from boukensha.registry import Registry
from boukensha.errors import UnknownToolError

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

config = Config()
player_settings = config.tasks("player")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
)

ctx = Context(task=Player, system=system_prompt)
registry = Registry(ctx)

# Notice that we now register the tools through the registry instead of directly
# on the context in the previous step.
# They will still be attached to context which is why we pass it into
# our registry when we initialize it.
registry.tool(
    "move",
    "Move the player in a direction (north, south, east, west, up, down)",
    {"direction": {"type": "string"}},
    lambda direction: f"You move {direction} into a torch-lit corridor.",
)

registry.tool(
    "shout",
    "Shout a message so everyone in the zone can hear it",
    {"message": {"type": "string"}},
    lambda message: message.upper(),
)

print("=== Boukensha Step 2: Tool Registry ===")
print()
print(f"Config:  {config}")
print(f"Context: {ctx}")
print("Tools:")
for t in ctx.tools.values():
    print(f"  {t}")
print()

# Here we are mimicking what the agent would do when
# it needs to call a tool from the registry. We are
# still missing the actual code that would decide when
# to call the registry for a tool.
print("Dispatching 'shout' with message='dragon spotted'...")
result = registry.dispatch("shout", {"message": "dragon spotted"})
print(f"Result: {result}")
print()

print("Dispatching 'move' with direction='north'...")
result = registry.dispatch("move", {"direction": "north"})
print(f"Result: {result}")
print()

try:
    registry.dispatch("flee")
except UnknownToolError as e:
    print(f"UnknownToolError caught: {e}")
