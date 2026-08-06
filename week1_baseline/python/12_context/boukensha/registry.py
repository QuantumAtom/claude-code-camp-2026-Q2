from .tool import Tool
from .errors import UnknownToolError
from .telemetry import tracer


class Registry:
    def __init__(self, context):
        self.context = context

    def tool(self, name, description, parameters=None, block=None):
        tool = Tool(str(name), description, parameters or {}, block)
        self.context.register_tool(tool)
        return tool

    def dispatch(self, name, args=None, tool_call_id=None):
        args = args or {}
        with tracer().start_as_current_span("tool.dispatch") as span:
            span.set_attribute("tool.name", str(name))
            span.set_attribute("tool.args", str(args))
            span.set_attribute("gen_ai.operation.name", "execute_tool")
            span.set_attribute("gen_ai.tool.name", str(name))
            span.set_attribute("gen_ai.tool.call.arguments", str(args))
            if tool_call_id:
                span.set_attribute("gen_ai.tool.call.id", str(tool_call_id))

            tool = self.context.tools.get(str(name))
            if tool is None:
                raise UnknownToolError(f"No tool registered as '{name}'")

            result = tool.block(**args)
            span.set_attribute("tool.result", str(result)[:200])
            span.set_attribute("gen_ai.tool.call.result", str(result)[:200])
            return result
            # No explicit except here: start_as_current_span already records
            # the exception and sets error status on this span for anything
            # that escapes the block above (unknown tool or a failing
            # tool.block).
