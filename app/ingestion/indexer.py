"""Elasticsearch index management and bulk upsert for ``rag_chunks``.

The mapping keeps text fields (``content``, ``title``) for BM25, ``keyword`` fields
for metadata/filtering, and a ``dense_vector`` for kNN. Upserts are keyed by
``chunk_id`` so re-ingest overwrites rather than duplicates.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.config import settings
from app.ingestion.models import Chunk


def get_client():
    """Construct an Elasticsearch 9.x client from settings."""
    from elasticsearch import Elasticsearch

    return Elasticsearch(settings.es_url, request_timeout=30)


def index_mapping(dims: int) -> dict:
    return {
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "content": {"type": "text"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "heading_path": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "version": {"type": "keyword"},
                "last_updated": {"type": "date"},
                "ingested_at": {"type": "date"},
                "permissions": {"type": "keyword"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        }
    }


def create_index(client, index: str, dims: int) -> bool:
    """Create the index if it does not exist. Returns True if created.

    Idempotent: safe to call when the index already exists.
    """
    if client.indices.exists(index=index):
        return False
    client.indices.create(index=index, body=index_mapping(dims))
    return True


def bulk_upsert(client, index: str, chunks: Iterable[Chunk]) -> int:
    """Index chunks keyed by chunk_id (overwrite-on-conflict). Returns count indexed."""
    from elasticsearch.helpers import bulk

    actions = (
        {
            "_op_type": "index",
            "_index": index,
            "_id": chunk.chunk_id,
            "_source": chunk.to_es_doc(),
        }
        for chunk in chunks
    )
    success, _ = bulk(client, actions)
    client.indices.refresh(index=index)
    return success
