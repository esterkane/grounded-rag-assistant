"""Integration tests for POST /search.

Requires the local stack (Elasticsearch). These tests ingest the sample corpus
if the index is empty and index one restricted chunk to exercise permission
filtering.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_embedder, get_es_client
from app.config import get_settings
from app.ingestion.index import count_chunks, ensure_index
from app.ingestion.run import ingest_path
from app.main import create_app

PRIVATE_CHUNK_ID = "test-private-chunk-zzz"
PRIVATE_MARKER = "Zphsixendoc confidential rollout marker"


@pytest.fixture(scope="module")
def client() -> TestClient:
    settings = get_settings()
    es = get_es_client()
    embedder = get_embedder()

    ensure_index(es, settings.elasticsearch_index, embedder.dimensions)
    if count_chunks(es, settings.elasticsearch_index) == 0:
        ingest_path(Path("data/sample_corpus"))

    # Index a restricted chunk only callers with the "secret" role may see.
    es.index(
        index=settings.elasticsearch_index,
        id=PRIVATE_CHUNK_ID,
        document={
            "chunk_id": PRIVATE_CHUNK_ID,
            "doc_id": "test-private-doc",
            "source_path": "private/secret.md",
            "source_url": "https://internal.example.com/secret",
            "title": "Confidential Rollout Notes",
            "heading_path": ["Confidential"],
            "version": "1.0",
            "last_updated": "2026-01-01",
            "ingested_at": datetime.now(UTC).isoformat(),
            "permissions": ["secret"],
            "chunk_index": 0,
            "content": f"{PRIVATE_MARKER}. Internal-only deployment details.",
            "embedding": embedder.embed([PRIVATE_MARKER])[0],
        },
    )
    es.indices.refresh(index=settings.elasticsearch_index)
    return TestClient(create_app())


def test_search_returns_relevant_chunks_with_metadata_and_methods(client: TestClient) -> None:
    response = client.post("/search", json={"query": "vector search in Elasticsearch", "k": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["count"] > 0
    assert len(body["results"]) <= 5

    top = body["results"][0]
    # Metadata is present.
    for field in ("chunk_id", "source_url", "title", "content", "heading_path", "permissions"):
        assert field in top
    # Method tags identify how the chunk was retrieved.
    assert top["methods"]
    assert "hybrid" in top["methods"]


def test_rerank_toggle_runs_and_tags_results(client: TestClient) -> None:
    base = client.post("/search", json={"query": "how does hybrid retrieval work", "k": 5})
    reranked = client.post(
        "/search", json={"query": "how does hybrid retrieval work", "k": 5, "rerank": True}
    )

    assert base.status_code == 200
    assert reranked.status_code == 200
    assert base.json()["reranked"] is False
    assert reranked.json()["reranked"] is True

    rr_results = reranked.json()["results"]
    assert rr_results
    # Reranking changes scores/ordering but not the schema; results carry the tag.
    assert all("rerank" in r["methods"] for r in rr_results)


def test_permissions_exclude_chunks_caller_roles_do_not_cover(client: TestClient) -> None:
    payload = {"query": PRIVATE_MARKER, "k": 10}

    without_role = client.post("/search", json=payload)
    assert without_role.status_code == 200
    ids = [r["chunk_id"] for r in without_role.json()["results"]]
    assert PRIVATE_CHUNK_ID not in ids

    with_role = client.post("/search", json={**payload, "caller_roles": ["secret"]})
    assert with_role.status_code == 200
    ids_with_role = [r["chunk_id"] for r in with_role.json()["results"]]
    assert PRIVATE_CHUNK_ID in ids_with_role
