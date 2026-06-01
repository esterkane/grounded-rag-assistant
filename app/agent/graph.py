"""LangGraph workflow builder for grounded-rag-assistant (Project 2).

Phase 0: placeholder builder. It wires an empty ``StateGraph`` over
``AgentState`` so the module imports cleanly and the LangGraph dependency is
exercised, but registers no nodes or edges yet. The plan / retrieve / reflect /
answer nodes — and the MCP-tool binding via langchain-mcp-adapters — arrive in
Phase 2.
"""

from __future__ import annotations

from langgraph.graph import StateGraph

from app.agent.state import AgentState


def build_graph() -> StateGraph:
    """Construct the (currently empty) agent ``StateGraph``.

    Returns the uncompiled builder. Phase 2 adds nodes, edges, and an entry
    point, then compiles it with a checkpointer.
    """
    # Nodes and edges are intentionally absent in Phase 0. A bare StateGraph is
    # enough to confirm the dependency resolves and the state type is valid.
    return StateGraph(AgentState)
