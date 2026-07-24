import json
import os
import re
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

    def iteration(self, *, n, max):
        self._write({"phase": "iteration", "n": n, "max": max})

    def limit_reached(self, *, kind, n, max):
        self._write({"phase": "limit_reached", "kind": kind, "n": n, "max": max})

    def turn_end(self, *, reason, iterations, tokens=None):
        self._write({"phase": "turn_end", "reason": reason, "iterations": iterations, "tokens": tokens})

    def prompt(self, *, messages, tools):
        self._write({
            "phase": "prompt",
            "message_count": len(messages),
            "messages": [self._serialize_message(m) for m in messages],
            "tool_count": len(tools),
            "tools": list(tools.keys()),
        })

    def tool_call(self, *, name, args):
        self._write({"phase": "tool_call", "name": name, "args": args})

    def tool_result(self, *, name, result, ok=True, error=None):
        self._write({"phase": "tool_result", "name": name, "result": str(result), "ok": ok, "error": error})

    def response(self, *, text, usage=None, stop_reason=None, task=None, backend=None):
        event = {
            "phase": "response",
            "text": str(text).strip(),
            "usage": usage,
            "stop_reason": stop_reason,
        }
        event.update(self._execution_metadata(task=task, backend=backend, usage=usage))
        self._write(event)

    def raw(self, *, data):
        from . import is_debug  # deferred: avoids a circular import with __init__.py

        if not is_debug():
            return

        self._write({"phase": "raw", "data": data})

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

    def _execution_metadata(self, *, task, backend, usage):
        if not (task or backend or usage):
            return {}

        tokens = self._usage_tokens(usage)
        metadata = {
            "task": self._task_name(task),
            "provider": self._provider_name(backend),
            "model": backend.model if backend else None,
            "usage_unit": backend.usage_unit if backend and hasattr(backend, "usage_unit") else None,
            "usage_level": backend.usage_level if backend and hasattr(backend, "usage_level") else None,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": self._estimate_cost(backend, tokens),
        }
        return {k: v for k, v in metadata.items() if v is not None}

    @staticmethod
    def _task_name(task):
        if task is None:
            return None
        if hasattr(task, "task_name"):
            return task.task_name()
        return str(task)

    @staticmethod
    def _provider_name(backend):
        if backend is None:
            return None
        name = type(backend).__name__
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()

    @staticmethod
    def _usage_tokens(usage):
        usage = usage or {}
        return {
            "input": Logger._first_int(usage, "input_tokens", "prompt_tokens", "promptTokenCount", "prompt_eval_count"),
            "output": Logger._first_int(usage, "output_tokens", "completion_tokens", "candidatesTokenCount", "eval_count"),
        }

    @staticmethod
    def _first_int(d, *keys):
        for key in keys:
            value = d.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    def _estimate_cost(backend, tokens):
        if backend is None or not hasattr(backend, "estimate_cost"):
            return None
        if tokens["input"] is None or tokens["output"] is None:
            return None
        return backend.estimate_cost(input_tokens=tokens["input"], output_tokens=tokens["output"])
