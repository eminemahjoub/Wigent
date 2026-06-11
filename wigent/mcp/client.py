# ════════════════════════════════════════
# wigent — MCP Client
# Role: JSON-RPC 2.0 client over stdio for MCP servers
# Author: wigent team
# ════════════════════════════════════════

"""MCP stdio client.

Spawns an MCP server as a subprocess and communicates via JSON-RPC
over stdin/stdout.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for a single MCP server over stdio."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._pending: dict[str, Any] = {}
        self._reader_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def connect(self) -> bool:
        """Start the MCP server subprocess and send initialize."""
        try:
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**self._get_env(), **(self.env or {})},
            )
        except Exception as exc:
            logger.error("Failed to start MCP server %s: %s", self.command, exc)
            return False

        self._stop.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()

        # Send initialize
        init_id = str(uuid.uuid4())
        self._send({
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "wigent", "version": "1.1.0"},
            },
        })

        # Wait for response with timeout
        for _ in range(50):  # 5s
            with self._lock:
                if init_id in self._pending and "result" in self._pending[init_id]:
                    return True
            time.sleep(0.1)

        logger.warning("MCP initialize timeout for %s", self.command)
        return False

    def disconnect(self) -> None:
        """Shutdown the MCP server."""
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self._proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "shutdown"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=2)
            except Exception:
                self._proc.kill()
        self._proc = None

    def list_tools(self) -> list[dict[str, Any]]:
        """Discover tools exposed by this MCP server."""
        req_id = str(uuid.uuid4())
        self._send({"jsonrpc": "2.0", "id": req_id, "method": "tools/list"})

        for _ in range(50):
            with self._lock:
                resp = self._pending.pop(req_id, None)
                if resp and "result" in resp:
                    return resp["result"].get("tools", [])
                if resp and "error" in resp:
                    logger.warning("MCP tools/list error: %s", resp["error"])
                    return []
            time.sleep(0.1)

        logger.warning("MCP tools/list timeout")
        return []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool by name with JSON arguments."""
        req_id = str(uuid.uuid4())
        self._send({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })

        for _ in range(300):  # 30s
            with self._lock:
                resp = self._pending.pop(req_id, None)
                if resp and "result" in resp:
                    return resp["result"]
                if resp and "error" in resp:
                    return {"error": resp["error"]}
            time.sleep(0.1)

        return {"error": "MCP tool call timeout"}

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ── Internals ──────────────────────────────────────────────────────

    def _get_env(self) -> dict[str, str]:
        import os
        return dict(os.environ)

    def _send(self, msg: dict[str, Any]) -> None:
        if self._proc and self._proc.stdin:
            line = json.dumps(msg) + "\n"
            self._proc.stdin.write(line)
            self._proc.stdin.flush()

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._proc and self._proc.stdout:
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    msg = json.loads(line)
                    msg_id = msg.get("id")
                    if msg_id is not None:
                        with self._lock:
                            self._pending[str(msg_id)] = msg
            except json.JSONDecodeError:
                continue
            except Exception:
                break
