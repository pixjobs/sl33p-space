"""
Config-driven MCP toolset loader.

Reads MCP server definitions from config.json and returns McpToolset instances
that ADK auto-discovers and exposes to the Gemini agent.

To add a new MCP server, add an entry to config.json under mcp.servers:

  Stdio (local server):
    {"name": "my_server", "type": "stdio", "command": "python3", "args": ["path/to/server.py"], "enabled": true}

  SSE (remote server):
    {"name": "partner", "type": "sse", "url": "https://partner.example.com/mcp/sse", "enabled": true}
"""

import os
import sys


def load_mcp_tools(config: dict) -> list:
    """Load MCP toolsets from config. Returns list of McpToolset instances."""
    try:
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            SseConnectionParams,
            StdioConnectionParams,
        )
        from mcp import StdioServerParameters
    except ImportError:
        return []

    mcp_config = config.get("mcp", {})
    servers = mcp_config.get("servers", [])
    toolsets = []

    for server in servers:
        if not server.get("enabled", True):
            continue

        name = server.get("name", "unnamed")
        server_type = server.get("type", "stdio")

        try:
            if server_type == "stdio":
                command = server.get("command", "python3")
                args = [os.path.expandvars(a) for a in server.get("args", [])]
                env = server.get("env")
                timeout = server.get("timeout", 30.0)
                toolset = McpToolset(
                    connection_params=StdioConnectionParams(
                        server_params=StdioServerParameters(
                            command=command,
                            args=args,
                            env=env,
                        ),
                        timeout=timeout,
                    )
                )
                toolsets.append(toolset)

            elif server_type == "sse":
                url = server.get("url")
                if not url:
                    continue
                toolset = McpToolset(
                    connection_params=SseConnectionParams(url=url)
                )
                toolsets.append(toolset)

        except Exception as e:
            print(f"Warning: failed to load MCP server '{name}': {e}", file=sys.stderr)

    return toolsets
