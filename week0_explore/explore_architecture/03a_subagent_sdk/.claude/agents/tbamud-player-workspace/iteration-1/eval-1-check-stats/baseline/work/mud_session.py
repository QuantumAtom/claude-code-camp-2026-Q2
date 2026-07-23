#!/usr/bin/env python3
"""
Minimal telnet-ish client for tbaMUD (CircleMUD derivative) using raw sockets.
Connects to localhost:4000, logs in, runs a few info commands, then quits.
Logs the full raw transcript to a file for later inspection.
"""
import socket
import time
import sys

HOST = "localhost"
PORT = 4000
LOGIN = "dummy"
PASSWORD = "helloworld"

TRANSCRIPT_PATH = sys.argv[1] if len(sys.argv) > 1 else "transcript.log"

def recv_all(sock, wait=1.5, chunk=4096):
    """Read whatever is available, waiting briefly for data to arrive."""
    sock.settimeout(wait)
    data = b""
    try:
        while True:
            part = sock.recv(chunk)
            if not part:
                break
            data += part
    except socket.timeout:
        pass
    return data

def strip_telnet_negotiation(data: bytes) -> bytes:
    """Strip IAC negotiation sequences (very naive) so text is readable."""
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0xFF:  # IAC
            if i + 1 < len(data) and data[i+1] in (0xFB, 0xFC, 0xFD, 0xFE):
                i += 3
                continue
            elif i + 1 < len(data) and data[i+1] == 0xFF:
                out.append(0xFF)
                i += 2
                continue
            else:
                i += 2
                continue
        out.append(b)
        i += 1
    return bytes(out)

def main():
    transcript = open(TRANSCRIPT_PATH, "wb")

    def log(label, data):
        transcript.write(f"\n----- {label} -----\n".encode())
        transcript.write(data)
        transcript.flush()

    s = socket.create_connection((HOST, PORT), timeout=10)

    banner = recv_all(s, wait=2)
    log("BANNER", strip_telnet_negotiation(banner))

    def send(line, wait=1.5, label=None):
        s.sendall((line + "\r\n").encode())
        time.sleep(0.2)
        resp = recv_all(s, wait=wait)
        clean = strip_telnet_negotiation(resp)
        log(label or f"SEND: {line!r}", clean)
        return clean

    # Login sequence: name, then password
    send(LOGIN, wait=2, label="after name")
    send(PASSWORD, wait=2, label="after password")

    # Some MUDs ask to press enter / show MOTD requiring another newline
    send("", wait=2, label="after blank (motd continue)")

    # Check character info
    send("score", wait=2, label="score")
    send("inventory", wait=2, label="inventory")
    send("equipment", wait=2, label="equipment")

    # Quit cleanly
    send("quit", wait=2, label="quit")
    send("y", wait=2, label="confirm quit (if prompted)")

    s.close()
    transcript.close()
    print(f"Transcript written to {TRANSCRIPT_PATH}")

if __name__ == "__main__":
    main()
