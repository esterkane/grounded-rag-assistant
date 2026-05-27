"""Chunking and stable chunk identity.

Pure functions, no heavy dependencies (no sentence-transformers / elasticsearch),
so these are fast to unit-test without the stack.

- Markdown is **header-aware**: split on ATX headings, keep the heading path, then
  size-split any oversized section so the heading path is preserved.
- PDF (and any plain text) is **size-based with overlap**.
- ``chunk_id`` is a deterministic hash of (source_path, heading_path, chunk_index),
  so re-ingesting the same corpus overwrites rather than duplicates.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.ingestion.models import Chunk, Document

# Token budget per chunk. We approximate tokens by whitespace-delimited words,
# which is good enough for sizing; the embedding model does its own tokenization.
TARGET_TOKENS = 600
OVERLAP_TOKENS = 100

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def estimate_tokens(text: str) -> int:
    """Rough token count via word count. Deterministic and dependency-free."""
    return len(text.split())


def make_doc_id(source_path: str) -> str:
    return hashlib.sha1(source_path.encode("utf-8")).hexdigest()[:16]


def make_chunk_id(source_path: str, heading_path: str, chunk_index: int) -> str:
    """Deterministic id from (source_path, heading_path, chunk_index)."""
    key = f"{source_path}\x00{heading_path}\x00{chunk_index}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class _Section:
    heading_path: list[str]
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def split_markdown_sections(content: str) -> list[_Section]:
    """Split markdown into sections at each heading, tracking the heading path.

    Content before the first heading is kept as a section with an empty path.
    """
    sections: list[_Section] = []
    heading_stack: dict[int, str] = {}
    current = _Section(heading_path=[], lines=[])

    for line in content.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            # Flush the section accumulated so far if it has content.
            if current.text:
                sections.append(current)
            level = len(m.group(1))
            title = m.group(2).strip()
            # Drop any deeper headings, then set this level.
            heading_stack[level] = title
            for deeper in [lv for lv in heading_stack if lv > level]:
                del heading_stack[deeper]
            path = [heading_stack[lv] for lv in sorted(heading_stack)]
            current = _Section(heading_path=path, lines=[])
        else:
            current.lines.append(line)

    if current.text:
        sections.append(current)
    return sections


def chunk_text_by_size(
    text: str, target_tokens: int = TARGET_TOKENS, overlap_tokens: int = OVERLAP_TOKENS
) -> list[str]:
    """Split text into ~target_tokens windows with overlap_tokens of overlap."""
    words = text.split()
    if not words:
        return []
    if len(words) <= target_tokens:
        return [" ".join(words)]

    step = max(1, target_tokens - overlap_tokens)
    chunks: list[str] = []
    start = 0
    while start < len(words):
        window = words[start : start + target_tokens]
        chunks.append(" ".join(window))
        if start + target_tokens >= len(words):
            break
        start += step
    return chunks


def chunk_document(
    doc: Document, target_tokens: int = TARGET_TOKENS, overlap_tokens: int = OVERLAP_TOKENS
) -> list[Chunk]:
    """Produce chunks for a document, dispatching on its kind."""
    from datetime import UTC, datetime

    ingested_at = datetime.now(UTC).isoformat()

    # (heading_path_str, text) pairs.
    pieces: list[tuple[str, str]] = []
    if doc.kind == "markdown":
        for section in split_markdown_sections(doc.content):
            heading_path = " > ".join(section.heading_path)
            for piece in chunk_text_by_size(section.text, target_tokens, overlap_tokens):
                pieces.append((heading_path, piece))
    else:  # pdf / plain text
        for piece in chunk_text_by_size(doc.content, target_tokens, overlap_tokens):
            pieces.append(("", piece))

    chunks: list[Chunk] = []
    for index, (heading_path, text) in enumerate(pieces):
        chunk_id = make_chunk_id(doc.source_path, heading_path, index)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                content=text,
                title=doc.title,
                heading_path=heading_path,
                source_url=doc.source_url,
                version=doc.version,
                last_updated=doc.last_updated,
                ingested_at=ingested_at,
            )
        )
    return chunks
