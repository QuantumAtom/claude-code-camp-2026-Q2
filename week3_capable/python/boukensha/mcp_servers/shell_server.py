"""MCP server exposing the run_command shell tool. Run as a stdio
subprocess by boukensha/tools/shell.py — configuration comes from
environment variables (root dir, timeout, allowed-commands list) rather
than a CLI argument or config file, since that's how the parent process
(boukensha/mcp_client.py's McpClient) launches it.

Tool logic here is identical to the pre-MCP boukensha/tools/shell.py
implementation — only the transport changed.
"""

import os
import subprocess
from typing import Annotated

from pydantic import Field

from mcp.server.fastmcp import FastMCP

ROOT = os.path.abspath(os.environ["BOUKENSHA_MCP_SHELL_ROOT"])
TIMEOUT = int(os.environ.get("BOUKENSHA_MCP_SHELL_TIMEOUT", "30"))

# None (env var unset) = allow all; "" (present but empty) = empty list,
# which rejects every command; "cmd1,cmd2" = that allow-list.
_raw_allowed = os.environ.get("BOUKENSHA_MCP_SHELL_ALLOWED")
ALLOWED_COMMANDS = None if _raw_allowed is None else [c for c in _raw_allowed.split(",") if c.strip()]

mcp = FastMCP("boukensha-shell")


def _oops(msg):
    return f"error: {msg}"


_allowed_note = f" Allowed executables: {', '.join(ALLOWED_COMMANDS)}." if ALLOWED_COMMANDS else ""


@mcp.tool(
    description=(
        "Run a shell command inside the working directory and return its combined stdout+stderr "
        f"output. Commands run with a {TIMEOUT}-second timeout.{_allowed_note}"
    )
)
def run_command(
    command: Annotated[str, Field(description="The shell command to execute (e.g. 'python3 script.py', 'ls -la', 'git status')")],
) -> str:
    if ALLOWED_COMMANDS is not None:
        tokens = str(command).strip().split()
        executable = tokens[0] if tokens else ""
        if executable not in ALLOWED_COMMANDS:
            return _oops(f"'{executable}' is not in the allowed-commands list ({', '.join(ALLOWED_COMMANDS)})")

    try:
        result = subprocess.run(
            command, shell=True, cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return _oops(f"command timed out after {TIMEOUT}s: {command}")
    except OSError as e:
        return _oops(f"command not found: {e}")

    output = result.stdout.decode("utf-8", errors="replace").strip()
    exit_note = "" if result.returncode == 0 else f"\n[exit {result.returncode}]"
    return f"(no output){exit_note}" if not output else f"{output}{exit_note}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
