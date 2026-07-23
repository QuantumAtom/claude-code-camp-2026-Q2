#!/usr/bin/env python3
"""
Minimal interactive-ish telnet client for a tbaMUD server.

Connects over a raw TCP socket (not telnetlib, to avoid deprecation /
protocol-negotiation headaches), strips IAC telnet negotiation bytes,
logs everything to a transcript file, and lets us send a scripted
sequence of commands while waiting for the server to go "quiet"
between each one (MUD output doesn't have a fixed prompt terminator,
so we use an idle-timeout heuristic).
"""
import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 4000
LOGFILE = sys.argv[1] if len(sys.argv) > 1 else "transcript.log"

IAC = 255  # 0xFF telnet "interpret as command"


def strip_telnet(data: bytes) -> bytes:
    """Strip IAC negotiation sequences from a byte buffer, return clean text bytes."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == IAC:
            if i + 1 >= n:
                break
            cmd = data[i + 1]
            if cmd in (251, 252, 253, 254):  # WILL WONT DO DONT
                i += 3
                continue
            elif cmd == 250:  # SB ... SE
                j = data.find(bytes([IAC, 240]), i + 2)
                if j == -1:
                    break
                i = j + 2
                continue
            elif cmd == IAC:
                out.append(IAC)
                i += 2
                continue
            else:
                i += 2
                continue
        else:
            out.append(b)
            i += 1
    return bytes(out)


class MudSession:
    def __init__(self, host, port, logfile):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(0.5)
        self.log = open(logfile, "ab")

    def read_quiet(self, idle=1.2, max_wait=15.0):
        """Read until no new data arrives for `idle` seconds, or max_wait total."""
        buf = bytearray()
        start = time.time()
        last_data = time.time()
        while True:
            try:
                chunk = self.sock.recv(4096)
                if chunk:
                    buf.extend(chunk)
                    last_data = time.time()
                else:
                    break  # connection closed
            except socket.timeout:
                pass
            now = time.time()
            if now - last_data >= idle:
                break
            if now - start >= max_wait:
                break
        clean = strip_telnet(bytes(buf))
        self.log.write(clean)
        self.log.flush()
        text = clean.decode("latin-1", errors="replace")
        print(text, end="")
        return text

    def send(self, line):
        self.log.write(("\n>>> SEND: " + line + "\n").encode())
        self.sock.sendall((line + "\r\n").encode("latin-1"))

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
        self.log.close()


def main():
    s = MudSession(HOST, PORT, LOGFILE)
    try:
        s.read_quiet(idle=1.5, max_wait=8)
        s.send("dummy")
        s.read_quiet(idle=1.5, max_wait=8)
        s.send("helloworld")
        text = s.read_quiet(idle=1.5, max_wait=8)

        # Some MUDs show a MOTD/"press enter" prompt after login.
        if "return" in text.lower() or "continue" in text.lower() or "press" in text.lower():
            s.send("")
            s.read_quiet(idle=1.5, max_wait=8)

        commands = sys.argv[2:] if len(sys.argv) > 2 else []
        for cmd in commands:
            if cmd.startswith("WAIT:"):
                secs = float(cmd.split(":", 1)[1])
                s.read_quiet(idle=2.5, max_wait=secs)
                continue
            s.send(cmd)
            s.read_quiet(idle=1.5, max_wait=10)
    finally:
        s.close()


if __name__ == "__main__":
    main()
