"""FastMCP server for grounded-rag-assistant (Project 2).

Exposes Project 1's retrieval and generation core as three MCP tools that any
MCP client (a LangGraph agent, Claude Code, Cursor) can call:

- ``retrieve_chunks`` — hybrid/bm25/vector retrieval over the documentation.
- ``answer_with_citations`` — the full grounded-answer pipeline.
- ``list_documents`` — a catalog of indexed documents for planning.

The tool *logic* lives in :mod:`app.mcp.tools` as plain functions; the wrappers
here add an OpenTelemetry span (so the trace_id propagates into the already
instrumented retriever/answerer) and supply the cached resource singletons.

Transport is selected by ``MCP_TRANSPORT``: ``stdio`` (default, for local dev
and Claude Code) or ``http`` (streamable-HTTP on ``MCP_HTTP_HOST``/
``MCP_HTTP_PORT``, for the LangGraph client in Phase 2).

Run it with::

    make mcp-server          # docker compose run --no-deps -i api python -m app.mcp.server
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from opentelemetry import trace

from app.config import get_settings
from app.mcp.errors import guard
from app.mcp.resources import get_embedder, get_es_client, get_provider, get_reranker
from app.mcp.tools import (
    answer_with_citations_impl,
    list_documents_impl,
    retrieve_chunks_impl,
)

tracer = trace.get_tracer(__name__)

_settings = get_settings()
mcp = FastMCP(
    "grounded-rag",
    host=_settings.mcp_http_host,
    port=_settings.mcp_http_port,
)


@mcp.tool()
@guard("retrieve_chunks")
def retrieve_chunks(
    query: str,
    k: int = 8,
    mode: str = "hybrid",
    rerank: bool = False,
    caller_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Retrieve the most relevant documentation chunks for a query.

    WHAT IT DOES: Runs retrieval over the indexed Elasticsearch/AI-search
    documentation corpus and returns the top-k matching chunks with their text,
    relevance score, the retrieval method(s) that surfaced them, and full
    metadata (doc_id, title, source_url, heading_path, version, chunk_index).

    WHEN TO USE: To gather raw evidence before reasoning or composing an answer
    yourself, to inspect what the corpus contains for a topic, or as the
    retrieval step of a multi-hop plan. Use this when you want the chunks, not a
    finished answer.

    WHEN NOT TO USE: If you want a finished, citation-grounded answer, call
    `answer_with_citations` instead — it runs retrieval AND generation with
    grounding enforcement. To discover which documents exist, call
    `list_documents`.

    INPUTS:
      - query (str, required): natural-language search query.
      - k (int, default 8, 1..100): number of chunks to return.
      - mode (str, default "hybrid"): "bm25" (lexical), "vector" (semantic), or
        "hybrid" (reciprocal-rank fusion of both — recommended).
      - rerank (bool, default false): apply a cross-encoder reranker over a wider
        candidate pool, then trim to k. Improves ordering; slower.
      - caller_roles (list[str], default ["public"]): the caller's roles. Chunks
        whose `permissions` do not intersect these roles are never returned.

    OUTPUT: {query, mode, rerank, count, chunks: [{chunk_id, content, score,
    methods, doc_id, source_url, title, heading_path, version, chunk_index,
    permissions, ...}]}. `chunks` is ordered best-first and may be empty.

    EDGE CASES & FAILURES: An empty `chunks` list with no error means nothing in
    the corpus matched. On failure a structured error is returned instead:
    errorCategory="validation" (unknown mode, k out of range) is not retryable;
    "transient" (search backend unreachable) is retryable; "business" (documents
    match but none are visible to caller_roles) is not retryable. Stack traces
    are never returned.
    """
    with tracer.start_as_current_span("mcp.retrieve_chunks") as span:
        span.set_attribute("mcp.tool", "retrieve_chunks")
        span.set_attribute("mcp.mode", mode)
        span.set_attribute("mcp.k", k)
        span.set_attribute("mcp.rerank", rerank)
        settings = get_settings()
        result = retrieve_chunks_impl(
            query,
            k=k,
            mode=mode,
            rerank=rerank,
            caller_roles=caller_roles,
            client=get_es_client(),
            embedder=get_embedder() if mode in ("vector", "hybrid") else None,
            reranker=get_reranker() if rerank else None,
            index=settings.elasticsearch_index,
            candidate_pool=settings.rerank_candidate_pool,
        )
        span.set_attribute("mcp.is_error", bool(result.get("isError", False)))
        if "count" in result:
            span.set_attribute("mcp.result_count", result["count"])
        return result


