"""Lightweight JSON-line TCP sync: host is authoritative, client sends inputs."""

from __future__ import annotations

import json
import queue
import socket
import threading
from typing import Any, Optional


def lan_ip() -> str:
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


class MatchSocket:
    def __init__(self) -> None:
        self._sock: Optional[socket.socket] = None
        self._peer: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.incoming: queue.Queue[dict[str, Any]] = queue.Queue()
        self.connected = threading.Event()
        self.error: Optional[str] = None
        self.endpoint: Optional[str] = None

    def start_host(self, port: int = 0) -> str:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(1)
        server.settimeout(0.5)
        self._sock = server
        ip = lan_ip()
        bound_port = server.getsockname()[1]
        self.endpoint = f"{ip}:{bound_port}"
        self._thread = threading.Thread(target=self._host_loop, daemon=True)
        self._thread.start()
        return self.endpoint

    def connect_client(self, endpoint: str, timeout: float = 8.0) -> None:
        host, port_s = endpoint.rsplit(":", 1)
        sock = socket.create_connection((host, int(port_s)), timeout=timeout)
        sock.settimeout(0.25)
        self._peer = sock
        self.connected.set()
        self._thread = threading.Thread(target=self._recv_loop, args=(sock,), daemon=True)
        self._thread.start()

    def send(self, payload: dict[str, Any]) -> None:
        peer = self._peer
        if peer is None:
            return
        try:
            data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
            peer.sendall(data)
        except OSError:
            self.error = "peer_disconnected"

    def drain(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        while True:
            try:
                items.append(self.incoming.get_nowait())
            except queue.Empty:
                break
        return items

    def close(self) -> None:
        self._stop.set()
        for sock in (self._peer, self._sock):
            if sock is None:
                continue
            try:
                sock.close()
            except OSError:
                pass
        self._peer = None
        self._sock = None

    def _host_loop(self) -> None:
        server = self._sock
        if server is None:
            return
        while not self._stop.is_set():
            try:
                peer, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            peer.settimeout(0.25)
            self._peer = peer
            self.connected.set()
            self._recv_loop(peer)
            break

    def _recv_loop(self, sock: socket.socket) -> None:
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                self.error = "peer_disconnected"
                break
            if not chunk:
                self.error = "peer_disconnected"
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line:
                    continue
                try:
                    self.incoming.put(json.loads(line.decode("utf-8")))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
