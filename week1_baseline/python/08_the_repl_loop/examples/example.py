import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha

os.environ.setdefault("BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha"))

# Config is loaded automatically inside boukensha.repl() — system prompt,
# model, and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by
# default.

print(f"Config: {boukensha.config()}")
print()

# The base directory tools will operate relative to — the step 7 folder
# makes a good playground since it already has source files to read.
base_dir = Path(__file__).resolve().parents[2] / "07_the_run_dsl"


def register_tools(dsl):
    dsl.tool(
        "read_file",
        "Read the contents of a file from disk",
        {"path": {"type": "string", "description": "File path (relative to the working directory)"}},
        lambda path: (base_dir / path).read_text(),
    )

    dsl.tool(
        "list_directory",
        "List the files in a directory",
        {"path": {"type": "string", "description": "Directory path (relative to the working directory, or '.' for root)"}},
        lambda path: ", ".join(sorted(f for f in os.listdir(base_dir / path) if not f.startswith("."))),
    )


boukensha.repl(configure=register_tools)
