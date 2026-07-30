from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    block: Optional[Callable] = None

    def __str__(self):
        return (
            f"#<Tool name={self.name} "
            f"description={str(self.description)[:41]} "
            f"params={list(self.parameters.keys())}>"
        )
