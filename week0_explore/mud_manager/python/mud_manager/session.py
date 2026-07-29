import re
import socket
import sys
import threading
import time


class Session:
    """Long-lived telnet connection to a CircleMUD server.

    A background thread continuously drains the socket into an internal
    buffer, stripping telnet IAC negotiation bytes. The agent loop sends a
    command and then calls `read_until_prompt` (or `read_until` for a known
    prompt) to collect both the command's response and any async chatter
    that arrived in the meantime.
    """

    DEFAULT_HOST = "localhost"
    DEFAULT_PORT = 4000
    DEFAULT_TIMEOUT = 10.0

    # Telnet protocol bytes we recognise. We don't negotiate — we just
    # consume and discard IAC sequences so they don't pollute the buffer.
    IAC, DONT, DO, WONT, WILL, SB, SE = 0xFF, 0xFE, 0xFD, 0xFC, 0xFB, 0xFA, 0xF0

    class Error(Exception):
        pass

    class ConnectionError(Error):
        pass

    class LoginError(Error):
        pass

    class Timeout(Error):
        pass

    # CircleMUD terminates every command response with a prompt that ends in
    # "> " (greater-than space). Waiting for that sentinel is faster and more
    # deterministic than relying on a silence window.
    PROMPT_SENTINEL = "> "

    # Sentinels for send_command meaning "just press return" — Python has no
    # equivalent of Ruby's :return/:enter symbols, so a unique sentinel
    # object is the direct, unambiguous stand-in (a raw string like "return"
    # would collide with someone actually wanting to send that word).
    RETURN = object()
    ENTER = object()

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=DEFAULT_TIMEOUT):
        self.host = host
        self.port = port
        self._timeout = timeout
        self._socket = None
        self._reader = None
        self._buffer = ""
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._closed = False
        self._last_recv_at = None

    def open(self):
        if self._socket is not None:
            raise Session.Error("already open")
        try:
            self._socket = socket.create_connection((self.host, self.port))
        except OSError as e:
            raise Session.ConnectionError(f"connect {self.host}:{self.port} failed: {e}") from e
        self._closed = False
        self._start_reader()
        return self

    def is_open(self):
        return self._socket is not None and not self._closed

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._socket is not None:
                self._socket.close()
        except OSError:
            pass  # already closed / broken — fine
        if self._reader is not None:
            self._reader.join(1)
        self._socket = None
        self._reader = None

    def send_command(self, command):
        """Send a command. Accepts a str, a primitives.Command (anything
        with a .raw attribute), or Session.RETURN/Session.ENTER for a bare
        keypress. A trailing newline is appended."""
        if not self.is_open():
            raise Session.Error("session not open")
        if command is Session.RETURN or command is Session.ENTER:
            line = ""
        elif hasattr(command, "raw"):
            line = command.raw
        else:
            line = str(command)
        self._socket.sendall((line + "\r\n").encode("utf-8"))
        return line

    send = send_command

    def drain(self):
        """Drain whatever is currently buffered and return it. Non-blocking."""
        with self._lock:
            out, self._buffer = self._buffer, ""
            return out

    def read_until_quiet(self, quiet_seconds=1.0, timeout=None):
        """Block until `quiet_seconds` have elapsed with no new bytes
        arriving, or `timeout` total seconds pass. Returns whatever
        accumulated."""
        if not self.is_open():
            raise Session.Error("session not open")
        deadline = time.monotonic() + (timeout or self._timeout)
        with self._lock:
            while True:
                remaining_total = deadline - time.monotonic()
                if remaining_total <= 0:
                    break

                if (self._last_recv_at is not None
                        and (time.monotonic() - self._last_recv_at) >= quiet_seconds
                        and self._buffer):
                    break

                if self._last_recv_at is not None and self._buffer:
                    wait_for = quiet_seconds - (time.monotonic() - self._last_recv_at)
                else:
                    wait_for = remaining_total
                wait_for = min(wait_for, remaining_total)
                if wait_for <= 0:
                    break
                self._cv.wait(wait_for)
            out, self._buffer = self._buffer, ""
            return out

    def read_until(self, pattern, timeout=None):
        """Block until the buffer contains the given pattern (str or
        compiled regex), then return everything up to and including the
        match. Raises Session.Timeout if `timeout` seconds pass without a
        match."""
        if not self.is_open():
            raise Session.Error("session not open")
        regex = pattern if isinstance(pattern, re.Pattern) else re.compile(re.escape(pattern))
        deadline = time.monotonic() + (timeout or self._timeout)
        with self._lock:
            while True:
                m = regex.search(self._buffer)
                if m:
                    cut = m.end()
                    out, self._buffer = self._buffer[:cut], self._buffer[cut:]
                    return out
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Session.Timeout(f"read_until {pattern!r} after {timeout}s")
                if self._closed:
                    raise Session.ConnectionError("socket closed while waiting")
                self._cv.wait(remaining)

    def read_until_prompt(self, timeout=None):
        """Falls back to draining the buffer if the prompt is never seen
        within the timeout (e.g. during combat when extra async lines may
        slip in)."""
        try:
            return self.read_until(Session.PROMPT_SENTINEL, timeout=timeout)
        except Session.Timeout:
            print("[mud_manager.Session] prompt not detected within timeout; "
                  "returning buffered content", file=sys.stderr)
            return self.drain()

    def login(self, username, password):
        """Walk the CircleMUD login dance."""
        self.read_until(re.compile(r"By what name do you wish to be known.*\?", re.IGNORECASE))

        self.send_command(username)
        self.read_until(re.compile(r"Password", re.IGNORECASE))

        self.send_command(password)
        output = self.read_until(re.compile(r"Welcome|Reconnecting|Wrong password", re.IGNORECASE))

        if re.search(r"Reconnecting", output, re.IGNORECASE):
            return None  # already in-world, skip menu
        elif re.search(r"Welcome", output, re.IGNORECASE):
            self.send_command(Session.RETURN)  # enter for main menu
            self.send_command(1)               # enter the game
            return self.read_until_quiet()
        elif re.search(r"Wrong password", output, re.IGNORECASE):
            raise Session.LoginError("wrong password")

    # ----- internals -----

    def _start_reader(self):
        def run():
            try:
                while True:
                    chunk = self._socket.recv(4096)
                    if not chunk:
                        break
                    text = self._strip_iac(chunk)
                    if text:
                        with self._lock:
                            self._buffer += text
                            self._last_recv_at = time.monotonic()
                            self._cv.notify_all()
            except OSError:
                pass  # remote closed — fall through
            except Exception as e:
                print(f"[mud_manager.Session] reader error: {type(e).__name__}: {e}", file=sys.stderr)
            finally:
                with self._lock:
                    self._closed = True
                    self._cv.notify_all()

        self._reader = threading.Thread(target=run, daemon=True)
        self._reader.start()

    def _strip_iac(self, data):
        """Telnet protocol IAC stripper. Discards WILL/WONT/DO/DONT
        negotiation and SB...SE subnegotiation blocks; keeps a literal 0xFF
        byte via the IAC-IAC escape."""
        out = bytearray()
        i, n = 0, len(data)
        while i < n:
            b = data[i]
            if b == Session.IAC:
                nxt = data[i + 1] if i + 1 < n else None
                if nxt is None:
                    break
                if nxt == Session.IAC:
                    out.append(0xFF)
                    i += 2
                elif nxt in (Session.WILL, Session.WONT, Session.DO, Session.DONT):
                    i += 3
                elif nxt == Session.SB:
                    j = i + 2
                    while j < n and not (data[j] == Session.IAC and j + 1 < n and data[j + 1] == Session.SE):
                        j += 1
                    i = j + 2
                else:
                    i += 2
            else:
                out.append(b)
                i += 1
        return bytes(out).decode("utf-8", errors="replace")
