from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256

from app.ingestion.models import DocumentChunk, SourceDocument

MIN_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100


def chunk_document(document: SourceDocument, ingested_at: str | None = None) -> list[DocumentChunk]:
    timestamp = ingested_at or datetime.now(UTC).isoformat()
    if document.source_path.lower().endswith(".md"):
        return chunk_markdown(document, timestamp)
    return chunk_size_based(document, timestamp, heading_path=[])


def chunk_markdown(document: SourceDocument, ingested_at: str) -> list[DocumentChunk]:
    sections = split_markdown_sections(document.content)
    chunks: list[DocumentChunk] = []
    chunk_index = 0
    for heading_path, section_text in sections:
        for text in split_with_overlap(section_text):
            chunks.append(build_chunk(document, text, heading_path, chunk_index, ingested_at))
            chunk_index += 1
    return chunks


def chunk_size_based(
    document: SourceDocument,
    ingested_at: str,
    heading_path: list[str],
) -> list[DocumentChunk]:
    chunks = []
    for chunk_index, text in enumerate(split_with_overlap(document.content)):
        chunks.append(build_chunk(document, text, heading_path, chunk_index, ingested_at))
    return chunks


def split_markdown_sections(content: str) -> list[tuple[list[str], str]]:
    sections: list[tuple[list[str], list[str]]] = []
    heading_stack: list[str] = []
    current_lines: list[str] = []
    current_path: list[str] = []

    for line in content.splitlines():
        heading = parse_heading(line)
        if heading:
            if current_lines:
                sections.append((current_path, current_lines))
            level, title = heading
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)
            current_path = heading_stack.copy()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_path, current_lines))

    normalized = [(path, "\n".join(lines).strip()) for path, lines in sections]
    return [(path, text) for path, text in normalized if text]


def parse_heading(line: str) -> tuple[int, str] | None:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return None
    marker, _, title = stripped.partition(" ")
    if not title or any(char != "#" for char in marker):
        return None
    level = min(len(marker), 6)
    return level, title.strip()


def split_with_overlap(text: str) -> Iterable[str]:
    tokens = text.split()
    if len(tokens) <= MAX_CHUNK_TOKENS:
        yield text.strip()
        return

    start = 0
    while start < len(tokens):
        end = min(start + MAX_CHUNK_TOKENS, len(tokens))
        if end < len(tokens) and end - start < MIN_CHUNK_TOKENS:
            end = min(start + MIN_CHUNK_TOKENS, len(tokens))
        yield " ".join(tokens[start:end]).strip()
        if end == len(tokens):
            break
        start = max(end - OVERLAP_TOKENS, start + 1)


def build_chunk(
    document: SourceDocument,
    content: str,
    heading_path: list[str],
    chunk_index: int,
    ingested_at: str,
) -> DocumentChunk:
    identity = f"{document.source_path}|{' > '.join(heading_path)}|{chunk_index}"
    chunk_id = sha256(identity.encode("utf-8")).hexdigest()
    doc_id = sha256(document.source_path.encode("utf-8")).hexdigest()
    return DocumentChunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        source_path=document.source_path,
        source_url=document.source_url,
        title=document.title,
        heading_path=heading_path,
        version=document.version,
        last_updated=document.last_updated,
        ingested_at=ingested_at,
        permissions=document.permissions,
        chunk_index=chunk_index,
        content=content,
    )
