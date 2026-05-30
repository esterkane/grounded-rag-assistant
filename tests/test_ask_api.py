"""Integration tests for POST /ask.

Requires Elasticsearch (real Phase-2 retrieval). The LLM provider is overridden
with a deterministic fake so the test does not depend on a live model — the fake
reads the prompt and cites a real retrieved chunk, exercising the full
retrieval -> prompt -> parse -> citation-validation pipeline.
"""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_embedder, get_es_client, get_provider
from app.config import get_settings
from app.generation.providers.base import LLMProvider
from app.ingestion.index import count_chunks, ensure_index
from app.ingestion.run import ingest_path
from app.main import create_app


class FirstChunkCitingProvider(LLMProvider):
    """Cites the first chunk_id found in the prompt — simulating a grounded model."""

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        user = next(m["content"] for m in messages if m["role"] == "user")
        match = re.search(r"chunk_id=(\S+)", user)
        chunk_id = match.group(1) if match else "none"
        return json.dumps(
            {
                "answered": True,
                "answer": "Grounded answer from context.",
                "claims": [{"text": "A grounded claim.", "citations": [chunk_id]}],
            }
        )


class InsufficientProvider(LLMProvider):
    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        return json.dumps(
            {"answered": False, "answer": "Not enough evidence.", "claims": []}
        )


@pytest.fixture(scope="module")
def populated_index() -> None:
    settings = get_settings()
    es = get_es_client()
    ensure_index(es, settings.elasticsearch_index, get_embedder().dimensions)
    if count_chunks(es, settings.elasticsearch_index) == 0:
        ingest_path(Path("data/sample_corpus"))
        es.indices.refresh(index=settings.elasticsearch_index)


def make_client(provider: LLMProvider) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_provider] = lambda: provider
    return TestClient(app)


def test_ask_returns_cited_answer_mapping_to_real_chunks(populated_index: None) -> None:
    client = make_client(FirstChunkCitingProvider())

    response = client.post("/ask", json={"query": "How does vector search work?", "k": 4})

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is True
    assert body["insufficient"] is False

    cited = {cid for claim in body["claims"] for cid in claim["citations"]}
    assert cited
    # Every citation maps to a chunk that retrieval actually returned (it is in sources).
    source_ids = {s["chunk_id"] for s in body["sources"]}
    assert cited <= source_ids
    assert body["dropped_citations"] == []


def test_ask_offtopic_takes_insufficient_path(populated_index: None) -> None:
    client = make_client(InsufficientProvider())

    response = client.post(
        "/ask", json={"query": "What is the best recipe for lasagna?", "k": 4}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answered"] is False
    assert body["insufficient"] is True
    assert body["claims"] == []
