"""Unit tests for the grounded-generation core.

These use a fake provider and fixed chunks — no Elasticsearch and no live LLM.
"""

import json

from app.generation.answerer import (
    build_context_block,
    generate_grounded_answer,
)
from app.generation.providers.base import LLMProvider
from app.retrieval.models import RetrievedChunk


def make_chunk(chunk_id: str, content: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        score=1.0,
        content=content,
        methods=["hybrid"],
        doc_id="doc",
        source_path="doc.md",
        source_url=f"https://example.com/{chunk_id}",
        title=f"Title {chunk_id}",
    )


class ScriptedProvider(LLMProvider):
    """Returns canned responses in sequence (one per generate() call)."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls = 0

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        self.calls += 1
        if not self._responses:
            return ""
        return self._responses.pop(0)


CHUNKS = [
    make_chunk("c1", "Elasticsearch stores dense vectors for kNN search."),
    make_chunk("c2", "RRF fuses BM25 and vector rankings."),
]


def test_context_block_labels_chunk_id_and_source_url() -> None:
    block = build_context_block(CHUNKS)
    assert "[1] (chunk_id=c1 source_url=https://example.com/c1)" in block
    assert "[2] (chunk_id=c2 source_url=https://example.com/c2)" in block
    assert "dense vectors" in block


def test_answerable_query_returns_valid_citations() -> None:
    provider = ScriptedProvider(
        json.dumps(
            {
                "answered": True,
                "answer": "Elasticsearch supports kNN over dense vectors.",
                "claims": [
                    {"text": "It stores dense vectors for kNN.", "citations": ["c1"]}
                ],
            }
        )
    )

    answer = generate_grounded_answer("How does ES do vector search?", CHUNKS, provider)

    assert answer.answered is True
    assert answer.insufficient is False
    # Every citation maps to a real retrieved chunk.
    cited = {cid for claim in answer.claims for cid in claim.citations}
    assert cited == {"c1"}
    assert all(cid in {c.chunk_id for c in CHUNKS} for cid in cited)
    assert [s.chunk_id for s in answer.sources] == ["c1"]
    assert answer.dropped_citations == []


def test_offtopic_query_takes_insufficient_path() -> None:
    provider = ScriptedProvider(
        json.dumps(
            {
                "answered": False,
                "answer": "The context does not cover this topic.",
                "claims": [],
            }
        )
    )

    answer = generate_grounded_answer("What is the capital of France?", CHUNKS, provider)

    assert answer.answered is False
    assert answer.insufficient is True
    assert answer.claims == []
    assert answer.sources == []


def test_invalid_citations_are_dropped_and_grounding_enforced() -> None:
    # Model claims it answered but cites a chunk that was never in context.
    provider = ScriptedProvider(
        json.dumps(
            {
                "answered": True,
                "answer": "Made-up answer.",
                "claims": [{"text": "Hallucinated claim.", "citations": ["ghost"]}],
            }
        )
    )

    answer = generate_grounded_answer("anything", CHUNKS, provider)

    # No valid citation remains -> cannot be trusted -> insufficient path.
    assert answer.answered is False
    assert answer.insufficient is True
    assert "ghost" in answer.dropped_citations


def test_parse_failure_retries_once_then_succeeds() -> None:
    provider = ScriptedProvider(
        "not json at all",
        json.dumps(
            {
                "answered": True,
                "answer": "Recovered on retry.",
                "claims": [{"text": "RRF fuses rankings.", "citations": ["c2"]}],
            }
        ),
    )

    answer = generate_grounded_answer("How does RRF work?", CHUNKS, provider)

    assert provider.calls == 2  # retried once
    assert answer.answered is True
    assert [s.chunk_id for s in answer.sources] == ["c2"]


def test_unparseable_output_after_retry_is_insufficient() -> None:
    provider = ScriptedProvider("garbage", "still garbage")

    answer = generate_grounded_answer("How does RRF work?", CHUNKS, provider)

    assert provider.calls == 2
    assert answer.answered is False
    assert answer.insufficient is True


def test_no_chunks_short_circuits_to_insufficient_without_calling_llm() -> None:
    provider = ScriptedProvider(json.dumps({"answered": True, "answer": "x", "claims": []}))

    answer = generate_grounded_answer("anything", [], provider)

    assert provider.calls == 0
    assert answer.insufficient is True
