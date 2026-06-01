"""MCP tool handlers wrapping Project 1's retrieval and generation core.

These are plain, importable functions — no FastMCP or HTTP coupling — so they
can be unit-tested directly with a fake Elasticsearch client and a fake LLM
provider. ``app/mcp/server.py`` registers thin FastMCP wrappers that supply the
cached resource singletons and open an OpenTelemetry span around each call.

Every handler is wrapped by :func:`app.mcp.errors.guard`, so it either returns a
structured success payload or a structured error payload — never a raised
exception or a stack trace.
"""

from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from app.config import get_settings
from app.generation.answerer import answer_question
from app.generation.providers import LLMProvider
from app.ingestion.embedder import SentenceTransformersEmbedder
from app.mcp.errors import ToolBusinessError, ToolValidationError, guard
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.retriever import (
    PUBLIC_ROLE,
    bm25_search,
    build_permissions_filter,
    hybrid_search,
    vector_search,
)

VALID_MODES = ("bm25", "vector", "hybrid")
MAX_K = 100
MAX_LIMIT = 1000


def _validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise ToolValidationError("`query` must be a non-empty string.")
    return query.strip()


def _validate_k(k: int) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or not (1 <= k <= MAX_K):
        raise ToolValidationError(
            f"`k` must be an integer between 1 and {MAX_K}.", details={"k": k}
        )


def _validate_rerank(rerank: bool) -> None:
    if not isinstance(rerank, bool):
        raise ToolValidationError("`rerank` must be a boolean.", details={"rerank": rerank})


def _roles(caller_roles: list[str] | None) -> list[str]:
    if caller_roles is None:
        return [PUBLIC_ROLE]
    if not isinstance(caller_roles, list) or not all(isinstance(r, str) for r in caller_roles):
        raise ToolValidationError("`caller_roles` must be a list of role strings.")
    return caller_roles or [PUBLIC_ROLE]


def _has_matches_ignoring_permissions(client: Elasticsearch, index: str, query: str) -> bool:
    """True if the corpus contains text matches for ``query`` regardless of
    permissions — used only to distinguish "nothing matches" from "matches exist
    but none are visible to the caller's roles" (a business error)."""
    resp = client.count(
        index=index,
        query={"multi_match": {"query": query, "fields": ["content", "title"]}},
    )
    return int(resp.get("count", 0)) > 0


@guard("retrieve_chunks")
def retrieve_chunks_impl(
    query: str,
    *,
    k: int = 8,
    mode: str = "hybrid",
    rerank: bool = False,
    caller_roles: list[str] | None = None,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder | None = None,
    reranker: CrossEncoderReranker | None = None,
    index: str,
    candidate_pool: int = 50,
) -> dict[str, Any]:
    """Retrieve the top chunks for a query. Returns a structured payload."""
    query = _validate_query(query)
    if mode not in VALID_MODES:
        raise ToolValidationError(
            f"`mode` must be one of {VALID_MODES}.", details={"mode": mode}
        )
    _validate_k(k)
    _validate_rerank(rerank)
    roles = _roles(caller_roles)

    if mode in ("vector", "hybrid") and embedder is None:
        # Wiring error, not a user error: the server always supplies an embedder
        # for these modes. Surfaced via the generic guard, not as validation.
        raise RuntimeError(f"mode={mode!r} requires an embedder")

    # When reranking, pull a wider candidate pool, then trim to k after rerank.
    fetch_k = max(k, candidate_pool) if (rerank and reranker is not None) else k

    if mode == "bm25":
        results = bm25_search(client, query, fetch_k, index=index, caller_roles=roles)
    elif mode == "vector":
        results = vector_search(client, embedder, query, fetch_k, index=index, caller_roles=roles)
    else:
        settings = get_settings()
        results = hybrid_search(
            client,
            embedder,
            query,
            fetch_k,
            index=index,
            caller_roles=roles,
            rank_constant=settings.rrf_rank_constant,
            rank_window=settings.rrf_rank_window,
        )

    if rerank and reranker is not None and results:
        results = reranker.rerank(query, results, top_k=k)
    elif len(results) > k:
        results = results[:k]

    if not results and _has_matches_ignoring_permissions(client, index, query):
        raise ToolBusinessError(
            "Documents match this query but none are visible to the caller's roles.",
            details={"caller_roles": roles},
        )

    return {
        "query": query,
        "mode": mode,
        "rerank": bool(rerank),
        "count": len(results),
        "chunks": [chunk.model_dump() for chunk in results],
    }


