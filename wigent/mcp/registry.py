# ════════════════════════════════════════
# wigent — MCP Registry
# Role: Manage multiple MCP server connections and expose their tools
# Author: wigent team
# ════════════════════════════════════════

"""Registry for MCP servers.

Loads server configs from environment / settings, connects to each,
and exposes a unified tool list.

Usage
-----
    from wigent.mcp import MCPRegistry

    registry = MCPRegistry()
    registry.add_server("filesystem", ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    registry.connect_all()

    schemas = registry.get_tool_schemas()   # OpenAI format
    tools = registry.list_tools()            # All available tool names
    result = registry.call_tool("read_file", {"path": "/tmp/test.txt"})
    registry.disconnect_all()
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from wigent.mcp.client import MCPClient
from wigent.mcp.tool_adapter import mcp_tools_to_openai

logger = logging.getLogger(__name__)


class MCPRegistry:
    """Manages multiple MCP server connections."""

    def __init__(self) -> None:
        self._servers: dict[str, MCPClient] = {}
        self._tool_map: dict[str, MCPClient] = {}  # tool_name -> client
        self._schemas: list[dict[str, Any]] = []

    # ── Server management ─────────────────────────────────────────────

    def add_server(self, name: str, command: list[str], env: dict[str, str] | None = None) -> None:
        """Register a server config (does not connect yet)."""
        self._servers[name] = MCPClient(command=command, env=env)

    def connect_all(self) -> dict[str, bool]:
        """Connect to all registered servers and discover tools."""
        results: dict[str, bool] = {}
        for name, client in self._servers.items():
            ok = client.connect()
            results[name] = ok
            if ok:
                mcp_tools = client.list_tools()
                logger.info("MCP server '%s' exposed %d tools", name, len(mcp_tools))
                for tool_def in mcp_tools:
                    tool_name = tool_def["name"]
                    self._tool_map[tool_name] = client
            else:
                logger.warning("MCP server '%s' failed to connect", name)

        # Build unified schema list
        all_mcp_tools: list[dict[str, Any]] = []
        for client in self._servers.values():
            if client.is_alive():
                all_mcp_tools.extend(client.list_tools())
        self._schemas = mcp_tools_to_openai(all_mcp_tools)
        return results

    def disconnect_all(self) -> None:
        """Shut down all MCP servers."""
        for client in self._servers.values():
            client.disconnect()
        self._tool_map.clear()
        self._schemas.clear()

    # ── Tool access ───────────────────────────────────────────────────

    def list_tools(self) -> list[str]:
        """Return names of all available MCP tools."""
        return list(self._tool_map.keys())

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-format schemas for all MCP tools."""
        return list(self._schemas)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call an MCP tool by name."""
        client = self._tool_map.get(name)
        if client is None:
            return {"error": f"MCP tool '{name}' not found"}
        return client.call_tool(name, arguments)

    def get_tool_callable(self, name: str) -> Callable[..., Any]:
        """Return a Python callable wrapper for an MCP tool."""
        def _wrapper(**kwargs: Any) -> Any:
            return self.call_tool(name, kwargs)
        return _wrapper
