"""Integration tests for POST /ask.

Use real phase-2 retrieval against the populated index, but a deterministic
fake provider (no real LLM key needed) so we can assert that citations map to
actually-retrieved chunks and that the insufficient path is wired through.
"""

from __future__ import annotations

import json
import re

import pytest

pytest.importorskip("sentence_transformers")
pytest.importorskip("elasticsearch")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.generation.providers.base import LLMProvider  # noqa: E402
from app.main import app  # noqa: E402


class _GroundedFake(LLMProvider):
    """Cites the first real chunk_id it sees in the prompt context."""

    name = "grounded-fake"

    def generate(self, messages, **opts):
        ctx = "\n".join(m["content"] for m in messages)
        ids = re.findall(r"chunk_id=(\S+)", ctx)
        cid = ids[0]
        return json.dumps(
            {
                "answer": "Grounded answer.",
                "claims": [{"text": "A grounded claim.", "citations": [cid]}],
                "insufficient": False,
            }
        )


class _InsufficientFake(LLMProvider):
    name = "insufficient-fake"

    def generate(self, messages, **opts):
        return json.dumps({"answer": "No evidence.", "claims": [], "insufficient": True})


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


def test_ask_returns_cited_answer_mapping_to_real_chunks(client, monkeypatch):
    monkeypatch.setattr("app.generation.answerer.get_provider", lambda *a, **k: _GroundedFake())
    resp = client.post("/ask", json={"query": "what is hybrid search?", "k": 5})
    assert resp.status_code == 200
    answer = resp.json()["answer"]

    assert answer["answered"] is True and answer["insufficient"] is False
    cited = {c for claim in answer["claims"] for c in claim["citations"]}
    assert cited, "expected at least one citation"
    # Every citation must map to a source that was actually retrieved.
    source_ids = {s["chunk_id"] for s in answer["sources"]}
    assert cited <= source_ids


def test_ask_insufficient_path(client, monkeypatch):
    monkeypatch.setattr(
        "app.generation.answerer.get_provider", lambda *a, **k: _InsufficientFake()
    )
    resp = client.post("/ask", json={"query": "unrelated off corpus question", "k": 5})
    assert resp.status_code == 200
    answer = resp.json()["answer"]
    assert answer["answered"] is False
    assert answer["insufficient"] is True
    assert answer["claims"] == []
