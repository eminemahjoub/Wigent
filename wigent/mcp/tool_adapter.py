# ════════════════════════════════════════
# wigent — MCP Tool Adapter
# Role: Convert MCP tool schemas to OpenAI function format
# Author: wigent team
# ════════════════════════════════════════

"""Convert MCP tool definitions to OpenAI-compatible function schemas.

MCP tools have this shape::

    {
        "name": "read_file",
        "description": "Read a file",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }

OpenAI tools have this shape::

    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
"""

from __future__ import annotations

from typing import Any


def mcp_to_openai_schema(mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """Convert a single MCP tool definition to OpenAI function format."""
    schema = mcp_tool.get("inputSchema", {})
    return {
        "type": "function",
        "function": {
            "name": mcp_tool["name"],
            "description": mcp_tool.get("description", ""),
            "parameters": {
                "type": schema.get("type", "object"),
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            },
        },
    }


def mcp_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a list of MCP tool definitions."""
    return [mcp_to_openai_schema(t) for t in tools]
