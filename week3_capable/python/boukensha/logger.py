import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    DEFAULT_SESSION_DIR = "sessions"

    def __init__(self, *, session_id=None, dir=None, log=None, snapshot=None):
        self.session_id = session_id or self._generate_session_id()
        self.path = Path(log) if log else Path(dir or self._default_dir()) / f"{self.session_id}.jsonl"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a")
        event = {"phase": "session_start"}
        if snapshot:
            event.update(snapshot)
        self._write(event)

    def turn(self, *, n):
        self._write({"phase": "turn", "n": n})

    def iteration(self, *, n, max):
        self._write({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, *, kind, n, max):
        self._write({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def turn_end(self, *, reason, iterations, tokens=None):
        self._write({"phase": "turn_end", "reason": reason, "iterations": iterations, "tokens": tokens})

    def prompt(self, *, messages, tools, context_window):
        self._write({
            "phase": "prompt",
            "message_count": len(messages),
            "messages": [self._serialize_message(m) for m in messages],
            "tool_count": len(tools),
            "tools": list(tools.keys()),
            "context_window": context_window,
        })

    def compaction(self, *, before, dropped, context_window):
        self._write({"phase": "compaction", "before": before, "dropped": dropped, "context_window": context_window})

    def tool_call(self, *, name, args):
        self._write({"phase": "tool_call", "name": name, "args": args})

    def tool_result(self, *, name, result, ok=True, error=None):
        self._write({"phase": "tool_result", "name": name, "result": str(result), "ok": ok, "error": error})

    def response(self, *, text, usage=None, stop_reason=None):
        self._write({"phase": "response", "text": str(text).strip(), "usage": usage, "stop_reason": stop_reason})

    def reasoning(self, *, text, redacted=False):
        self._write({"phase": "reasoning", "text": str(text), "redacted": redacted})

    def plan(self, *, text):
        self._write({"phase": "plan", "text": str(text).strip()})

    def raw(self, *, data):
        from . import is_debug  # deferred: avoids a circular import with __init__.py

        if not is_debug():
            return

        self._write({"phase": "raw", "data": data})

    def subscribe(self, callback):
        if not hasattr(self, "_subscribers"):
            self._subscribers = []
        self._subscribers.append(callback)

    def close(self):
        if self._file:
            self._file.close()

    # ---------- internals ----------------------------------------------

    def _default_dir(self):
        from . import config  # deferred: avoids a circular import with __init__.py

        return os.path.join(config().dir, self.DEFAULT_SESSION_DIR)

    def _write(self, event):
        record = {**event, "session_id": self.session_id, "at": self._now_iso()}
        self._file.write(json.dumps(record) + "\n")
        self._file.flush()
        for subscriber in getattr(self, "_subscribers", []):
            subscriber(event)

    @staticmethod
    def _now_iso():
        return datetime.now().astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _generate_session_id():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{stamp}-{secrets.token_hex(4)}"

    @staticmethod
    def _serialize_message(msg):
        return {"role": msg.role, "content": msg.content}
