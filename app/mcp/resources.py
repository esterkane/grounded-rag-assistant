"""Lazily-constructed resource singletons for the MCP layer.

The MCP server is a sibling front-end to the FastAPI app: both adapt the same
Project 1 core (retrieval, generation, embeddings) to a transport. These
accessors mirror ``app/api/dependencies.py`` but import only from the core
packages, so the MCP layer never depends on ``app/api`` (or FastAPI).

The Elasticsearch client, embedder, and reranker are expensive to build (the
embedder and reranker load local models), so each is cached for the process
lifetime and built on first use — a tool that never needs an embedder (e.g.
``list_documents`` or a bm25 ``retrieve_chunks``) never pays to load one.
"""

from functools import lru_cache

from elasticsearch import Elasticsearch

from app.config import get_settings
from app.generation.providers import LLMProvider, build_provider
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
    settings = get_settings()
    return CrossEncoderReranker(settings.rerank_model)


@lru_cache
def get_provider() -> LLMProvider:
    return build_provider(get_settings())
