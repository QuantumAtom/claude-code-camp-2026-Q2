import json

from .base import Base


# https://docs.z.ai/api-reference/llm/chat-completion
#
# Z.ai (GLM models) speaks the standard OpenAI Chat Completions wire format
# (not the Responses API that boukensha/backends/openai.py targets) --
# messages list with role/content, tools wrapped in {"type": "function",
# "function": {...}}, tool results as {"role": "tool", "tool_call_id": ...},
# and assistant tool calls under message.tool_calls[].function.arguments as
# a JSON string. finish_reason is "tool_calls" or "stop".
class Zai(Base):
    BASE_URL = "https://api.z.ai/api/paas/v4/chat/completions"
    MODELS = {
        "glm-5.2": {
            "context_window": 1_000_000,
            "cost_per_million": {"input": 1.4, "output": 4.4},
            "usage_unit": "tokens",
        },
        "glm-4.6": {
            "context_window": 200_000,
            "cost_per_million": {"input": 0.6, "output": 2.2},
            "usage_unit": "tokens",
        },
        "glm-4.5": {
            "context_window": 128_000,
            "cost_per_million": {"input": 0.6, "output": 2.2},
            "usage_unit": "tokens",
        },
        "glm-4.5-air": {
            "context_window": 128_000,
            "cost_per_million": {"input": 0.2, "output": 1.1},
            "usage_unit": "tokens",
        },
        "glm-4.5-flash": {
            "context_window": 128_000,
            "cost_per_million": {"input": None, "output": None},
            "usage_unit": "tokens",
        },
    }

    def __init__(self, *, api_key, model):
        self.api_key = api_key
        self.configure_model(model)

    def to_messages(self, system, messages):
        system_message = [{"role": "system", "content": system}]
        conversation = []
        for msg in messages:
            if msg.role == "tool_result":
                conversation.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_use_id,
                    "content": str(msg.content),
                })
            elif msg.role == "assistant":
                conversation.append(self._assistant_message(msg.content))
            else:
                conversation.append({"role": str(msg.role), "content": msg.content})
        return system_message + conversation

    def to_tools(self, tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.parameters,
                        "required": list(tool.parameters.keys()),
                    },
                },
            }
            for tool in tools.values()
        ]

    def to_payload(self, context, max_output_tokens=1024, tools=None):
        return {
            "model": self.model,
            "messages": self.to_messages(context.system, context.messages),
            "tools": self.to_tools(context.tools) if tools is None else tools,
            "max_tokens": max_output_tokens,
        }

    def headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def url(self):
        return self.BASE_URL

    def parse_response(self, response):
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = message.get("tool_calls") or []

        content = []
        if message.get("reasoning_content"):
            content.append({"type": "reasoning", "text": message["reasoning_content"]})
        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})
        for tc in tool_calls:
            fn = tc.get("function", {})
            args = fn.get("arguments")
            if isinstance(args, str):
                args = json.loads(args or "{}")
            content.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": fn.get("name"),
                "input": args or {},
            })

        return {"stop_reason": "end_turn" if not tool_calls else "tool_use", "content": content}

    def _assistant_message(self, content):
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        text_blocks = [b for b in blocks if b.get("type") == "text"]
        tool_blocks = [b for b in blocks if b.get("type") == "tool_use"]

        text = "".join(b["text"] for b in text_blocks)
        message: dict = {"role": "assistant", "content": text or None}
        if tool_blocks:
            message["tool_calls"] = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b["input"])},
                }
                for b in tool_blocks
            ]
        return message
