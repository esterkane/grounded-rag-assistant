"""Unit tests for Reciprocal Rank Fusion and the permission filter.

These are pure-logic tests — no Elasticsearch required.
"""

from app.retrieval.models import RetrievedChunk
from app.retrieval.retriever import (
    build_permissions_filter,
    effective_roles,
    reciprocal_rank_fusion,
)


def make_chunk(chunk_id: str, method: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        score=0.0,
        content=f"content for {chunk_id}",
        methods=[method],
        doc_id="doc",
        source_path="doc.md",
        source_url="https://example.com/doc",
        title="Doc",
    )


def test_rrf_rewards_agreement_across_methods() -> None:
    # "b" is ranked highly by both methods; it should win the fusion.
    bm25 = [make_chunk("a", "bm25"), make_chunk("b", "bm25"), make_chunk("c", "bm25")]
    vector = [make_chunk("b", "vector"), make_chunk("d", "vector"), make_chunk("a", "vector")]

    fused = reciprocal_rank_fusion([bm25, vector], k=10, rank_constant=60)

    order = [chunk.chunk_id for chunk in fused]
    assert order[0] == "b"
    # "b" appears in both lists -> tagged with both methods.
    b = next(chunk for chunk in fused if chunk.chunk_id == "b")
    assert set(b.methods) == {"bm25", "vector"}


def test_rrf_scores_match_formula() -> None:
    bm25 = [make_chunk("x", "bm25"), make_chunk("y", "bm25")]
    vector = [make_chunk("y", "vector"), make_chunk("x", "vector")]

    fused = reciprocal_rank_fusion([bm25, vector], k=10, rank_constant=60)

    scores = {chunk.chunk_id: chunk.score for chunk in fused}
    # x: rank 1 in bm25, rank 2 in vector. y: rank 2 in bm25, rank 1 in vector.
    expected = 1 / 61 + 1 / 62
    assert scores["x"] == expected
    assert scores["y"] == expected


def test_rrf_respects_k() -> None:
    bm25 = [make_chunk(c, "bm25") for c in "abcde"]
    fused = reciprocal_rank_fusion([bm25], k=3, rank_constant=60)
    assert [chunk.chunk_id for chunk in fused] == ["a", "b", "c"]


def test_rrf_dedupes_by_chunk_id() -> None:
    bm25 = [make_chunk("a", "bm25"), make_chunk("a", "bm25")]
    fused = reciprocal_rank_fusion([bm25], k=10, rank_constant=60)
    assert [chunk.chunk_id for chunk in fused] == ["a"]


def test_effective_roles_always_includes_public() -> None:
    assert effective_roles(None) == {"public"}
    assert effective_roles([]) == {"public"}
    assert effective_roles(["admin"]) == {"public", "admin"}


def test_permissions_filter_is_a_terms_filter_over_effective_roles() -> None:
    assert build_permissions_filter(["admin"]) == {
        "terms": {"permissions": ["admin", "public"]}
    }
    assert build_permissions_filter(None) == {"terms": {"permissions": ["public"]}}
