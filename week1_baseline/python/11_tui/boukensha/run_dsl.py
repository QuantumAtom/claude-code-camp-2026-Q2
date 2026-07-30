class RunDSL:
    def __init__(self, registry):
        self.registry = registry

    def tool(self, name, description, parameters=None, block=None):
        return self.registry.tool(name, description, parameters, block)
