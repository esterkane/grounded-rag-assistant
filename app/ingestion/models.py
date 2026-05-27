"""Data models for the ingestion pipeline.

Plain dataclasses with no FastAPI / web coupling — ingestion is an offline
pipeline. ``Chunk`` is the unit indexed into Elasticsearch; its fields map 1:1 to
the ``rag_chunks`` mapping in ``indexer.py`` and are relied on by retrieval,
permission filtering, and citations downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Document:
    """A source document loaded from the corpus, before chunking."""

    doc_id: str
    source_path: str  # path relative to the corpus root — stable across machines
    title: str
    content: str
    kind: str  # "markdown" or "pdf"
    source_url: str = ""
    version: str = "unknown"
    last_updated: str | None = None  # ISO date (YYYY-MM-DD) or None


@dataclass
class Chunk:
    """A retrievable chunk. Fields mirror the rag_chunks ES mapping."""

    chunk_id: str
    doc_id: str
    content: str
    title: str
    heading_path: str  # e.g. "Hybrid search > RRF" ("" for non-markdown)
    source_url: str
    version: str
    last_updated: str | None
    ingested_at: str
    permissions: list[str] = field(default_factory=lambda: ["public"])
    embedding: list[float] | None = None

    def to_es_doc(self) -> dict:
        """Serialize to the Elasticsearch document body (keyed externally by chunk_id)."""
        doc = {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "content": self.content,
            "title": self.title,
            "heading_path": self.heading_path,
            "source_url": self.source_url,
            "version": self.version,
            "ingested_at": self.ingested_at,
            "permissions": self.permissions,
        }
        if self.last_updated:
            doc["last_updated"] = self.last_updated
        if self.embedding is not None:
            doc["embedding"] = self.embedding
        return doc
