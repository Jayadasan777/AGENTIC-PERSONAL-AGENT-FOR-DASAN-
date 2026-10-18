"""Model Context Protocol (MCP) Client with strict security allowlisting.

Implements JSON-RPC 2.0 client for discovering and executing external tools
exposed by authenticated MCP servers, enforcing strict URL allowlisting to prevent SSRF.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import create_model

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult

logger = logging.getLogger("aura.mcp")


class MCPToolWrapper(AgentTool):
    """Dynamic wrapper presenting an MCP remote capability as an AURA AgentTool."""

    def __init__(
        self,
        name: str,
        description: str,
        server_url: str,
        risk_tier: RiskTier = RiskTier.MUTATING,
    ) -> None:
        self.name = f"mcp_{name}"
        self.description = f"[Remote MCP] {description}"
        self.server_url = server_url
        self.risk_tier = risk_tier
        # Dynamically create loose schema for unknown external args
        self.args_schema = create_model(f"MCP_{name}_Args", **{"__extra__": (Any, None)})  # type: ignore[call-overload]

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Call remote MCP server via JSON-RPC 2.0 tools/call."""
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": self.name.removeprefix("mcp_"),
                "arguments": kwargs,
            },
            "id": context.request_id,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(self.server_url, json=payload)
                res.raise_for_status()
                data = res.json()
                if "error" in data:
                    return ToolResult(success=False, error=str(data["error"]))
                return ToolResult(success=True, data=data.get("result"))
        except Exception as err:
            logger.exception("MCP tool execution failed: %s", err)
            return ToolResult(success=False, error=f"MCP remote tool failed: {err}")


class MCPClient:
    """Discovers and connects to approved Model Context Protocol servers."""

    def __init__(self, allowlisted_hosts: set[str] | None = None) -> None:
        # Strict SSRF defense: only allow approved hosts (default localhost ports)
        self.allowlisted_hosts = allowlisted_hosts or {"localhost", "127.0.0.1"}

    def is_url_allowed(self, server_url: str) -> bool:
        """Verify URL host is in the strict allowlist to prevent SSRF."""
        try:
            parsed = urlparse(server_url)
            if parsed.scheme not in ("http", "https"):
                return False
            hostname = parsed.hostname
            return hostname in self.allowlisted_hosts
        except Exception:
            return False

    async def discover_tools(self, server_url: str) -> list[AgentTool]:
        """Query remote MCP server for tools/list and return wrapped tools."""
        if not self.is_url_allowed(server_url):
            raise PermissionError(
                f"Server URL '{server_url}' violates strict MCP host allowlist (SSRF blocked)."
            )

        payload = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": "discover-1",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(server_url, json=payload)
                res.raise_for_status()
                data = res.json()
                raw_tools = data.get("result", {}).get("tools", [])

                wrapped: list[AgentTool] = []
                for t in raw_tools:
                    wrapper = MCPToolWrapper(
                        name=t.get("name", "unknown"),
                        description=t.get("description", "No description provided"),
                        server_url=server_url,
                        risk_tier=RiskTier.MUTATING,
                    )
                    wrapped.append(wrapper)
                return wrapped
        except Exception as err:
            logger.warning("Failed to discover MCP tools from %s: %s", server_url, err)
            return []
