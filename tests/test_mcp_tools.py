"""Unit tests for the MCP tool handlers.

These call the underlying handlers directly with a fake Elasticsearch client and
a fake LLM provider — no live services. They assert input validation, the
structured-error shape (category / retryable / no stack trace), and that
insufficient evidence is passed through as a normal result rather than an error.
"""

import json

import pytest
from elasticsearch import ConnectionError as ESConnectionError

from app.generation.providers.base import LLMProvider
from app.mcp.tools import (
    answer_with_citations_impl,
    list_documents_impl,
    retrieve_chunks_impl,
)

# --- fakes ----------------------------------------------------------------


class FakeES:
    """Minimal Elasticsearch stand-in for the handlers' .search / .count calls."""

    def __init__(self, *, hits=None, count=0, agg_buckets=None, docs=None, search_error=None):
        self._hits = hits or []
        self._count = count
        self._agg_buckets = agg_buckets
        self._docs = docs  # for list_documents: honor permission/prefix filters
        self._search_error = search_error
        self.search_calls = []
        self.count_calls = []

    @staticmethod
    def _parse_filters(query):
        allowed = None
        prefix = None
        for clause in (query or {}).get("bool", {}).get("filter", []):
            if "terms" in clause and "permissions" in clause["terms"]:
                allowed = set(clause["terms"]["permissions"])
            if "prefix" in clause and "doc_id" in clause["prefix"]:
                prefix = clause["prefix"]["doc_id"]
        return allowed, prefix

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        if self._search_error is not None:
            raise self._search_error
        if "aggs" in kwargs:
            if self._docs is not None:
                allowed, prefix = self._parse_filters(kwargs.get("query"))
                buckets = []
                for d in self._docs:
                    perms = set(d.get("permissions", ["public"]))
                    if prefix and not d["doc_id"].startswith(prefix):
                        continue
                    if allowed is not None and not (perms & allowed):
                        continue
                    src = {k: d.get(k, "") for k in ("doc_id", "title", "source_url")}
                    hits = {"hits": {"hits": [{"_source": src}]}}
                    buckets.append({"key": d["doc_id"], "top": hits})
                return {"aggregations": {"docs": {"buckets": buckets}}}
            if self._agg_buckets is not None:
                return {"aggregations": {"docs": {"buckets": self._agg_buckets}}}
        return {"hits": {"hits": self._hits}}

    def count(self, **kwargs):
        self.count_calls.append(kwargs)
        return {"count": self._count}

    def info(self):
        # Lets hybrid_search's native-RRF probe run; .search ignores the body.
        return {"cluster_name": "fake", "version": {"number": "9.4.1"}}


class FakeEmbedder:
    dimensions = 4

    def embed(self, texts, batch_size=32):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class ScriptedProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self._response = response

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        return self._response


def _hit(chunk_id="c1", **source):
    base = {
        "chunk_id": chunk_id,
        "content": "Vector search uses dense embeddings.",
        "doc_id": "doc-1",
        "source_path": "docs/vector.md",
        "source_url": "https://example/vector",
        "title": "Vector search",
        "permissions": ["public"],
        "chunk_index": 0,
    }
    base.update(source)
    return {"_score": 1.5, "_source": base}


# --- retrieve_chunks ------------------------------------------------------


def test_retrieve_unknown_mode_is_validation_error():
    result = retrieve_chunks_impl("q", mode="fuzzy", client=FakeES(), index="rag_chunks")
    assert result["isError"] is True
    assert result["errorCategory"] == "validation"
    assert result["isRetryable"] is False


def test_retrieve_bad_k_is_validation_error():
    result = retrieve_chunks_impl("q", k=0, mode="bm25", client=FakeES(), index="rag_chunks")
    assert result["errorCategory"] == "validation"
    assert result["isRetryable"] is False


def test_retrieve_empty_query_is_validation_error():
    result = retrieve_chunks_impl("   ", mode="bm25", client=FakeES(), index="rag_chunks")
    assert result["errorCategory"] == "validation"


def test_retrieve_bm25_success_returns_chunks():
    es = FakeES(hits=[_hit("c1"), _hit("c2")])
    result = retrieve_chunks_impl("vector search", mode="bm25", k=8, client=es, index="rag_chunks")
    assert result.get("isError", False) is False
    assert result["count"] == 2
    assert result["mode"] == "bm25"
    assert result["chunks"][0]["chunk_id"] == "c1"
    assert result["chunks"][0]["methods"] == ["bm25"]


def test_retrieve_transient_error_when_backend_unreachable():
    es = FakeES(search_error=ESConnectionError("es down"))
    result = retrieve_chunks_impl("q", mode="bm25", client=es, index="rag_chunks")
    assert result["errorCategory"] == "transient"
    assert result["isRetryable"] is True
    # No stack trace / internal detail leaks into the message.
    assert "Traceback" not in result["message"]
    assert "es down" not in result["message"]


def test_retrieve_business_error_when_matches_hidden_from_roles():
    # Filtered search returns nothing, but the corpus has matches (count > 0):
    # documents exist but none are visible to the caller's roles.
    es = FakeES(hits=[], count=3)
    result = retrieve_chunks_impl(
        "secret", mode="bm25", caller_roles=["public"], client=es, index="rag_chunks"
    )
    assert result["errorCategory"] == "business"
    assert result["isRetryable"] is False


def test_retrieve_empty_is_not_error_when_corpus_has_no_match():
    es = FakeES(hits=[], count=0)
    result = retrieve_chunks_impl("nothing", mode="bm25", client=es, index="rag_chunks")
    assert result.get("isError", False) is False
    assert result["count"] == 0
    assert result["chunks"] == []


