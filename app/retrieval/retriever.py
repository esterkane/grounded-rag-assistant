"""Hybrid retrieval over Elasticsearch.

Pure, importable functions with **no FastAPI coupling** (a later phase exposes
these as MCP tools). Each function takes an Elasticsearch client (and, where
needed, an embedder) and returns a list of :class:`RetrievedChunk`.

Three retrieval methods are provided:

- :func:`bm25_search` — lexical ``multi_match`` over ``content`` + ``title``.
- :func:`vector_search` — embed the query and run kNN over the ``embedding`` field.
- :func:`hybrid_search` — Reciprocal Rank Fusion of the two. Uses the
  Elasticsearch **native RRF retriever** when the cluster supports it and falls
  back to a pure-Python RRF implementation otherwise (auto-detected).

Permission filtering (dropping chunks whose ``permissions`` do not intersect the
caller's roles) is applied at the Elasticsearch query level so it is correct with
respect to ``k``.
"""

import logging
from typing import Any, Protocol

from elasticsearch import ApiError, Elasticsearch, TransportError

from app.retrieval.models import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_K = 10
DEFAULT_RANK_CONSTANT = 60
DEFAULT_RANK_WINDOW = 50
PUBLIC_ROLE = "public"

# The ES vector field name (see the rag_chunks mapping in app/ingestion/index.py).
VECTOR_FIELD = "embedding"

# Auto-detection cache for native RRF retriever support, keyed by cluster name.
# None = not yet probed, True/False = known support.
_native_rrf_support: dict[str, bool] = {}


class Embedder(Protocol):
    """Minimal embedder interface (satisfied by SentenceTransformersEmbedder)."""

    def embed(self, texts: list[str], batch_size: int = ...) -> list[list[float]]: ...


def effective_roles(caller_roles: list[str] | None) -> set[str]:
    """The caller's roles, always including the implicit ``public`` role."""
    return set(caller_roles or []) | {PUBLIC_ROLE}


def build_permissions_filter(caller_roles: list[str] | None) -> dict[str, Any]:
    """An ES ``terms`` filter matching chunks visible to ``caller_roles``.

    A chunk is visible when its ``permissions`` list intersects the caller's
    effective roles. Everyone implicitly has the ``public`` role, so public
    chunks are always visible and restricted chunks require a matching role.
    """
    return {"terms": {"permissions": sorted(effective_roles(caller_roles))}}


def _hit_to_chunk(
    hit: dict[str, Any], methods: list[str], score: float | None = None
) -> RetrievedChunk:
    source = hit["_source"]
    return RetrievedChunk(
        chunk_id=source["chunk_id"],
        score=float(score if score is not None else hit.get("_score") or 0.0),
        content=source.get("content", ""),
        methods=list(methods),
        doc_id=source.get("doc_id", ""),
        source_path=source.get("source_path", ""),
        source_url=source.get("source_url", ""),
        title=source.get("title", ""),
        heading_path=source.get("heading_path", []) or [],
        version=source.get("version", ""),
        last_updated=source.get("last_updated", ""),
        ingested_at=source.get("ingested_at", ""),
        permissions=source.get("permissions", [PUBLIC_ROLE]) or [PUBLIC_ROLE],
        chunk_index=source.get("chunk_index", 0),
    )


