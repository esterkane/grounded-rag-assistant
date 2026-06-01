"""Run the agent graph against the live MCP server (Project 2 Phase 2).

Opens a single MCP session (spawning the stdio server once, or connecting to the
streamable-HTTP server), converts the MCP tools to LangChain tools with
langchain-mcp-adapters, builds the graph, and executes it. The session is held
for the whole run so every hop's tool call reuses the same server process.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

from app.agent.graph import DEFAULT_K, DEFAULT_MAX_HOPS, build_agent_graph
from app.agent.mcp_client import SERVER_NAME, build_connections
from app.config import get_settings
from app.generation.providers import build_provider


@asynccontextmanager
async def _prepared(
    query: str,
    *,
    k: int,
    rerank: bool,
    caller_roles: list[str] | None,
    max_hops: int,
    thread_id: str | None,
    checkpointer: Any | None,
) -> AsyncIterator[tuple[Any, dict[str, Any], dict[str, Any]]]:
    settings = get_settings()
    provider = build_provider(settings)
    client = MultiServerMCPClient(build_connections(settings))
    async with client.session(SERVER_NAME) as session:
        tools = await load_mcp_tools(session)
        tools_by_name = {t.name: t for t in tools}
        graph = build_agent_graph(
            tools_by_name,
            provider,
            k=k,
            rerank=rerank,
            caller_roles=caller_roles,
            max_hops=max_hops,
            checkpointer=checkpointer,
        )
        trace_id = thread_id or uuid.uuid4().hex
        initial: dict[str, Any] = {
            "query": query,
            "max_hops": max_hops,
            "hop": 0,
            "retrieved": [],
            "trace_id": trace_id,
        }
        config = {"configurable": {"thread_id": trace_id}}
        yield graph, initial, config


async def run_agent(
    query: str,
    *,
    k: int = DEFAULT_K,
    rerank: bool = False,
    caller_roles: list[str] | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
) -> dict[str, Any]:
    """Run the agent to completion and return the final state (incl. final_answer)."""
    async with _prepared(
        query,
        k=k,
        rerank=rerank,
        caller_roles=caller_roles,
        max_hops=max_hops,
        thread_id=thread_id,
        checkpointer=checkpointer,
    ) as (graph, initial, config):
        return await graph.ainvoke(initial, config)


async def stream_agent(
    query: str,
    *,
    k: int = DEFAULT_K,
    rerank: bool = False,
    caller_roles: list[str] | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    thread_id: str | None = None,
    checkpointer: Any | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield per-node state updates as the graph executes (for CLI/SSE streaming)."""
    async with _prepared(
        query,
        k=k,
        rerank=rerank,
        caller_roles=caller_roles,
        max_hops=max_hops,
        thread_id=thread_id,
        checkpointer=checkpointer,
    ) as (graph, initial, config):
        async for update in graph.astream(initial, config, stream_mode="updates"):
            yield update
