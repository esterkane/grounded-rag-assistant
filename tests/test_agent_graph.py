"""Full-graph tests for the agent workflow.

These exercise the compiled plan → retrieve → reflect → answer graph end to end
with in-process fake tools (returning the same dict shapes the MCP tools return)
and a scripted provider — deterministic, no MCP/ES/LLM. They cover the grounded
path, a multi-hop re-retrieval, and the insufficient-evidence terminal.
"""

import asyncio
import json

from app.agent.graph import build_agent_graph
from app.generation.providers.base import LLMProvider


class RoutingProvider(LLMProvider):
    """Returns plan sub-queries, then a scripted sequence of reflect verdicts."""

    def __init__(self, sub_queries, sufficiencies) -> None:
        self._subs = sub_queries
        self._suff = list(sufficiencies)

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        system = messages[0]["content"]
        if "plan retrieval" in system:
            return json.dumps({"sub_queries": self._subs})
        sufficient = self._suff.pop(0) if self._suff else True
        return json.dumps({"sufficient": sufficient, "follow_up_query": "follow-up"})


class FakeTool:
    def __init__(self, fn) -> None:
        self._fn = fn
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return self._fn(args)


def _retrieve_ok(args):
    return {
        "isError": False,
        "count": 1,
        "chunks": [
            {"chunk_id": "c1", "title": "Vector search", "content": "Uses dense embeddings."}
        ],
    }


def _answer_grounded(args):
    return {
        "query": args["query"],
        "answered": True,
        "insufficient": False,
        "answer": "Grounded answer.",
        "claims": [{"text": "A grounded claim.", "citations": ["c1"]}],
        "sources": [{"chunk_id": "c1", "source_url": "u", "title": "Vector search"}],
        "dropped_citations": [],
        "model": "fake",
        "usage": None,
    }


def _run(graph, query, max_hops=2):
    state = {"query": query, "max_hops": max_hops, "hop": 0, "retrieved": [], "trace_id": "t1"}
    return asyncio.run(graph.ainvoke(state, {"configurable": {"thread_id": "t1"}}))


def test_graph_returns_grounded_answer_with_mapped_citations():
    tools = {
        "retrieve_chunks": FakeTool(_retrieve_ok),
        "answer_with_citations": FakeTool(_answer_grounded),
    }
    graph = build_agent_graph(tools, RoutingProvider(["q"], [True]))
    final = _run(graph, "how does vector search work?")

    answer = final["final_answer"]
    assert answer["answered"] is True
    cited = {c for claim in answer["claims"] for c in claim["citations"]}
    sources = {s["chunk_id"] for s in answer["sources"]}
    assert cited and cited <= sources


def test_graph_reretrieves_then_answers():
    retrieve = FakeTool(_retrieve_ok)
    tools = {"retrieve_chunks": retrieve, "answer_with_citations": FakeTool(_answer_grounded)}
    # reflect: insufficient once (re-retrieve), then sufficient (answer).
    graph = build_agent_graph(tools, RoutingProvider(["q"], [False, True]), max_hops=2)
    final = _run(graph, "multi-part question")

    assert final["final_answer"]["answered"] is True
    assert len(retrieve.calls) == 2  # initial pass + one reflect-driven follow-up


def test_graph_routes_to_insufficient_when_hops_exhausted():
    answer = FakeTool(_answer_grounded)
    tools = {"retrieve_chunks": FakeTool(_retrieve_ok), "answer_with_citations": answer}
    # Never sufficient; with max_hops=1 the second reflect is exhausted.
    graph = build_agent_graph(tools, RoutingProvider(["q"], [False, False]), max_hops=1)
    final = _run(graph, "off-corpus question", max_hops=1)

    fa = final["final_answer"]
    assert fa["answered"] is False
    assert fa["insufficient"] is True
    assert fa["claims"] == []
    assert answer.calls == []  # the answerer is never invoked on the insufficient path
