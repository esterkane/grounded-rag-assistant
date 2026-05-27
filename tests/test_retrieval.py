"""Unit tests for RRF fusion and permission filtering (no ES, no model)."""

from app.retrieval.models import RetrievalResult
from app.retrieval.retriever import filter_by_permissions, reciprocal_rank_fusion


def _r(chunk_id: str, methods: list[str], permissions: list[str] | None = None) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=0.0,
        content=f"content {chunk_id}",
        title="t",
        heading_path="",
        source_url="https://example/doc",
        version="main",
        last_updated=None,
        doc_id="d",
        permissions=permissions or ["public"],
        methods=methods,
    )


def test_rrf_fuses_and_orders_by_reciprocal_rank():
    bm25 = [_r("a", ["bm25"]), _r("b", ["bm25"]), _r("c", ["bm25"])]
    vector = [_r("b", ["vector"]), _r("c", ["vector"]), _r("d", ["vector"])]

    fused = reciprocal_rank_fusion([bm25, vector])
    order = [r.chunk_id for r in fused]

    # b and c appear in both lists at strong ranks → top; a then d by single-list rank.
    assert order == ["b", "c", "a", "d"]
    assert fused[0].score > fused[1].score > fused[2].score


def test_rrf_unions_method_tags():
    bm25 = [_r("b", ["bm25"])]
    vector = [_r("b", ["vector"])]
    fused = reciprocal_rank_fusion([bm25, vector])
    assert fused[0].methods == ["bm25", "vector"]


def test_rrf_respects_top_k():
    bm25 = [_r("a", ["bm25"]), _r("b", ["bm25"]), _r("c", ["bm25"])]
    assert len(reciprocal_rank_fusion([bm25], top_k=2)) == 2


def test_permission_filter_intersects_roles():
    results = [
        _r("pub", ["bm25"], ["public"]),
        _r("adm", ["bm25"], ["admin"]),
        _r("beta", ["bm25"], ["public", "beta"]),
    ]
    assert {r.chunk_id for r in filter_by_permissions(results, ["public"])} == {"pub", "beta"}
    assert {r.chunk_id for r in filter_by_permissions(results, ["admin"])} == {"adm"}
    assert {r.chunk_id for r in filter_by_permissions(results, ["beta"])} == {"beta"}
    # No roles → treated as public.
    assert {r.chunk_id for r in filter_by_permissions(results, None)} == {"pub", "beta"}
