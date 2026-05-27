"""Integration tests for POST /search.

Require the running stack with a populated ``rag_chunks`` index and the embedding
model. Skip cleanly otherwise so `make test` passes on a bare checkout.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("elasticsearch")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402

VALID_METHODS = {"bm25", "vector", "hybrid"}
PERM_CHUNK_ID = "perm_test_chunk_zqx"
PERM_TOKEN = "zqxpermtoken"


@pytest.fixture(scope="module")
def client():
    from app.ingestion.indexer import get_client

    es = get_client()
    try:
        if not es.ping() or es.count(index=settings.es_index)["count"] == 0:
            pytest.skip("rag_chunks not populated — run `make corpus && make ingest`")
    except Exception:  # noqa: BLE001
        pytest.skip("Elasticsearch not reachable")
    return TestClient(app)


def test_search_returns_results_with_metadata_and_methods(client):
    resp = client.post(
        "/search", json={"query": "hybrid search combining bm25 and vectors", "k": 5}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] > 0
    for r in data["results"]:
        assert r["chunk_id"]
        assert r["content"]
        assert r["source_url"].startswith("http")
        assert r["methods"], "result is missing method tags"
        assert set(r["methods"]) <= VALID_METHODS


def test_permissions_exclude_unauthorized_chunks(client):
    from app.ingestion.embedder import Embedder
    from app.ingestion.indexer import get_client

    es = get_client()
    content = f"{PERM_TOKEN} specialadminonly note about {PERM_TOKEN}"
    es.index(
        index=settings.es_index,
        id=PERM_CHUNK_ID,
        document={
            "chunk_id": PERM_CHUNK_ID,
            "doc_id": "perm_doc",
            "content": content,
            "title": "Admin only",
            "heading_path": "",
            "source_url": "https://example.com/admin",
            "version": "main",
            "ingested_at": "2025-01-01T00:00:00Z",
            "permissions": ["admin"],
            "embedding": Embedder().encode([content])[0],
        },
        refresh=True,
    )
    try:
        public = client.post(
            "/search", json={"query": PERM_TOKEN, "k": 10, "caller_roles": ["public"]}
        ).json()
        assert PERM_CHUNK_ID not in {r["chunk_id"] for r in public["results"]}

        admin = client.post(
            "/search", json={"query": PERM_TOKEN, "k": 10, "caller_roles": ["admin"]}
        ).json()
        assert PERM_CHUNK_ID in {r["chunk_id"] for r in admin["results"]}
    finally:
        es.delete(index=settings.es_index, id=PERM_CHUNK_ID, refresh=True)


def test_rerank_toggle_runs_without_error(client):
    body = {"query": "vector similarity search", "k": 5}
    no_rerank = client.post("/search", json={**body, "rerank": False})
    assert no_rerank.status_code == 200 and no_rerank.json()["count"] > 0

    reranked = client.post("/search", json={**body, "rerank": True})
    if reranked.status_code == 502:
        pytest.skip("cross-encoder reranker unavailable")
    assert reranked.status_code == 200 and reranked.json()["count"] > 0
