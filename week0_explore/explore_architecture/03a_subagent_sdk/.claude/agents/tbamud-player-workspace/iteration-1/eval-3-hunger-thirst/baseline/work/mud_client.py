#!/usr/bin/env python3
"""
Minimal scriptable telnet-ish client for a tbaMUD server.

Usage:
    python3 mud_client.py commands.txt transcript.log

commands.txt format: one entry per line, tab-separated:
    <seconds_to_wait_before_sending>\t<text_to_send>

If text_to_send is literally __QUIT__, the connection is closed after waiting.

The script strips telnet IAC negotiation bytes, logs everything raw (server
output + a marker for what we sent) to transcript.log, and prints the final
buffer to stdout at the end.
"""
import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 4000

IAC = 255


def strip_telnet(data: bytes) -> bytes:
    """Strip minimal telnet negotiation (IAC ...) sequences from a byte buffer."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == IAC:
            if i + 1 < n:
                cmd = data[i + 1]
                if cmd in (251, 252, 253, 254):  # WILL/WONT/DO/DONT + 1 option byte
                    i += 3
                    continue
                elif cmd == 250:  # SB ... SE
                    j = data.find(bytes([IAC, 240]), i + 2)
                    if j == -1:
                        break
                    i = j + 2
                    continue
                else:
                    i += 2
                    continue
            else:
                break
        else:
            out.append(b)
            i += 1
    return bytes(out)


def recv_available(sock, timeout=1.5):
    sock.settimeout(timeout)
    chunks = []
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            chunks.append(data)
    except socket.timeout:
        pass
    return b"".join(chunks)


def main():
    if len(sys.argv) != 3:
        print("usage: mud_client.py commands.txt transcript.log")
        sys.exit(1)

    cmds_path, log_path = sys.argv[1], sys.argv[2]
    with open(cmds_path, "r") as f:
        lines = [l.rstrip("\n") for l in f if l.strip() != ""]

    log = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")

    def logboth(text):
        print(text, end="")
        log.write(text)

    sock = socket.create_connection((HOST, PORT), timeout=10)
    logboth(f"\n=== connecting to {HOST}:{PORT} at {time.ctime()} ===\n")

    # Initial banner
    data = recv_available(sock, timeout=2)
    logboth(strip_telnet(data).decode("utf-8", errors="replace"))

    for line in lines:
        wait_s, sep, text = line.partition("\t")
        wait_s = float(wait_s)
        time.sleep(wait_s)
        if text == "__QUIT__":
            logboth(f"\n>>> [closing socket after {wait_s}s wait]\n")
            break
        logboth(f"\n>>> SEND: {text!r}\n")
        sock.sendall((text + "\r\n").encode("utf-8"))
        data = recv_available(sock, timeout=2)
        logboth(strip_telnet(data).decode("utf-8", errors="replace"))

    sock.close()
    logboth(f"\n=== socket closed at {time.ctime()} ===\n")
    log.close()


if __name__ == "__main__":
    main()
