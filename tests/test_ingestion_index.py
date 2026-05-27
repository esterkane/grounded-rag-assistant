"""Integration test: ingest a fixture doc and assert a chunk has a real vector.

Requires the running stack (Elasticsearch) and the embedding model. Skips cleanly
when neither is available, so `make test` still passes on a bare checkout.
Uses a dedicated throwaway index so it never touches the real corpus index.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.ingestion.chunking import chunk_document
from app.ingestion.models import Document

pytest.importorskip("sentence_transformers")
pytest.importorskip("elasticsearch")

TEST_INDEX = f"{settings.es_index}_pytest"

FIXTURE = Document(
    doc_id="fixture-doc",
    source_path="fixture/hybrid.md",
    title="Hybrid Search",
    content=(
        "# Hybrid Search\n\n"
        "Hybrid search combines BM25 keyword scoring with dense vector similarity.\n\n"
        "## RRF\n\nReciprocal rank fusion merges the two ranked lists into one.\n"
    ),
    kind="markdown",
    source_url="https://github.com/elastic/elasticsearch-labs/blob/main/hybrid.md",
    version="main",
    last_updated="2025-01-01",
)


@pytest.fixture(scope="module")
def es_index():
    from app.ingestion.embedder import Embedder
    from app.ingestion.indexer import bulk_upsert, create_index, get_client

    client = get_client()
    try:
        if not client.ping():
            pytest.skip("Elasticsearch not reachable")
    except Exception:  # noqa: BLE001
        pytest.skip("Elasticsearch not reachable")

    embedder = Embedder()
    chunks = chunk_document(FIXTURE)
    for chunk, vector in zip(chunks, embedder.encode([c.content for c in chunks]), strict=True):
        chunk.embedding = vector

    if client.indices.exists(index=TEST_INDEX):
        client.indices.delete(index=TEST_INDEX)
    create_index(client, TEST_INDEX, dims=embedder.dim())
    bulk_upsert(client, TEST_INDEX, chunks)

    yield client, chunks, embedder.dim()

    client.indices.delete(index=TEST_INDEX, ignore_unavailable=True)


def test_known_chunk_exists_with_nonempty_vector(es_index):
    client, chunks, dims = es_index
    known = chunks[0]

    # ES 9.x keeps dense_vector out of _source by default and serves it via the
    # `fields` API, so we request the vector explicitly.
    res = client.search(
        index=TEST_INDEX,
        query={"term": {"chunk_id": known.chunk_id}},
        fields=["embedding"],
        size=1,
    )
    hits = res["hits"]["hits"]
    assert len(hits) == 1, "known chunk not found in index"
    hit = hits[0]

    source = hit["_source"]
    assert source["chunk_id"] == known.chunk_id
    assert source["permissions"] == ["public"]
    assert source["source_url"].startswith("https://")

    vector = hit["fields"]["embedding"]
    assert isinstance(vector, list)
    assert len(vector) == dims
    assert any(abs(v) > 0 for v in vector)  # non-empty / non-zero


def test_reingest_is_idempotent(es_index):
    from app.ingestion.indexer import bulk_upsert

    client, chunks, _ = es_index
    before = client.count(index=TEST_INDEX)["count"]
    bulk_upsert(client, TEST_INDEX, chunks)  # re-upsert identical chunks
    after = client.count(index=TEST_INDEX)["count"]
    assert before == after == len(chunks)
