"""Shared, lazily-constructed singletons for the API layer.

The Elasticsearch client, embedder, and reranker are expensive to build (the
embedder and reranker load local models), so they are cached for the process
lifetime. These live in the API layer; the retrieval functions themselves stay
dependency-injected and pure.
"""

from functools import lru_cache

from elasticsearch import Elasticsearch

from app.config import Settings, get_settings
from app.ingestion.embedder import SentenceTransformersEmbedder
from app.retrieval.reranker import CrossEncoderReranker


@lru_cache
def get_es_client() -> Elasticsearch:
    settings = get_settings()
    return Elasticsearch(settings.elasticsearch_url, request_timeout=30)


@lru_cache
def get_embedder() -> SentenceTransformersEmbedder:
    settings = get_settings()
    return SentenceTransformersEmbedder(settings.embedding_model)


@lru_cache
def get_reranker() -> CrossEncoderReranker:
    settings: Settings = get_settings()
    return CrossEncoderReranker(settings.rerank_model)
