from .tool import Tool
from .errors import UnknownToolError


class Registry:
    def __init__(self, context):
        self.context = context

    def tool(self, name, description, parameters=None, block=None):
        tool = Tool(str(name), description, parameters or {}, block)
        self.context.register_tool(tool)
        return tool

    def dispatch(self, name, args=None):
        args = args or {}
        tool = self.context.tools.get(str(name))
        if tool is None:
            raise UnknownToolError(f"No tool registered as '{name}'")
        return tool.block(**args)
