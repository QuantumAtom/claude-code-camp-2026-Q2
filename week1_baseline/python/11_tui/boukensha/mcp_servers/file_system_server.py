"""MCP server exposing the standard file-system tools, sandboxed to a
single root directory. Run as a stdio subprocess by
boukensha/tools/file_system.py — the root directory is passed via the
BOUKENSHA_MCP_FS_ROOT environment variable rather than a CLI argument or
config file, since that's how the parent process (boukensha/mcp_client.py's
McpClient) launches it.

Tool logic here is identical to the pre-MCP boukensha/tools/file_system.py
implementation — only the transport changed (local Python closures ->
an MCP server the framework talks to over stdio).
"""

import glob as _glob
import os
import re
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
def list_directory(
    path: Annotated[str, Field(description="Relative path to list (default '.')")] = ".",
) -> str:
    """List files and subdirectories at a path relative to the working directory. Defaults to the working directory itself."""
    target = _resolve(path)
    if target.startswith("error:"):
        return target
    if not os.path.isdir(target):
        return _oops(f"'{path}' is not a directory")

    entries = sorted(os.listdir(target))
    entries = [e + "/" if os.path.isdir(os.path.join(target, e)) else e for e in entries]
    return "\n".join(entries) if entries else "(empty)"


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


@mcp.tool()
def search_files(
    pattern: Annotated[str, Field(description="The text or regex pattern to search for")],
    path: Annotated[str, Field(description="Subdirectory or file to search within (default '.' = entire working directory)")] = ".",
    glob: Annotated[str, Field(description="File glob to restrict which files are searched, e.g. '*.py' (default '*')")] = "*",
) -> str:
    """Search for a text pattern (literal string or Python regex) across all files in the working directory tree. Returns matching lines in 'path:line_number:content' format."""
    target = _resolve(path)
    if target.startswith("error:"):
        return target

    search_is_file = os.path.isfile(target)
    file_glob = target if search_is_file else os.path.join(target, "**", glob)

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return _oops(f"invalid pattern: {e}")

    matches = []
    for file in sorted(_glob.glob(file_glob, recursive=True)):
        if not os.path.isfile(file):
            continue
        rel = os.path.relpath(file, ROOT)
        try:
            with open(file, "r", errors="replace") as f:
                for lineno, line in enumerate(f, start=1):
                    if regex.search(line):
                        matches.append(f"{rel}:{lineno}:{line.rstrip(chr(10))}")
        except OSError as e:
            matches.append(f"{rel}: error reading file: {e}")

    return "\n".join(matches) if matches else "no matches"


if __name__ == "__main__":
    mcp.run(transport="stdio")
