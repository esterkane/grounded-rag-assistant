"""Unit tests for the agent's plan / reflect routing logic.

Pure-logic tests with a fake provider — no LLM, no MCP, no Elasticsearch.
"""

import json

from app.agent.reasoning import ANSWER, INSUFFICIENT, RETRIEVE, plan_subqueries, reflect
from app.generation.providers.base import LLMProvider

CHUNKS = [{"chunk_id": "c1", "title": "Vector search", "content": "Uses dense embeddings."}]


class FakeProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        return self._response


# --- plan -----------------------------------------------------------------


def test_plan_single_query():
    p = FakeProvider(json.dumps({"sub_queries": ["just one"]}))
    assert plan_subqueries(p, "q") == ["just one"]


def test_plan_clamps_to_three():
    p = FakeProvider(json.dumps({"sub_queries": ["a", "b", "c", "d"]}))
    assert plan_subqueries(p, "q") == ["a", "b", "c"]


def test_plan_falls_back_to_query_on_bad_json():
    assert plan_subqueries(FakeProvider("not json at all"), "the original") == ["the original"]


def test_plan_falls_back_when_empty():
    assert plan_subqueries(FakeProvider(json.dumps({"sub_queries": []})), "q") == ["q"]


# --- reflect --------------------------------------------------------------


def test_reflect_sufficient_routes_to_answer():
    p = FakeProvider(json.dumps({"sufficient": True}))
    assert reflect(p, "q", CHUNKS, 0, 2).action == ANSWER


def test_reflect_insufficient_with_hops_left_retrieves():
    p = FakeProvider(json.dumps({"sufficient": False, "follow_up_query": "go deeper"}))
    d = reflect(p, "q", CHUNKS, 0, 2)
    assert d.action == RETRIEVE
    assert d.follow_up == "go deeper"


def test_reflect_insufficient_when_exhausted_gives_insufficient():
    p = FakeProvider(json.dumps({"sufficient": False, "follow_up_query": "x"}))
    assert reflect(p, "q", CHUNKS, 2, 2).action == INSUFFICIENT


def test_reflect_no_chunks_exhausted_is_insufficient():
    assert reflect(FakeProvider("{}"), "q", [], 2, 2).action == INSUFFICIENT


def test_reflect_no_chunks_with_hops_left_retries():
    assert reflect(FakeProvider("{}"), "q", [], 0, 2).action == RETRIEVE


def test_reflect_parse_failure_defers_to_answer():
    # With chunks present, an unparseable reflect output defers to the grounded
    # answerer (which never hallucinates) rather than looping.
    assert reflect(FakeProvider("garbage"), "q", CHUNKS, 0, 2).action == ANSWER
