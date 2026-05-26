from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceDocument:
    source_path: str
    content: str
    title: str
    source_url: str
    version: str
    last_updated: str
    permissions: list[str] = field(default_factory=lambda: ["public"])


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    doc_id: str
    source_path: str
    source_url: str
    title: str
    heading_path: list[str]
    version: str
    last_updated: str
    ingested_at: str
    permissions: list[str]
    chunk_index: int
    content: str
    embedding: list[float] | None = None
