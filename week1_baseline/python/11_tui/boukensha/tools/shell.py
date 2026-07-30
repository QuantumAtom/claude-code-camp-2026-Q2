import sys
from pathlib import Path

from ..mcp_client import register_mcp_tools

_SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp_servers" / "shell_server.py"


# Shell registers command-execution tools against a registry.
#
# Tools registered:
#   run_command  — run an arbitrary shell command inside the working directory
#
# Options:
#   working_dir:      (required) all commands run with this as their cwd
#   timeout:          seconds before a command is killed (default 30)
#   allowed_commands: optional list of allowed executable names (e.g. ["python3", "git"]).
#                     When None (the default) all commands are permitted.
#                     When set, any command whose first token is not in the list
#                     is rejected before execution.
#
# The tool itself runs inside a separate MCP server process
# (mcp_servers/shell_server.py), spawned over stdio and bridged into this
# Registry via mcp_client.register_mcp_tools — same bridge pattern as
# tools/file_system.py.
def register(registry, *, working_dir, timeout=30, allowed_commands=None):
    env = {
        "BOUKENSHA_MCP_SHELL_ROOT": str(working_dir),
        "BOUKENSHA_MCP_SHELL_TIMEOUT": str(timeout),
    }
    if allowed_commands is not None:
        env["BOUKENSHA_MCP_SHELL_ALLOWED"] = ",".join(str(c) for c in allowed_commands)

    return register_mcp_tools(
        registry,
        command=sys.executable,
        args=[str(_SERVER_SCRIPT)],
        env=env,
    )
