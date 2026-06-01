"""Agent state for the LangGraph workflow (Project 2).

Phase 0: the initial ``AgentState`` shape. The nodes that read and write these
fields arrive in Phase 2; this module only defines the contract so the graph
builder and tests have a stable type to import.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State threaded through the plan → retrieve → reflect → answer graph.

    ``total=False`` so nodes may populate fields incrementally across hops.

    Fields:
        query: The original user question.
        sub_queries: Decomposed sub-queries produced by the plan node.
        retrieved: Chunks accumulated across retrieval hops, deduplicated on
            ``chunk_id``.
        draft_answer: Intermediate structured answer, if any.
        final_answer: The structured grounded-answer object returned to the
            caller (answer text, claims with cited chunk_ids, sources,
            answered/insufficient flag).
        hop: Current retrieval hop (0-based).
        max_hops: Hard upper bound on retrieval hops (default 2). The reflect
            node may not loop past this.
        trace_id: Trace identifier propagated to MCP tool calls and used as the
            checkpointer thread key.
    """

    query: str
    sub_queries: list[str]
    retrieved: list[dict[str, Any]]
    draft_answer: dict[str, Any] | None
    final_answer: dict[str, Any] | None
    hop: int
    max_hops: int
    trace_id: str
