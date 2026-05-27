"""Retrieval over Elasticsearch: BM25, vector kNN, and hybrid RRF fusion.

Pure, importable functions with **no FastAPI coupling** (a later phase exposes
these as MCP tools). The HTTP layer in ``app/api/`` adapts them; logic lives here.

``hybrid_search`` uses Elasticsearch's native RRF retriever when available and
falls back to a Python RRF implementation otherwise — detected automatically and
cached. Permission filtering (dropping chunks whose ``permissions`` do not
intersect the caller's roles) is a retrieval-layer concern handled in ``search``.
"""

from __future__ import annotations

from app.config import settings
from app.retrieval.models import RetrievalResult

# RRF rank constant (the conventional default).
RANK_CONSTANT = 60
# BGE retrieval is asymmetric: the query gets an instruction, passages do not.
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_client = None
_embedder = None
# Tri-state cache for native RRF support: None=unknown, True/False once probed.
_native_rrf: bool | None = None


def _get_client():
    global _client
    if _client is None:
        from elasticsearch import Elasticsearch

        _client = Elasticsearch(settings.es_url, request_timeout=30)
    return _client


def _embed_query(query: str) -> list[float]:
    global _embedder
    if _embedder is None:
        from app.ingestion.embedder import Embedder

        _embedder = Embedder()
    return _embedder.encode([QUERY_INSTRUCTION + query])[0]


def _bm25_query(query: str) -> dict:
    return {"multi_match": {"query": query, "fields": ["content", "title^2"]}}


def bm25_search(
    query: str, k: int = 5, client=None, index: str | None = None
) -> list[RetrievalResult]:
    """Lexical BM25 search over content + title."""
    client = client or _get_client()
    index = index or settings.es_index
    resp = client.search(index=index, query=_bm25_query(query), size=k)
    return [RetrievalResult.from_hit(h, methods=["bm25"]) for h in resp["hits"]["hits"]]


def _knn_search(
    query_vector: list[float], k: int, client, index: str
) -> list[RetrievalResult]:
    resp = client.search(
        index=index,
        knn={
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": max(100, k * 5),
        },
        size=k,
    )
    return [RetrievalResult.from_hit(h, methods=["vector"]) for h in resp["hits"]["hits"]]


def vector_search(
    query: str, k: int = 5, client=None, index: str | None = None
) -> list[RetrievalResult]:
    """Dense vector kNN search: embed the query, then ES kNN on ``embedding``."""
    client = client or _get_client()
    index = index or settings.es_index
    return _knn_search(_embed_query(query), k, client, index)


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievalResult]],
    rank_constant: int = RANK_CONSTANT,
    top_k: int | None = None,
) -> list[RetrievalResult]:
    """Fuse ranked lists with RRF: score = sum 1/(rank_constant + rank).

    Pure function (no ES) — unit-tested with fixed inputs. Method tags are unioned
    across the lists a chunk appears in.
    """
    scores: dict[str, float] = {}
    methods: dict[str, set[str]] = {}
    representative: dict[str, RetrievalResult] = {}

    for results in result_lists:
        for rank, result in enumerate(results, start=1):
            cid = result.chunk_id
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rank_constant + rank)
            methods.setdefault(cid, set()).update(result.methods)
            representative.setdefault(cid, result)

    fused = [
        representative[cid].model_copy(
            update={"score": score, "methods": sorted(methods[cid])}
        )
        for cid, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return fused[:top_k] if top_k else fused


def _native_rrf_search(
    query: str, query_vector: list[float], k: int, client, index: str
) -> list[dict]:
    """Run ES native RRF retriever; returns raw hits. Raises if unsupported."""
    resp = client.search(
        index=index,
        retriever={
            "rrf": {
                "retrievers": [
                    {"standard": {"query": _bm25_query(query)}},
                    {
                        "knn": {
                            "field": "embedding",
                            "query_vector": query_vector,
                            "k": k,
                            "num_candidates": max(100, k * 5),
                        }
                    },
                ],
                "rank_window_size": k,
                "rank_constant": RANK_CONSTANT,
            }
        },
        size=k,
    )
    return resp["hits"]["hits"]


def hybrid_search(
    query: str, k: int = 5, client=None, index: str | None = None
) -> list[RetrievalResult]:
    """Combine BM25 and vector search with RRF.

    Prefers Elasticsearch native RRF; auto-detects and falls back to Python RRF.
    Method tags are derived from which of the BM25 / vector result sets each chunk
    appears in.
    """
    global _native_rrf
    client = client or _get_client()
    index = index or settings.es_index

    query_vector = _embed_query(query)
    bm25 = bm25_search(query, k, client, index)
    vector = _knn_search(query_vector, k, client, index)
    bm25_ids = {r.chunk_id for r in bm25}
    vector_ids = {r.chunk_id for r in vector}

    def _python_fusion() -> list[RetrievalResult]:
        return reciprocal_rank_fusion([bm25, vector], top_k=k)

    if _native_rrf is False:
        return _python_fusion()

    try:
        hits = _native_rrf_search(query, query_vector, k, client, index)
        _native_rrf = True
    except Exception:  # noqa: BLE001 - unsupported version / client → fall back
        _native_rrf = False
        return _python_fusion()

    results: list[RetrievalResult] = []
    for hit in hits:
        cid = hit.get("_source", {}).get("chunk_id", hit.get("_id", ""))
        methods = [m for m, ids in (("bm25", bm25_ids), ("vector", vector_ids)) if cid in ids]
        results.append(RetrievalResult.from_hit(hit, methods=methods or ["hybrid"]))
    return results


def filter_by_permissions(
    results: list[RetrievalResult], caller_roles: list[str] | None
) -> list[RetrievalResult]:
    """Drop chunks whose ``permissions`` do not intersect the caller's roles.

    A caller with no roles is treated as ``["public"]``.
    """
    roles = set(caller_roles) if caller_roles else {"public"}
    return [r for r in results if set(r.permissions) & roles]


def search(
    query: str,
    k: int = 5,
    rerank: bool | None = None,
    caller_roles: list[str] | None = None,
    client=None,
    index: str | None = None,
) -> list[RetrievalResult]:
    """End-to-end retrieval: hybrid fusion -> permission filter -> optional rerank.

    ``rerank`` overrides the ``RERANK_ENABLED`` config flag when not None.
    """
    fetch_n = max(k * 4, 20)
    fused = hybrid_search(query, fetch_n, client, index)
    fused = filter_by_permissions(fused, caller_roles)

    do_rerank = settings.rerank_enabled if rerank is None else rerank
    if do_rerank and fused:
        from app.retrieval.reranker import rerank_results

        return rerank_results(query, fused, top_k=k)
    return fused[:k]