def bm25_search(
    client: Elasticsearch,
    query: str,
    k: int = DEFAULT_K,
    *,
    index: str,
    caller_roles: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Lexical BM25 search over ``content`` and ``title``."""
    body: dict[str, Any] = {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["content", "title^1.5"],
                    }
                }
            ],
            "filter": [build_permissions_filter(caller_roles)],
        }
    }
    response = client.search(index=index, query=body, size=k)
    return [_hit_to_chunk(hit, ["bm25"]) for hit in response["hits"]["hits"]]


def vector_search(
    client: Elasticsearch,
    embedder: Embedder,
    query: str,
    k: int = DEFAULT_K,
    *,
    index: str,
    caller_roles: list[str] | None = None,
    num_candidates: int | None = None,
) -> list[RetrievedChunk]:
    """Semantic kNN search over the dense ``embedding`` field."""
    query_vector = embedder.embed([query])[0]
    knn = {
        "field": VECTOR_FIELD,
        "query_vector": query_vector,
        "k": k,
        "num_candidates": num_candidates or max(k * 10, 100),
        "filter": build_permissions_filter(caller_roles),
    }
    response = client.search(index=index, knn=knn, size=k)
    return [_hit_to_chunk(hit, ["vector"]) for hit in response["hits"]["hits"]]


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    k: int = DEFAULT_K,
    *,
    rank_constant: int = DEFAULT_RANK_CONSTANT,
) -> list[RetrievedChunk]:
    """Fuse several ranked result lists with Reciprocal Rank Fusion.

    Each chunk's fused score is ``sum(1 / (rank_constant + rank))`` over every
    list it appears in (rank is 1-based). Chunks are deduplicated by
    ``chunk_id``; the merged result records the union of the ``methods`` from
    each list it appeared in. Returns the top ``k`` by fused score.

    This is a pure function (no Elasticsearch needed) and is unit-tested with
    fixed inputs.
    """
    fused_scores: dict[str, float] = {}
    fused_methods: dict[str, list[str]] = {}
    representative: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            cid = chunk.chunk_id
            fused_scores[cid] = fused_scores.get(cid, 0.0) + 1.0 / (rank_constant + rank)
            methods = fused_methods.setdefault(cid, [])
            for method in chunk.methods:
                if method not in methods:
                    methods.append(method)
            representative.setdefault(cid, chunk)

    ordered = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    results: list[RetrievedChunk] = []
    for cid in ordered[:k]:
        chunk = representative[cid].model_copy(
            update={"score": fused_scores[cid], "methods": fused_methods[cid]}
        )
        results.append(chunk)
    return results


def _supports_native_rrf(client: Elasticsearch) -> bool:
    """Probe (and cache) whether the cluster's RRF retriever API is usable."""
    try:
        cluster_name = client.info().get("cluster_name", "default")
    except (ApiError, TransportError):  # pragma: no cover - network failure
        return False
    return _native_rrf_support.get(cluster_name, True)


def _record_native_rrf_support(client: Elasticsearch, supported: bool) -> None:
    try:
        cluster_name = client.info().get("cluster_name", "default")
    except (ApiError, TransportError):  # pragma: no cover - network failure
        return
    _native_rrf_support[cluster_name] = supported


def _native_rrf_search(
    client: Elasticsearch,
    query: str,
    query_vector: list[float],
    k: int,
    *,
    index: str,
    caller_roles: list[str] | None,
    rank_constant: int,
    rank_window: int,
) -> list[RetrievedChunk]:
    permissions_filter = build_permissions_filter(caller_roles)
    retriever = {
        "rrf": {
            "retrievers": [
                {
                    "standard": {
                        "query": {
                            "bool": {
                                "must": [
                                    {
                                        "multi_match": {
                                            "query": query,
                                            "fields": ["content", "title^1.5"],
                                        }
                                    }
                                ],
                                "filter": [permissions_filter],
                            }
                        }
                    }
                },
                {
                    "knn": {
                        "field": VECTOR_FIELD,
                        "query_vector": query_vector,
                        "k": rank_window,
                        "num_candidates": max(rank_window * 2, 100),
                        "filter": permissions_filter,
                    }
                },
            ],
            "rank_window_size": rank_window,
            "rank_constant": rank_constant,
        }
    }
    response = client.search(index=index, retriever=retriever, size=k)
    return [_hit_to_chunk(hit, ["hybrid"]) for hit in response["hits"]["hits"]]


def hybrid_search(
    client: Elasticsearch,
    embedder: Embedder,
    query: str,
    k: int = DEFAULT_K,
    *,
    index: str,
    caller_roles: list[str] | None = None,
    rank_constant: int = DEFAULT_RANK_CONSTANT,
    rank_window: int = DEFAULT_RANK_WINDOW,
) -> list[RetrievedChunk]:
    """Hybrid BM25 + vector retrieval fused with Reciprocal Rank Fusion.

    Uses the Elasticsearch native RRF retriever when supported, otherwise falls
    back to running BM25 and vector searches separately and fusing them in
    Python. Support is auto-detected and cached.
    """
    query_vector = embedder.embed([query])[0]
    window = max(rank_window, k)

    if _supports_native_rrf(client):
        try:
            results = _native_rrf_search(
                client,
                query,
                query_vector,
                k,
                index=index,
                caller_roles=caller_roles,
                rank_constant=rank_constant,
                rank_window=window,
            )
            _record_native_rrf_support(client, True)
            return results
        except (ApiError, TransportError) as exc:
            logger.warning(
                "Native RRF retriever unavailable (%s); falling back to Python RRF.",
                getattr(exc, "message", exc),
            )
            _record_native_rrf_support(client, False)

    # Python fallback: fetch each method's window then fuse.
    bm25_hits = bm25_search(client, query, window, index=index, caller_roles=caller_roles)
    knn = {
        "field": VECTOR_FIELD,
        "query_vector": query_vector,
        "k": window,
        "num_candidates": max(window * 2, 100),
        "filter": build_permissions_filter(caller_roles),
    }
    response = client.search(index=index, knn=knn, size=window)
    vector_hits = [_hit_to_chunk(hit, ["vector"]) for hit in response["hits"]["hits"]]

    fused = reciprocal_rank_fusion(
        [bm25_hits, vector_hits], k, rank_constant=rank_constant
    )
    # Tag fused results as hybrid while preserving the contributing methods.
    return [
        chunk.model_copy(
            update={"methods": ["hybrid", *[m for m in chunk.methods if m != "hybrid"]]}
        )
        for chunk in fused
    ]
