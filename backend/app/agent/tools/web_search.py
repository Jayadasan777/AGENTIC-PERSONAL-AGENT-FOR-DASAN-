"""Live Web Search Tool for AURA Agent Harness.

Enables the agent to search real-time web information (news, travel, flights,
timings, prices, weather, technical docs) using live web queries.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from backend.app.agent.tools.base import AgentTool, RiskTier, ToolContext, ToolResult

logger = logging.getLogger("aura.tools.web_search")


class WebSearchArgs(BaseModel):
    """Input parameters for live web search."""

    query: str = Field(..., description="The search query terms to find real-time information.")
    max_results: int = Field(default=5, description="Maximum number of search results to retrieve (1-10).")


class WebSearchTool(AgentTool):
    """Autonomous tool that searches the live web for real-time information."""

    name = "web_search"
    description = (
        "Search the live web for real-time information: travel tickets, train/flight timings, "
        "current prices, news, documentation, or facts not in memory."
    )
    risk_tier = RiskTier.READ_ONLY
    args_schema = WebSearchArgs

    async def execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "").strip()
        max_results = min(int(kwargs.get("max_results", 5)), 10)

        if not query:
            return ToolResult(success=False, error="Query cannot be empty.")

        logger.info("Executing web search for query=%r user_id=%s", query, context.user_id)

        try:
            url = "https://lite.duckduckgo.com/lite/"
            post_data = urllib.parse.urlencode({"q": query}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=post_data,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            with urllib.request.urlopen(req, timeout=12) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Extract snippets and titles
            snippets = re.findall(r"<td[^>]*class=['\"]result-snippet['\"][^>]*>(.*?)</td>", html, re.DOTALL)
            links = re.findall(r"<a[^>]*class=['\"]result-link['\"][^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", html, re.DOTALL)

            results: list[dict[str, str]] = []
            for i in range(min(len(snippets), max_results)):
                raw_snippet = snippets[i]
                clean_snippet = re.sub(r"<[^>]+>", " ", raw_snippet).strip()
                clean_snippet = re.sub(r"\s+", " ", clean_snippet)

                title = "Result"
                link_url = ""
                if i < len(links):
                    link_url = links[i][0]
                    title = re.sub(r"<[^>]+>", " ", links[i][1]).strip()
                    title = re.sub(r"\s+", " ", title)

                results.append({
                    "title": title,
                    "url": link_url,
                    "snippet": clean_snippet,
                })

            if not results:
                return ToolResult(
                    success=True,
                    data={"query": query, "results": [], "message": f"No web results found for '{query}'."},
                )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "total_found": len(results),
                    "results": results,
                },
            )
        except Exception as err:
            logger.error("Web search failed for query=%r: %s", query, err)
            return ToolResult(
                success=False,
                error=f"Web search connection error: {err}",
            )
