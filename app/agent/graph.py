"""LangGraph workflow for the agent (Project 2 Phase 2).

Builds the plan → retrieve → reflect → answer graph over the project's MCP
tools (converted to LangChain tools by ``langchain-mcp-adapters`` in
``app.agent.runner``). The reflect node bounds the loop by ``max_hops`` and
routes to a dedicated insufficient-evidence terminal when the corpus cannot
support an answer — the grounded answerer is the final guarantee against
hallucination.

The graph is built per run with the loaded tools and an LLM provider bound into
the nodes, so the module stays importable and testable without HTTP.
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace

from app.agent.mcp_client import parse_tool_result
from app.agent.reasoning import ANSWER, INSUFFICIENT, RETRIEVE, plan_subqueries, reflect
from app.agent.state import AgentState
from app.generation.answerer import INSUFFICIENT_MESSAGE
from app.generation.providers import LLMProvider

tracer = trace.get_tracer(__name__)

DEFAULT_MAX_HOPS = 2
DEFAULT_K = 8


def _insufficient_answer(query: str) -> dict[str, Any]:
    """The structured insufficient-evidence response (matches GroundedAnswer)."""
    return {
        "query": query,
        "answered": False,
        "insufficient": True,
        "answer": INSUFFICIENT_MESSAGE,
        "claims": [],
        "sources": [],
        "dropped_citations": [],
        "model": "",
        "usage": None,
    }


def _merge_chunks(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Accumulate chunks across hops, deduplicating on chunk_id, preserving order."""
    seen = {c.get("chunk_id") for c in existing}
    merged = list(existing)
    for chunk in new:
        cid = chunk.get("chunk_id")
        if cid and cid not in seen:
            seen.add(cid)
            merged.append(chunk)
    return merged


def build_agent_graph(
    tools_by_name: dict[str, Any],
    provider: LLMProvider,
    *,
    k: int = DEFAULT_K,
    rerank: bool = False,
    caller_roles: list[str] | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    checkpointer: Any | None = None,
):
    """Build and compile the agent graph.

    ``tools_by_name`` maps "retrieve_chunks" / "answer_with_citations" to the
    LangChain tools produced by langchain-mcp-adapters. ``provider`` powers the
    plan and reflect reasoning (reuse ``build_provider`` for Gemini→Ollama
    fallback). The returned object is a compiled graph; invoke it with
    ``config={"configurable": {"thread_id": trace_id}}``.
    """
    roles = caller_roles or ["public"]

    def plan_node(state: AgentState) -> dict[str, Any]:
        with tracer.start_as_current_span("agent.plan") as span:
            subs = plan_subqueries(provider, state["query"])
            span.set_attribute("agent.sub_query_count", len(subs))
            return {
                "sub_queries": subs,
                "pending_queries": list(subs),
                "hop": 0,
                "retrieved": list(state.get("retrieved", [])),
            }

    async def retrieve_node(state: AgentState) -> dict[str, Any]:
        with tracer.start_as_current_span("agent.retrieve") as span:
            pending = state.get("pending_queries") or [state["query"]]
            accumulated = list(state.get("retrieved", []))
            for sub_query in pending:
                raw = await tools_by_name["retrieve_chunks"].ainvoke(
                    {
                        "query": sub_query,
                        "k": k,
                        "mode": "hybrid",
                        "rerank": rerank,
                        "caller_roles": roles,
                    }
                )
                result = parse_tool_result(raw)
                if not result.get("isError"):
                    accumulated = _merge_chunks(accumulated, result.get("chunks", []))
            span.set_attribute("agent.hop", state.get("hop", 0))
            span.set_attribute("agent.retrieved_total", len(accumulated))
            return {"retrieved": accumulated, "pending_queries": []}

    def reflect_node(state: AgentState) -> dict[str, Any]:
        with tracer.start_as_current_span("agent.reflect") as span:
            hop = state.get("hop", 0)
            decision = reflect(
                provider,
                state["query"],
                state.get("retrieved", []),
                hop,
                state.get("max_hops", max_hops),
            )
            span.set_attribute("agent.reflect_action", decision.action)
            span.set_attribute("agent.hop", hop)
            if decision.action == RETRIEVE:
                follow_up = decision.follow_up or state["query"]
                return {
                    "next_action": RETRIEVE,
                    "pending_queries": [follow_up],
                    "hop": hop + 1,
                    "sub_queries": [*state.get("sub_queries", []), follow_up],
                }
            return {"next_action": decision.action}

    async def answer_node(state: AgentState) -> dict[str, Any]:
        with tracer.start_as_current_span("agent.answer") as span:
            raw = await tools_by_name["answer_with_citations"].ainvoke(
                {
                    "query": state["query"],
                    "k": k,
                    "rerank": rerank,
                    "caller_roles": roles,
                }
            )
            result = parse_tool_result(raw)
            if result.get("isError"):
                # A tool failure must not produce a hallucinated answer.
                span.set_attribute("agent.answer_error", True)
                return {"final_answer": _insufficient_answer(state["query"])}
            span.set_attribute("agent.answered", bool(result.get("answered")))
            return {"final_answer": result}

    def insufficient_node(state: AgentState) -> dict[str, Any]:
        with tracer.start_as_current_span("agent.insufficient"):
            return {"final_answer": _insufficient_answer(state["query"])}

    def route_after_reflect(state: AgentState) -> str:
        return state.get("next_action", ANSWER)

    builder = StateGraph(AgentState)
    builder.add_node("plan", plan_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("reflect", reflect_node)
    builder.add_node("answer", answer_node)
    builder.add_node("insufficient", insufficient_node)

    builder.add_edge(START, "plan")
    builder.add_edge("plan", "retrieve")
    builder.add_edge("retrieve", "reflect")
    builder.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {RETRIEVE: "retrieve", ANSWER: "answer", INSUFFICIENT: "insufficient"},
    )
    builder.add_edge("answer", END)
    builder.add_edge("insufficient", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())
