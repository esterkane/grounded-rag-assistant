"""Agent state for the LangGraph workflow (Project 2).

Phase 2: the state threaded through the plan → retrieve → reflect → answer
graph. ``total=False`` so nodes populate fields incrementally across hops.
"""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State for the plan → retrieve → reflect → answer graph.

    Fields:
        query: The original user question.
        sub_queries: Decomposed sub-queries produced by the plan node.
        pending_queries: Sub-queries not yet retrieved; the retrieve node
            consumes these and clears the list. Plan seeds it from sub_queries;
            reflect appends a single follow-up when it routes back to retrieve.
        retrieved: Chunks accumulated across retrieval hops, deduplicated on
            ``chunk_id``.
        draft_answer: Reserved for an intermediate answer (unused in Phase 2).
        final_answer: The structured GroundedAnswer dict returned to the caller.
        hop: Current retrieval hop (0-based); bounded by ``max_hops``.
        max_hops: Hard upper bound on retrieval hops (default 2).
        next_action: Routing decision set by the reflect node — one of
            "retrieve", "answer", "insufficient".
        trace_id: Trace identifier; also the checkpointer thread key.
    """

    query: str
    sub_queries: list[str]
    pending_queries: list[str]
    retrieved: list[dict[str, Any]]
    draft_answer: dict[str, Any] | None
    final_answer: dict[str, Any] | None
    hop: int
    max_hops: int
    next_action: str
    trace_id: str
