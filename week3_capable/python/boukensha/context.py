import math
import os

from .message import Message


class Context:
    def __init__(self, *, system, context_window=200_000, working_dir=None,
                 compaction_threshold=0.85):
        self.system = system
        self.context_window = context_window
        self.working_dir = os.path.abspath(working_dir) if working_dir else None
        self.compaction_threshold = compaction_threshold
        self.messages = []
        self.tools = {}
        self.current_tokens = 0
        self.turn_tokens = 0

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    # Update the known context size from the last API response's input_tokens.
    def update_tokens(self, n):
        self.current_tokens = int(n or 0)

    # Reset the cumulative per-turn spend counter. Called at the top of a turn.
    def reset_turn_tokens(self):
        self.turn_tokens = 0

    # Add one API call's input+output tokens to the cumulative per-turn
    # total. This is the spend budget -- distinct from current_tokens
    # (window pressure).
    def add_turn_tokens(self, input_tokens, output_tokens):
        self.turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    # Fraction of the context window currently in use (0.0-1.0).
    @property
    def usage_fraction(self):
        return self.current_tokens / self.context_window if self.context_window > 0 else 0.0

    # Integer percentage (0-100).
    @property
    def usage_pct(self):
        return round(self.usage_fraction * 100)

    # True when we should compact before the next API call. Defaults to
    # the configured compaction_threshold (a fraction of context_window).
    def needs_compaction(self, threshold=None):
        threshold = self.compaction_threshold if threshold is None else threshold
        return self.usage_fraction >= threshold

    # Drop the oldest 40% of messages to free space, keeping at least 2.
    # Resets current_tokens to 0 (will be updated by the next API response).
    # Returns the number of messages dropped.
    def compact_messages(self, target_fraction=0.60):
        drop_count = min(math.ceil(len(self.messages) * 0.40), len(self.messages) - 2)
        drop_count = max(drop_count, 0)
        self.messages = self.messages[drop_count:]
        self.current_tokens = 0
        return drop_count

    # Drop all conversation history, keeping tools and system prompt intact.
    def clear_messages(self):
        self.messages = []
        self.current_tokens = 0

    @property
    def tool_count(self):
        return len(self.tools)

    @property
    def turn_count(self):
        return len(self.messages)

    def __str__(self):
        return (f"#<Context turns={self.turn_count} tools={self.tool_count} "
                f"window={self.context_window} current={self.current_tokens}>")