# --- answer_with_citations ------------------------------------------------


def test_answer_bad_k_is_validation_error():
    result = answer_with_citations_impl(
        "q",
        k=999,
        client=FakeES(),
        embedder=FakeEmbedder(),
        provider=ScriptedProvider("{}"),
        index="rag_chunks",
    )
    assert result["errorCategory"] == "validation"


def test_answer_insufficient_when_no_chunks_is_not_error():
    # Empty retrieval -> answerer returns the insufficient-evidence response and
    # never calls the provider; the handler passes it through as a NORMAL result.
    es = FakeES(hits=[])
    result = answer_with_citations_impl(
        "off-corpus question",
        k=4,
        client=es,
        embedder=FakeEmbedder(),
        provider=ScriptedProvider(json.dumps({"answered": False, "answer": "n/a", "claims": []})),
        index="rag_chunks",
    )
    assert result.get("isError", False) is False
    assert result["answered"] is False
    assert result["insufficient"] is True
    assert result["claims"] == []


def test_answer_transient_error_when_backend_unreachable():
    es = FakeES(search_error=ESConnectionError("es down"))
    result = answer_with_citations_impl(
        "q",
        k=4,
        client=es,
        embedder=FakeEmbedder(),
        provider=ScriptedProvider("{}"),
        index="rag_chunks",
    )
    assert result["errorCategory"] == "transient"
    assert result["isRetryable"] is True


# --- list_documents -------------------------------------------------------


def test_list_documents_bad_limit_is_validation_error():
    result = list_documents_impl(limit=0, client=FakeES(), index="rag_chunks")
    assert result["errorCategory"] == "validation"


def test_list_documents_success_shape():
    def _bucket(doc_id, title, url):
        src = {"doc_id": doc_id, "title": title, "source_url": url}
        return {"key": doc_id, "top": {"hits": {"hits": [{"_source": src}]}}}

    buckets = [_bucket("doc-1", "T1", "u1"), _bucket("doc-2", "T2", "u2")]
    es = FakeES(agg_buckets=buckets)
    result = list_documents_impl(client=es, index="rag_chunks")
    assert result.get("isError", False) is False
    assert result["count"] == 2
    assert result["documents"][0] == {"doc_id": "doc-1", "title": "T1", "source_url": "u1"}


# --- rerank / prefix input validation -------------------------------------


def test_retrieve_non_boolean_rerank_is_validation_error():
    result = retrieve_chunks_impl(
        "q", mode="bm25", rerank="yes", client=FakeES(), index="rag_chunks"
    )
    assert result["errorCategory"] == "validation"


def test_answer_non_boolean_rerank_is_validation_error():
    result = answer_with_citations_impl(
        "q",
        rerank=1,
        client=FakeES(),
        embedder=FakeEmbedder(),
        provider=ScriptedProvider("{}"),
        index="rag_chunks",
    )
    assert result["errorCategory"] == "validation"


def test_list_documents_non_string_prefix_is_validation_error():
    result = list_documents_impl(prefix=123, client=FakeES(agg_buckets=[]), index="rag_chunks")
    assert result["errorCategory"] == "validation"


def test_list_documents_whitespace_prefix_treated_as_none():
    es = FakeES(agg_buckets=[])
    result = list_documents_impl(prefix="   ", client=es, index="rag_chunks")
    assert result.get("isError", False) is False
    # Whitespace-only prefix is dropped -> the query carries no prefix clause.
    filters = es.search_calls[-1]["query"]["bool"]["filter"]
    assert not any("prefix" in clause for clause in filters)


def test_list_documents_hides_docs_not_visible_to_caller_roles():
    docs = [
        {"doc_id": "pub", "title": "Public", "source_url": "u1", "permissions": ["public"]},
        {"doc_id": "sec", "title": "Secret", "source_url": "u2", "permissions": ["admin"]},
    ]
    es = FakeES(docs=docs)

    public = list_documents_impl(caller_roles=["public"], client=es, index="rag_chunks")
    assert {d["doc_id"] for d in public["documents"]} == {"pub"}

    # "admin" effective roles include "public", so the admin sees both.
    admin = list_documents_impl(caller_roles=["admin"], client=es, index="rag_chunks")
    assert {d["doc_id"] for d in admin["documents"]} == {"pub", "sec"}


@pytest.mark.parametrize("payload", ["isError", "errorCategory", "isRetryable", "message"])
def test_error_payload_has_required_keys(payload):
    result = retrieve_chunks_impl("q", mode="bad", client=FakeES(), index="rag_chunks")
    assert payload in result


# --- @mcp.tool() wrapper guard --------------------------------------------
# Resource acquisition (get_es_client/get_embedder/get_provider) and span setup
# happen in the registered wrapper, outside the guarded _impl. The wrapper is
# guarded too, so a failure there must still return a structured error, not raise
# a stack trace into the MCP response.


def _boom(*args, **kwargs):
    raise RuntimeError("bad ES URL / resource construction failed")


def test_retrieve_chunks_wrapper_guards_resource_errors(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server, "get_es_client", _boom)
    result = server.retrieve_chunks("q", mode="bm25")
    assert result["isError"] is True
    assert "Traceback" not in result["message"]
    assert "bad ES URL" not in result["message"]


def test_answer_with_citations_wrapper_guards_resource_errors(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server, "get_es_client", _boom)
    result = server.answer_with_citations("q")
    assert result["isError"] is True
    assert "Traceback" not in result["message"]


def test_list_documents_wrapper_guards_resource_errors(monkeypatch):
    import app.mcp.server as server

    monkeypatch.setattr(server, "get_es_client", _boom)
    result = server.list_documents()
    assert result["isError"] is True
    assert "Traceback" not in result["message"]
