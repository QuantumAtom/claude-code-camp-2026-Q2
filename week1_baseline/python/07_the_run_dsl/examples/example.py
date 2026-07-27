import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

# Config is loaded automatically inside boukensha.run() — system prompt,
# model, and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by
# default. You can still override any of them as keyword arguments.

print("=== BOUKENSHA Step 7: The boukensha.run DSL ===")
print()
print(f"Config: {boukensha.config()}")
print()

base_dir = Path(__file__).resolve().parents[1]


def register_tools(dsl):
    dsl.tool(
        "read_file",
        "Read the contents of a file from disk",
        {"path": {"type": "string", "description": "The file path to read"}},
        lambda path: (base_dir / path).read_text(),
    )

    dsl.tool(
        "list_directory",
        "List the files in a directory",
        {"path": {"type": "string", "description": "The directory path to list"}},
        lambda path: ", ".join(f for f in os.listdir(base_dir / path) if not f.startswith(".")),
    )


result = boukensha.run(
    task="Read the README.md file and summarise what this MUD player assistant framework can do.",
    configure=register_tools,
)

print()
print("=== FINAL RESPONSE ===")
print(result)
