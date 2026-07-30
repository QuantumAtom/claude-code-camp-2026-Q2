import sys
from pathlib import Path

from ..mcp_client import register_mcp_tools

_SERVER_SCRIPT = Path(__file__).resolve().parent.parent / "mcp_servers" / "file_system_server.py"


# FileSystem registers the standard set of file-oriented tools against a
# registry, all sandboxed to a single root directory.
#
# Tools registered:
#   pwd              — return the working directory
#   list_directory   — list files and subdirectories at a path
#   read_file        — read the full contents of a file
#   write_file       — write (or overwrite) a file
#   delete_file      — delete a file
#   search_files     — grep for a pattern across files in the working tree
#
# The tools themselves run inside a separate MCP server process
# (mcp_servers/file_system_server.py), spawned over stdio and bridged into
# this Registry via mcp_client.register_mcp_tools — the Registry/Tool/Agent
# call sites here are unchanged from the pre-MCP version; only where the
# tool logic actually executes has moved.
def register(registry, *, working_dir):
    return register_mcp_tools(
        registry,
        command=sys.executable,
        args=[str(_SERVER_SCRIPT)],
        env={"BOUKENSHA_MCP_FS_ROOT": str(working_dir)},
    )
