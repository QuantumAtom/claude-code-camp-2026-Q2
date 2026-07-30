import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

cfg = boukensha.config()
print(f"Config: {cfg}")
print(f"API key set? {os.environ.get('ANTHROPIC_API_KEY') is not None}")
print()

# mud: comes from config (.boukensha/settings.yaml's `mud:` block) automatically.
result = boukensha.run(
    task="Connect to the MUD, look at your surroundings, check your score, "
         "then look at the available exits and tell me what you see.",
    working_dir=False,  # no filesystem tools needed for MUD play
)

print()
print("=== FINAL RESPONSE ===")
print(result)
