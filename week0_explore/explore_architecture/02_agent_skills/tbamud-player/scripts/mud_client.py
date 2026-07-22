#!/usr/bin/env python3
"""
mud_client.py — manage a persistent telnet session to a tbaMUD/CircleMUD server.

A MUD session is long-lived and stateful: you log in once, then send commands
one at a time and react to what comes back (a monster attacks, a door is
locked, etc). That doesn't fit a single request/response call, so this script
runs the actual telnet connection in a small background daemon process. Each
CLI invocation below is a short-lived client that talks to that daemon:

    mud_client.py start                 # connect + log in, daemon keeps running
    mud_client.py send "look"           # send one command line to the game
    mud_client.py read                  # print any new game output since last read
    mud_client.py status                # is the daemon alive? show last output
    mud_client.py stop                  # disconnect and shut the daemon down

The typical loop is: send a command, then read to see what happened, then
decide the next command based on that — same as a human typing into a MUD
client.

All session state (transcript log, pid file, control socket) lives under
--session-dir (default: a "session" directory next to this script), so
nothing is written to /tmp and the whole session is inspectable as plain files.
"""

import argparse
import hashlib
import os
import re
import socket
import sys
import threading
import time

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 4000
DEFAULT_USERNAME = "dummy"
DEFAULT_PASSWORD = "helloworld"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SESSION_DIR = os.path.join(SCRIPT_DIR, "..", "session")

# --- Telnet protocol bytes (RFC 854) ---
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


class TelnetFilter:
    """Strips telnet IAC negotiation from a byte stream, replying to option
    offers with a blanket refusal (DONT/WONT), and hands back plain text.

    Keeps a leftover buffer across calls because recv() can split an IAC
    sequence across two TCP chunks — a single-shot parser would silently
    corrupt output whenever that happens.
    """

    def __init__(self, sock):
        self.sock = sock
        self._buf = b""

    def feed(self, data: bytes) -> str:
        self._buf += data
        out = bytearray()
        i = 0
        buf = self._buf
        n = len(buf)
        while i < n:
            b = buf[i]
            if b == IAC:
                if i + 1 >= n:
                    break  # incomplete, wait for more data
                cmd = buf[i + 1]
                if cmd in (DO, DONT, WILL, WONT):
                    if i + 2 >= n:
                        break
                    opt = buf[i + 2]
                    if cmd == DO:
                        self.sock.sendall(bytes([IAC, WONT, opt]))
                    elif cmd == WILL:
                        self.sock.sendall(bytes([IAC, DONT, opt]))
                    i += 3
                elif cmd == SB:
                    end = buf.find(bytes([IAC, SE]), i + 2)
                    if end == -1:
                        break  # subnegotiation not fully arrived yet
                    i = end + 2
                elif cmd == IAC:
                    out.append(IAC)  # escaped 0xFF literal
                    i += 2
                else:
                    i += 2  # other 2-byte telnet commands (NOP, GA, ...)
            else:
                out.append(b)
                i += 1
        self._buf = buf[i:]
        return out.decode("utf-8", errors="replace")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _socket_dir():
    # Unix domain socket paths are capped at ~108 bytes on Linux, and this
    # project lives under a long, deeply-nested path — too long to hold a
    # socket file directly. XDG_RUNTIME_DIR (e.g. /run/user/1000) is short,
    # per-user, and the conventional place for this kind of runtime socket;
    # fall back to ~/.cache if it's not set.
    base = os.environ.get("XDG_RUNTIME_DIR") or os.path.expanduser("~/.cache")
    d = os.path.join(base, "tbamud-sessions")
    os.makedirs(d, exist_ok=True)
    return d


def session_paths(session_dir):
    session_dir = os.path.abspath(session_dir)
    session_hash = hashlib.sha1(session_dir.encode()).hexdigest()[:16]
    return {
        "dir": session_dir,
        "pidfile": os.path.join(session_dir, "daemon.pid"),
        "ready": os.path.join(session_dir, "daemon.pid.ready"),
        "control_socket": os.path.join(_socket_dir(), session_hash + ".sock"),
        "transcript": os.path.join(session_dir, "transcript.log"),
        "offset": os.path.join(session_dir, "read.offset"),
        "daemon_log": os.path.join(session_dir, "daemon.log"),
    }


def daemon_running(paths):
    if not os.path.exists(paths["pidfile"]):
        return False
    try:
        with open(paths["pidfile"]) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Daemon: owns the actual MUD socket, logs in, then serves send/read requests.
# ---------------------------------------------------------------------------

def wait_for_marker(get_text, marker, timeout=10.0):
    """Poll get_text() until it returns text containing `marker`."""
    return wait_for_any_marker(get_text, [marker], timeout) is not None


def wait_for_any_marker(get_text, markers, timeout=10.0):
    """Poll get_text() until any of `markers` shows up; return which one (or
    None on timeout). Checked as "has this marker appeared since we started
    waiting" so a marker from an earlier step already in the buffer can't
    cause a false match.
    """
    start_len = len(get_text())
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = get_text()[start_len:]
        for m in markers:
            if m in text:
                return m
        time.sleep(0.1)
    return None


