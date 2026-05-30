"""Data models for the retrieval layer.

These are plain Pydantic models with no FastAPI coupling so a later MCP/LangGraph
layer can reuse the retrieval functions unchanged.
"""

from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """A single chunk returned by a retrieval method.

    Carries the chunk identity, a relevance ``score``, the chunk ``content``, the
    full chunk metadata, and a ``methods`` tag recording which retrieval
    method(s) surfaced it (e.g. ``["bm25"]``, ``["bm25", "vector"]``,
    ``["hybrid", "rerank"]``).
    """

    chunk_id: str
    score: float
    content: str
    methods: list[str] = Field(default_factory=list)

    # Full chunk metadata (mirrors the ES ``rag_chunks`` mapping).
    doc_id: str
    source_path: str
    source_url: str
    title: str
    heading_path: list[str] = Field(default_factory=list)
    version: str = ""
    last_updated: str = ""
    ingested_at: str = ""
    permissions: list[str] = Field(default_factory=lambda: ["public"])
    chunk_index: int = 0