@guard("answer_with_citations")
def answer_with_citations_impl(
    query: str,
    *,
    k: int = 8,
    rerank: bool = False,
    caller_roles: list[str] | None = None,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder,
    provider: LLMProvider,
    reranker: CrossEncoderReranker | None = None,
    index: str,
) -> dict[str, Any]:
    """Run the full grounded-answer pipeline. Returns the GroundedAnswer payload.

    Insufficient evidence is *not* an error here: the answerer returns a
    structured answer with ``answered=false`` / ``insufficient=true`` and empty
    claims, which is passed through verbatim.
    """
    query = _validate_query(query)
    _validate_k(k)
    _validate_rerank(rerank)
    roles = _roles(caller_roles)
    settings = get_settings()

    answer = answer_question(
        query,
        client=client,
        embedder=embedder,
        provider=provider,
        index=index,
        k=k,
        caller_roles=roles,
        rerank=rerank,
        reranker=reranker,
        rank_constant=settings.rrf_rank_constant,
        rank_window=settings.rrf_rank_window,
        rerank_candidate_pool=settings.rerank_candidate_pool,
    )
    return answer.model_dump()


@guard("list_documents")
def list_documents_impl(
    prefix: str | None = None,
    *,
    limit: int = 50,
    caller_roles: list[str] | None = None,
    client: Elasticsearch,
    index: str,
) -> dict[str, Any]:
    """List distinct documents (doc_id / title / source_url) in the corpus.

    Only documents with at least one chunk visible to ``caller_roles`` are
    returned, mirroring the permission filtering of the retrieval tools — the
    catalog must not leak the existence of restricted documents.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= MAX_LIMIT):
        raise ToolValidationError(
            f"`limit` must be an integer between 1 and {MAX_LIMIT}.", details={"limit": limit}
        )
    if prefix is not None:
        if not isinstance(prefix, str):
            raise ToolValidationError(
                "`prefix` must be a string when provided.", details={"prefix": prefix}
            )
        # Treat a whitespace-only prefix as "no prefix".
        prefix = prefix.strip() or None

    roles = _roles(caller_roles)
    # Restrict the aggregation to chunks visible to the caller's roles, so only
    # documents with at least one visible chunk surface in the catalog.
    filters: list[dict[str, Any]] = [build_permissions_filter(roles)]
    if prefix:
        filters.append({"prefix": {"doc_id": prefix}})

    resp = client.search(
        index=index,
        size=0,
        query={"bool": {"filter": filters}},
        aggs={
            "docs": {
                "terms": {"field": "doc_id", "size": limit, "order": {"_key": "asc"}},
                "aggs": {
                    "top": {
                        "top_hits": {
                            "size": 1,
                            "_source": ["doc_id", "title", "source_url"],
                        }
                    }
                },
            }
        },
    )

    buckets = resp.get("aggregations", {}).get("docs", {}).get("buckets", [])
    documents = []
    for bucket in buckets:
        hits = bucket.get("top", {}).get("hits", {}).get("hits", [])
        source = hits[0].get("_source", {}) if hits else {}
        documents.append(
            {
                "doc_id": source.get("doc_id", bucket.get("key", "")),
                "title": source.get("title", ""),
                "source_url": source.get("source_url", ""),
            }
        )

    return {"count": len(documents), "documents": documents}
