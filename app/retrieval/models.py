"""Retrieval result model.

Pydantic (not FastAPI) so it is importable from the pure retrieval layer and a
later MCP/LangGraph layer, while still serializing cleanly when the API returns it.
Carries the chunk content, all chunk metadata, a score, and which retrieval
method(s) surfaced it.
"""

from __future__ import annotations

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    chunk_id: str
    score: float
    content: str
    title: str
    heading_path: str
    source_url: str
    version: str
    last_updated: str | None
    doc_id: str
    permissions: list[str]
    methods: list[str]  # subset of {"bm25", "vector", "hybrid"}

    @classmethod
    def from_hit(
        cls, hit: dict, methods: list[str], score: float | None = None
    ) -> RetrievalResult:
        src = hit.get("_source", {})
        return cls(
            chunk_id=src.get("chunk_id", hit.get("_id", "")),
            score=float(hit["_score"]) if score is None else float(score),
            content=src.get("content", ""),
            title=src.get("title", ""),
            heading_path=src.get("heading_path", ""),
            source_url=src.get("source_url", ""),
            version=src.get("version", "unknown"),
            last_updated=src.get("last_updated"),
            doc_id=src.get("doc_id", ""),
            permissions=src.get("permissions", ["public"]),
            methods=methods,
        )
