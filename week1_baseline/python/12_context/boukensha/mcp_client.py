import asyncio
import atexit
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpClient:
    """Synchronous bridge to an MCP server run as a stdio subprocess.

    The official MCP SDK is asyncio-based; boukensha's Registry/Agent loop
    is synchronous throughout. This runs the whole connect-serve-close
    lifetime as a single coroutine on a dedicated background thread's event
    loop (anyio's cancel scopes require __aenter__/__aexit__ to happen in
    the same asyncio Task, so the connection can't be opened and closed via
    two separate scheduled coroutines) and exposes plain blocking methods
    that hand work to that loop and wait for the result — the same
    "own the concurrency internally, expose a synchronous interface" shape
    as mud_manager.Session's background reader thread, just built on
    asyncio instead of raw sockets.
    """

    def __init__(self, *, command, args=None, env=None):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        self._session = None
        self._stop_event = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._connect_error = None

        params = StdioServerParameters(command=command, args=args or [], env=env)
        asyncio.run_coroutine_threadsafe(self._session_main(params), self._loop)
        if not self._ready.wait(timeout=15):
            raise TimeoutError(f"MCP server did not become ready in time: {command} {args}")
        if self._connect_error is not None:
            raise self._connect_error

        atexit.register(self.close)

    async def _session_main(self, params):
        self._stop_event = asyncio.Event()
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as e:
            self._connect_error = e
            self._ready.set()
        finally:
            self._closed.set()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def list_tools(self):
        return self._run(self._session.list_tools()).tools

    def call_tool(self, name, arguments):
        result = self._run(self._session.call_tool(name, arguments))
        parts = [block.text for block in result.content if getattr(block, "text", None) is not None]
        text = "\n".join(parts)
        if result.isError:
            return f"error: {text}" if text else "error: tool call failed"
        return text

    def close(self):
        if self._closed.is_set():
            return
        if self._stop_event is not None:
            self._loop.call_soon_threadsafe(self._stop_event.set)
            self._closed.wait(timeout=5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2)


def register_mcp_tools(registry, *, command, args=None, env=None):
    """Spawn an MCP server, discover its tools, and register each one into
    a boukensha Registry — a bridge, not a replacement, for the existing
    Tool/Registry/Agent/backends architecture.

    Each MCP tool's `inputSchema` (a full JSON Schema object) is unpacked
    back into boukensha's flat `{name: {"type":..., "description":...}}`
    parameters shape, since that's what backends/*.py already expects
    (they build "properties"/"required" from it themselves) — this is the
    layer that lets the rest of the framework stay exactly as it was.
    """
    client = McpClient(command=command, args=args, env=env)

    def make_block(tool_name):
        return lambda **kwargs: client.call_tool(tool_name, kwargs)

    for tool in client.list_tools():
        parameters = (tool.inputSchema or {}).get("properties", {})
        registry.tool(tool.name, tool.description or "", parameters, make_block(tool.name))

    return client
