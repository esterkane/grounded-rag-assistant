"""Unit tests for grounded-answer assembly and the provider factory.

No Elasticsearch and no real LLM — a FakeProvider returns canned text so we can
exercise citation validation, the insufficient-evidence path, and parse-retry.
"""

import pytest

from app.generation.answerer import build_grounded_answer
from app.generation.providers.base import LLMProvider
from app.generation.providers.factory import get_provider
from app.generation.providers.gemini import GeminiProvider
from app.generation.providers.ollama import OllamaProvider
from app.retrieval.models import RetrievalResult


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responses):
        self.responses = responses if isinstance(responses, list) else [responses]
        self.calls = 0

    def generate(self, messages, **opts):
        out = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return out


def _res(chunk_id: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=1.0,
        content=f"content for {chunk_id}",
        title="Doc",
        heading_path="",
        source_url=f"https://example/{chunk_id}",
        version="main",
        last_updated=None,
        doc_id="d",
        permissions=["public"],
        methods=["hybrid"],
    )


RESULTS = [_res("c1"), _res("c2")]


def test_answerable_returns_valid_citations_and_sources():
    p = FakeProvider(
        '{"answer":"BM25 is lexical.",'
        '"claims":[{"text":"BM25 is lexical scoring.","citations":["c1"]}],'
        '"insufficient":false}'
    )
    ans = build_grounded_answer("q", RESULTS, p)
    assert ans.answered and not ans.insufficient
    assert ans.claims[0].citations == ["c1"]
    assert {s.chunk_id for s in ans.sources} == {"c1"}


def test_invalid_citations_are_dropped():
    p = FakeProvider(
        '{"answer":"x","claims":[{"text":"t","citations":["c1","bogus"]}],"insufficient":false}'
    )
    ans = build_grounded_answer("q", RESULTS, p)
    assert ans.claims[0].citations == ["c1"]  # bogus dropped
    assert {s.chunk_id for s in ans.sources} == {"c1"}


def test_all_invalid_citations_fall_back_to_insufficient():
    p = FakeProvider(
        '{"answer":"made up","claims":[{"text":"t","citations":["nope"]}],"insufficient":false}'
    )
    ans = build_grounded_answer("q", RESULTS, p)
    assert ans.answered is False
    assert ans.insufficient is True
    assert ans.claims == []


def test_model_declared_insufficient():
    p = FakeProvider('{"answer":"no evidence","claims":[],"insufficient":true}')
    ans = build_grounded_answer("q", RESULTS, p)
    assert ans.answered is False and ans.insufficient is True


def test_parse_retry_recovers_from_garbage_first_response():
    p = FakeProvider(
        [
            "I'm not going to give JSON, sorry!",
            '{"answer":"ok","claims":[{"text":"t","citations":["c2"]}],"insufficient":false}',
        ]
    )
    ans = build_grounded_answer("q", RESULTS, p)
    assert p.calls == 2
    assert ans.answered is True
    assert ans.claims[0].citations == ["c2"]


def test_unparseable_twice_is_insufficient():
    p = FakeProvider(["garbage", "still garbage"])
    ans = build_grounded_answer("q", RESULTS, p)
    assert ans.insufficient is True and ans.answered is False


def test_no_results_short_circuits_without_calling_provider():
    p = FakeProvider("should not be used")
    ans = build_grounded_answer("q", [], p)
    assert ans.insufficient is True
    assert p.calls == 0


def test_factory_selects_provider_by_name():
    assert isinstance(get_provider("gemini"), GeminiProvider)
    assert isinstance(get_provider("ollama"), OllamaProvider)
    with pytest.raises(ValueError):
        get_provider("nope")
