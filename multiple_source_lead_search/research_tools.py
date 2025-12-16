from __future__ import annotations

import sys
import os
import requests
from typing import Any, Dict, List


from dotenv import load_dotenv
from utils.logger import logging
from utils.exception import CustomException

from agents import function_tool
from agents.mcp import MCPServerStdio
from tavily import TavilyClient



logger = logging.getLogger(__name__)

load_dotenv(override=True)


# ======================================
# MCP SERVER HELPERS (unchanged) -> gives a simple nice list of mcp servers that we can directly pass into the agent
# ======================================

def researcher_mcp_stdio_servers(
    client_session_timeout_seconds: int = 300,
) -> List[MCPServerStdio]:
    servers: List[MCPServerStdio] = []

    servers.append(
        MCPServerStdio(
            name="fetch_mcp",
            params={
                "command": "python",
                "args": ["-m", "mcp_server_fetch"],
            },
            client_session_timeout_seconds=client_session_timeout_seconds,
        )
    )

    servers.append(
        MCPServerStdio(
            name="ddg_mcp",
            params={
                "command": "ddg-search-mcp",
                "args": [],
            },
            client_session_timeout_seconds=client_session_timeout_seconds,
        )
    )

    return servers



# ======================================================================
# TAVILY SEARCH TOOL
# ======================================================================

TAVILY_MAX_RESULTS = 25

@function_tool
def tavily_search(
    query: str,
    max_results: int,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict:
    """
    Search using Tavily API - fallback when MCP DDG fails.
    
    Args:
        query: Natural language search query (e.g. "Singapore construction companies LinkedIn")
        max_results: Number of results to return (default 5)
        include_domains: Optional list of domains to search within (e.g. ['linkedin.com'])
        exclude_domains: Optional list of domains to exclude
    
    Returns:
        dict with search results including titles, URLs, and content snippets
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        raise ImportError("tavily-python not installed. Run: pip install tavily-python")
    
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return {"error": "TAVILY_API_KEY not set in environment"}
    
    try:
        client = TavilyClient(api_key=api_key)
        
        response = client.search(
            query=query,
            max_results=TAVILY_MAX_RESULTS,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            search_depth="advanced",  # More thorough search
            include_answer=False,      # DONT Get AI-generated summary
        )
        
        return response
        
    except Exception as e:
        return {"error": f"Tavily search failed: {str(e)}"}