@mcp.tool()
@guard("answer_with_citations")
def answer_with_citations(
    query: str,
    k: int = 8,
    rerank: bool = False,
    caller_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Answer a question strictly grounded in the retrieved documentation.

    WHAT IT DOES: Runs the full pipeline — hybrid retrieval (optionally reranked)
    followed by grounded generation. Every claim in the answer cites the
    chunk_ids that support it; citations that do not map to a retrieved chunk are
    dropped. If the retrieved evidence does not support an answer, it returns the
    explicit insufficient-evidence response rather than guessing.

    WHEN TO USE: When you want a finished, citation-backed answer to a user
    question about Elasticsearch / AI-search documentation.

    WHEN NOT TO USE: When you only need raw chunks (use `retrieve_chunks`) or a
    document catalog (use `list_documents`). For multi-hop questions, you may
    prefer to `retrieve_chunks` across sub-queries yourself, then call this once
    with the focused final question.

    INPUTS:
      - query (str, required): the question to answer.
      - k (int, default 8, 1..100): chunks to retrieve as context.
      - rerank (bool, default false): cross-encoder rerank the context first.
      - caller_roles (list[str], default ["public"]): role-based visibility; the
        answer can only cite chunks these roles may see.

    OUTPUT: a structured GroundedAnswer — {query, answered (bool), insufficient
    (bool, always the opposite of answered), answer (str), claims: [{text,
    citations: [chunk_id]}], sources: [{chunk_id, source_url, title}],
    dropped_citations, model, usage}.

    EDGE CASES & FAILURES: Insufficient evidence is a NORMAL result, not an
    error: answered=false, insufficient=true, claims=[], sources=[]. Genuine
    failures return a structured error instead: "validation" (k out of range),
    "transient" (backend unreachable, retryable). Stack traces are never
    returned, and the tool never fabricates an ungrounded answer.
    """
    with tracer.start_as_current_span("mcp.answer_with_citations") as span:
        span.set_attribute("mcp.tool", "answer_with_citations")
        span.set_attribute("mcp.k", k)
        span.set_attribute("mcp.rerank", rerank)
        settings = get_settings()
        result = answer_with_citations_impl(
            query,
            k=k,
            rerank=rerank,
            caller_roles=caller_roles,
            client=get_es_client(),
            embedder=get_embedder(),
            provider=get_provider(),
            reranker=get_reranker() if rerank else None,
            index=settings.elasticsearch_index,
        )
        span.set_attribute("mcp.is_error", bool(result.get("isError", False)))
        if "answered" in result:
            span.set_attribute("mcp.answered", bool(result["answered"]))
        return result


@mcp.tool()
@guard("list_documents")
def list_documents(prefix: str | None = None, limit: int = 50) -> dict[str, Any]:
    """List the distinct documents available in the indexed corpus.

    WHAT IT DOES: Returns a catalog of distinct documents — (doc_id, title,
    source_url) tuples — aggregated from the rag_chunks index, ordered by doc_id.

    WHEN TO USE: During planning, to discover what documentation exists before
    deciding how to query, or to scope a search to a known document by reading
    its doc_id/title.

    WHEN NOT TO USE: To search document *contents* (use `retrieve_chunks`) or to
    answer a question (use `answer_with_citations`). This returns metadata only,
    no chunk text.

    INPUTS:
      - prefix (str, optional): if given, only documents whose doc_id starts with
        this prefix are returned.
      - limit (int, default 50, 1..1000): maximum number of documents to return.

    OUTPUT: {count, documents: [{doc_id, title, source_url}]}. `documents` may be
    empty if the corpus is empty or nothing matches the prefix.

    EDGE CASES & FAILURES: On failure a structured error is returned:
    "validation" (limit out of range, not retryable) or "transient" (backend
    unreachable, retryable). Stack traces are never returned.
    """
    with tracer.start_as_current_span("mcp.list_documents") as span:
        span.set_attribute("mcp.tool", "list_documents")
        span.set_attribute("mcp.limit", limit)
        settings = get_settings()
        result = list_documents_impl(
            prefix,
            limit=limit,
            client=get_es_client(),
            index=settings.elasticsearch_index,
        )
        span.set_attribute("mcp.is_error", bool(result.get("isError", False)))
        if "count" in result:
            span.set_attribute("mcp.result_count", result["count"])
        return result


def main() -> None:
    """Run the FastMCP server on the configured transport."""
    settings = get_settings()
    if settings.mcp_transport == "http":
        # Streamable-HTTP for the LangGraph client (Phase 2).
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