def run_daemon(host, port, username, password, paths):
    os.makedirs(paths["dir"], exist_ok=True)
    with open(paths["pidfile"], "w") as f:
        f.write(str(os.getpid()))

    transcript_lock = threading.Lock()
    transcript_text = [""]  # mutable cell shared with reader thread

    def append_transcript(text):
        with transcript_lock:
            transcript_text[0] += text
            with open(paths["transcript"], "a") as f:
                f.write(text)

    def get_transcript():
        with transcript_lock:
            return transcript_text[0]

    sock = socket.create_connection((host, port), timeout=10)
    telnet = TelnetFilter(sock)
    stop_flag = threading.Event()

    def reader_loop():
        sock.settimeout(0.5)
        while not stop_flag.is_set():
            try:
                data = sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                append_transcript("\n[connection closed by server]\n")
                break
            append_transcript(telnet.feed(data))

    reader = threading.Thread(target=reader_loop, daemon=True)
    reader.start()

    # --- Login automaton ---
    # tbaMUD's flow after name+password branches depending on server state:
    # a brand-new login gets "*** PRESS RETURN:" then a numbered menu (choose
    # "1) Enter the game"); a character still logged in from a previous,
    # not-cleanly-closed session instead gets "Reconnecting." straight into
    # the game. Rather than assume one path and block on markers that may
    # never come, watch for whichever one actually shows up at each step.
    wait_for_marker(get_transcript, "By what name", timeout=10)
    sock.sendall((username + "\r\n").encode())

    wait_for_marker(get_transcript, "Password:", timeout=10)
    sock.sendall((password + "\r\n").encode())

    marker = wait_for_any_marker(
        get_transcript, ["Reconnecting", "PRESS RETURN", "Make your choice"], timeout=10)
    if marker == "PRESS RETURN":
        sock.sendall(b"\r\n")
        marker = wait_for_any_marker(get_transcript, ["Make your choice"], timeout=10)
    if marker == "Make your choice":
        sock.sendall(b"1\r\n")

    # Signal readiness with a sentinel file rather than a fixed sleep, so the
    # `start` CLI command knows exactly when it's safe to hand control back.
    with open(paths["ready"], "w") as f:
        f.write("1")

    # --- Control socket: serves `send`/`stop` requests from the CLI ---
    if os.path.exists(paths["control_socket"]):
        os.remove(paths["control_socket"])
    ctrl = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    ctrl.bind(paths["control_socket"])
    ctrl.listen(5)
    ctrl.settimeout(0.5)

    def cleanup():
        stop_flag.set()
        try:
            sock.close()
        except OSError:
            pass
        try:
            ctrl.close()
        except OSError:
            pass
        for p in (paths["control_socket"], paths["pidfile"], paths["ready"]):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    try:
        while not stop_flag.is_set():
            try:
                conn, _ = ctrl.accept()
            except socket.timeout:
                continue
            with conn:
                data = conn.recv(65536)
                if not data:
                    continue
                line = data.decode("utf-8", errors="replace").rstrip("\n")
                if line.startswith("SEND "):
                    cmd = line[len("SEND "):]
                    try:
                        sock.sendall((cmd + "\r\n").encode())
                        conn.sendall(b"OK\n")
                    except OSError as e:
                        conn.sendall(f"ERROR {e}\n".encode())
                elif line == "QUIT":
                    conn.sendall(b"OK\n")
                    stop_flag.set()
                else:
                    conn.sendall(b"ERROR unknown command\n")
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# CLI client: talks to the daemon over the control socket / reads the log.
# ---------------------------------------------------------------------------

def send_control(paths, line, timeout=5.0):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(paths["control_socket"])
        s.sendall((line + "\n").encode())
        return s.recv(4096).decode("utf-8", errors="replace").strip()


def cmd_start(args):
    paths = session_paths(args.session_dir)
    if daemon_running(paths):
        print(f"Already connected (pid file: {paths['pidfile']}). "
              f"Use 'send'/'read', or 'stop' first to reconnect.")
        return 1

    os.makedirs(paths["dir"], exist_ok=True)
    # Truncate old transcript/offset/ready so a fresh session starts clean.
    for p in (paths["transcript"], paths["offset"], paths["ready"]):
        if os.path.exists(p):
            os.remove(p)

    daemon_log = open(paths["daemon_log"], "w")
    script = os.path.abspath(__file__)
    import subprocess
    proc = subprocess.Popen(
        [sys.executable, script, "_daemon",
         "--host", args.host, "--port", str(args.port),
         "--username", args.username, "--password", args.password,
         "--session-dir", paths["dir"]],
        stdout=daemon_log, stderr=daemon_log,
        start_new_session=True,
    )

    # The daemon writes paths["ready"] once the login automaton has fully
    # resolved (whether via the new-login menu or the reconnect fast-path),
    # so wait on that file rather than guessing from transcript contents.
    # Use proc.poll() (not daemon_running(), which checks for the pidfile)
    # to detect a real crash — the child hasn't written its own pidfile yet
    # in the first instants after Popen returns, and daemon_running() would
    # misreport that brief startup window as "exited unexpectedly".
    deadline = time.time() + 20
    while time.time() < deadline and not os.path.exists(paths["ready"]):
        if proc.poll() is not None:
            print("Daemon exited unexpectedly during login — check:")
            print(f"  {paths['daemon_log']}")
            return 1
        time.sleep(0.2)
    if not os.path.exists(paths["ready"]):
        print("Timed out waiting for login to complete. Current transcript:")

    print(f"Connected to {args.host}:{args.port} as '{args.username}'.")
    print("-" * 60)
    with open(paths["transcript"]) as f:
        text = f.read()
    print(strip_ansi(text))
    with open(paths["offset"], "w") as f:
        f.write(str(len(text.encode("utf-8"))))
    return 0


