"""MCP connection wiring for the agent (Project 2 Phase 2).

The agent drives the project's own ``grounded-rag`` MCP server through
``langchain-mcp-adapters``. By default it spawns the server over stdio (one
subprocess per agent run, reused for every tool call in that run via a
persistent session). When ``MCP_TRANSPORT=http`` is configured, it instead
connects to an already-running streamable-HTTP server.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from app.config import Settings

SERVER_NAME = "grounded-rag"


def build_connections(settings: Settings) -> dict[str, dict[str, Any]]:
    """Build the MultiServerMCPClient connections map for this project's server."""
    if settings.mcp_transport == "http":
        url = f"http://{settings.mcp_http_host}:{settings.mcp_http_port}/mcp"
        return {SERVER_NAME: {"transport": "streamable_http", "url": url}}

    # stdio: spawn `python -m app.mcp.server`. Pass the full environment (so the
    # child sees ELASTICSEARCH_URL, LLM_PROVIDER, etc.) and force stdio on it.
    env = dict(os.environ)
    env["MCP_TRANSPORT"] = "stdio"
    return {
        SERVER_NAME: {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "app.mcp.server"],
            "env": env,
        }
    }


def parse_tool_result(raw: Any) -> dict[str, Any]:
    """Normalize a LangChain MCP tool result into the tool's structured dict.

    langchain-mcp-adapters may hand back the result as a dict, a JSON string, or
    a (content, artifact) tuple depending on version/response format. Parse all
    of them into the dict our tools return; on failure, synthesize a structured
    transient error rather than raising.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (tuple, list)) and raw:
        # (content, artifact) — prefer a dict artifact, else parse the content.
        for part in raw:
            if isinstance(part, dict):
                return part
        raw = raw[0]
    if isinstance(raw, str):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {
        "isError": True,
        "errorCategory": "transient",
        "isRetryable": False,
        "message": "Tool returned an unparseable result.",
        "details": {},
    }
