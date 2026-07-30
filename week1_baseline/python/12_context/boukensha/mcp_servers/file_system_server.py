"""MCP server exposing the standard file-system tools, sandboxed to a
single root directory. Run as a stdio subprocess by
boukensha/tools/file_system.py — the root directory is passed via the
BOUKENSHA_MCP_FS_ROOT environment variable rather than a CLI argument or
config file, since that's how the parent process (boukensha/mcp_client.py's
McpClient) launches it.

Tools exposed: pwd, read_file, write_file, delete_file. list_directory
and search_files (directory discovery) were dropped -- leftover from
when this app was a coding harness; the player agent operates on paths
it's already told about and has no use for them yet.
"""

import os
from typing import Annotated

from pydantic import Field

from mcp.server.fastmcp import FastMCP

ROOT = os.path.abspath(os.environ["BOUKENSHA_MCP_FS_ROOT"])

mcp = FastMCP("boukensha-file-system")


def _resolve(path):
    path = str(path)
    joined = path if os.path.isabs(path) else os.path.join(ROOT, path)
    absolute = os.path.normpath(joined)
    if absolute == ROOT or absolute.startswith(ROOT + os.sep):
        return absolute
    return f"error: path '{path}' escapes the working directory"


def _oops(msg):
    return f"error: {msg}"


@mcp.tool()
def pwd() -> str:
    """Return the working directory — the root that all file paths are relative to."""
    return ROOT


@mcp.tool()
def read_file(
    path: Annotated[str, Field(description="Relative path to the file")],
) -> str:
    """Read and return the full contents of a file. Path is relative to the working directory."""
    target = _resolve(path)
    if target.startswith("error:"):
        return target
    if not os.path.isfile(target):
        return _oops(f"'{path}' is not a file")
    try:
        with open(target, "r") as f:
            return f.read()
    except OSError as e:
        return _oops(str(e))


@mcp.tool()
def write_file(
    path: Annotated[str, Field(description="Relative path to the file")],
    content: Annotated[str, Field(description="Text content to write")],
) -> str:
    """Write content to a file, creating it (and any missing parent directories) if needed, overwriting if it exists. Path is relative to the working directory."""
    target = _resolve(path)
    if target.startswith("error:"):
        return target
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w") as f:
            f.write(content)
        rel = os.path.relpath(target, ROOT)
        return f"ok: wrote {len(content.encode('utf-8'))} bytes to {rel}"
    except OSError as e:
        return _oops(str(e))


@mcp.tool()
def delete_file(
    path: Annotated[str, Field(description="Relative path to the file to delete")],
) -> str:
    """Delete a file. Directories are not deleted. Path is relative to the working directory."""
    target = _resolve(path)
    if target.startswith("error:"):
        return target
    if not os.path.isfile(target):
        return _oops(f"'{path}' is not a file")
    try:
        os.remove(target)
        return f"ok: deleted {path}"
    except OSError as e:
        return _oops(str(e))


if __name__ == "__main__":
    mcp.run(transport="stdio")
