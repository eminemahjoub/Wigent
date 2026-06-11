# ════════════════════════════════════════
# wigent — MCP Package
# Role: Model Context Protocol client integration
# Author: wigent team
# ════════════════════════════════════════

"""MCP (Model Context Protocol) integration for Wigent.

Allows the agent to discover and use tools from external MCP servers
via stdio or SSE transport.

Usage
-----
    from wigent.mcp import MCPClient

    client = MCPClient(command=["npx", "-y", "@modelcontextprotocol/server-filesystem"])
    client.connect()
    tools = client.list_tools()
    result = client.call_tool("read_file", {"path": "/tmp/test.txt"})
    client.disconnect()
"""

from __future__ import annotations

from wigent.mcp.client import MCPClient
from wigent.mcp.registry import MCPRegistry
from wigent.mcp.tool_adapter import mcp_to_openai_schema

__all__ = [
    "MCPClient",
    "MCPRegistry",
    "mcp_to_openai_schema",
]