def cmd_send(args):
    paths = session_paths(args.session_dir)
    if not daemon_running(paths):
        print("Not connected. Run 'mud_client.py start' first.")
        return 1
    reply = send_control(paths, f"SEND {args.command}")
    if reply != "OK":
        print(f"Failed to send command: {reply}")
        return 1
    if args.wait:
        time.sleep(args.wait)
        args.all = False
        return cmd_read(args)
    return 0


def cmd_read(args):
    paths = session_paths(args.session_dir)
    if not os.path.exists(paths["transcript"]):
        print("No transcript yet. Run 'mud_client.py start' first.")
        return 1
    offset = 0
    if os.path.exists(paths["offset"]) and not args.all:
        with open(paths["offset"]) as f:
            offset = int(f.read().strip() or 0)
    with open(paths["transcript"], "rb") as f:
        f.seek(offset if not args.all else 0)
        new_bytes = f.read()
    text = strip_ansi(new_bytes.decode("utf-8", errors="replace"))
    print(text, end="" if text.endswith("\n") else "\n")
    with open(paths["offset"], "w") as f:
        f.write(str(offset + len(new_bytes)))
    return 0


def cmd_status(args):
    paths = session_paths(args.session_dir)
    running = daemon_running(paths)
    print(f"Session dir: {paths['dir']}")
    print(f"Connected:   {running}")
    if running and os.path.exists(paths["transcript"]):
        with open(paths["transcript"]) as f:
            f.seek(max(0, os.path.getsize(paths["transcript"]) - 2000))
            tail = f.read()
        print("-" * 60)
        print("Last output:")
        print(strip_ansi(tail))
    return 0


def cmd_stop(args):
    paths = session_paths(args.session_dir)
    if not daemon_running(paths):
        print("Not connected.")
        return 0
    try:
        send_control(paths, "QUIT")
    except OSError:
        pass
    deadline = time.time() + 5
    while daemon_running(paths) and time.time() < deadline:
        time.sleep(0.2)
    print("Disconnected.")
    return 0


def cmd_daemon(args):
    paths = session_paths(args.session_dir)
    run_daemon(args.host, args.port, args.username, args.password, paths)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)

    # Shared so --session-dir works regardless of whether it's passed before
    # or after the subcommand name (subprocess spawn below passes it after).
    session_parent = argparse.ArgumentParser(add_help=False)
    session_parent.add_argument("--session-dir", default=DEFAULT_SESSION_DIR,
                                 help="Where to store the transcript/pid/socket for this session")

    p_start = sub.add_parser("start", parents=[session_parent],
                              help="Connect and log in (starts the background daemon)")
    p_start.add_argument("--host", default=DEFAULT_HOST)
    p_start.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_start.add_argument("--username", default=DEFAULT_USERNAME)
    p_start.add_argument("--password", default=DEFAULT_PASSWORD)
    p_start.set_defaults(func=cmd_start)

    p_send = sub.add_parser("send", parents=[session_parent], help="Send one command line to the game")
    p_send.add_argument("command", help='e.g. "look", "north", "kill rat"')
    p_send.add_argument("--wait", type=float, default=0.6,
                         help="Seconds to wait before printing the response (0 to skip)")
    p_send.set_defaults(func=cmd_send)

    p_read = sub.add_parser("read", parents=[session_parent], help="Print new game output since the last read")
    p_read.add_argument("--all", action="store_true", help="Print the whole transcript, not just new output")
    p_read.set_defaults(func=cmd_read)

    p_status = sub.add_parser("status", parents=[session_parent], help="Show whether connected + recent output")
    p_status.set_defaults(func=cmd_status)

    p_stop = sub.add_parser("stop", parents=[session_parent], help="Disconnect and stop the daemon")
    p_stop.set_defaults(func=cmd_stop)

    p_daemon = sub.add_parser("_daemon", parents=[session_parent], help=argparse.SUPPRESS)  # internal use only
    p_daemon.add_argument("--host", default=DEFAULT_HOST)
    p_daemon.add_argument("--port", type=int, default=DEFAULT_PORT)
    p_daemon.add_argument("--username", default=DEFAULT_USERNAME)
    p_daemon.add_argument("--password", default=DEFAULT_PASSWORD)
    p_daemon.set_defaults(func=cmd_daemon)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
