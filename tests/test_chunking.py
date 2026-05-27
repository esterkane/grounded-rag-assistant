"""Unit tests for chunking and stable chunk identity (no ES, no model)."""

from app.ingestion.chunking import (
    chunk_document,
    chunk_text_by_size,
    make_chunk_id,
    split_markdown_sections,
)
from app.ingestion.models import Document

MARKDOWN = """# Hybrid Search

Intro paragraph about combining signals.

## RRF

Reciprocal rank fusion merges result lists.

### Tuning

The rank constant k controls weighting.
"""


def _doc(content: str = MARKDOWN) -> Document:
    return Document(
        doc_id="d1",
        source_path="elasticsearch-labs/hybrid.md",
        title="Hybrid Search",
        content=content,
        kind="markdown",
        source_url="https://example/blob/main/hybrid.md",
        version="main",
        last_updated="2025-01-01",
    )


def test_chunk_id_is_deterministic_and_index_sensitive():
    a = make_chunk_id("p", "A > B", 0)
    assert a == make_chunk_id("p", "A > B", 0)
    assert a != make_chunk_id("p", "A > B", 1)
    assert a != make_chunk_id("p", "A", 0)


def test_header_aware_keeps_heading_path():
    sections = split_markdown_sections(MARKDOWN)
    paths = [" > ".join(s.heading_path) for s in sections]
    assert "Hybrid Search" in paths
    assert "Hybrid Search > RRF" in paths
    assert "Hybrid Search > RRF > Tuning" in paths


def test_chunk_document_is_idempotent():
    ids_first = [c.chunk_id for c in chunk_document(_doc())]
    ids_second = [c.chunk_id for c in chunk_document(_doc())]
    assert ids_first == ids_second
    assert len(ids_first) == len(set(ids_first))  # no duplicate ids


def test_chunks_carry_required_metadata():
    chunk = chunk_document(_doc())[0]
    assert chunk.permissions == ["public"]
    assert chunk.source_url.startswith("https://")
    assert chunk.version == "main"
    assert chunk.doc_id == "d1"


def test_size_based_chunking_overlaps():
    text = " ".join(f"w{i}" for i in range(1500))
    chunks = chunk_text_by_size(text, target_tokens=600, overlap_tokens=100)
    assert len(chunks) >= 3
    # Consecutive windows overlap: tail of one reappears at head of the next.
    first_tail = chunks[0].split()[-100:]
    second_head = chunks[1].split()[:100]
    assert first_tail == second_head
