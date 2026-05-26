from dataclasses import asdict, replace

from elasticsearch import Elasticsearch, helpers

from app.config import Settings
from app.ingestion.models import DocumentChunk


def create_client(settings: Settings) -> Elasticsearch:
    return Elasticsearch(settings.elasticsearch_url, request_timeout=60)


def ensure_index(client: Elasticsearch, index_name: str, vector_dims: int) -> None:
    if client.indices.exists(index=index_name):
        return
    client.indices.create(
        index=index_name,
        settings={"index.mapping.exclude_source_vectors": False},
        mappings={
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "source_path": {"type": "keyword"},
                "source_url": {"type": "keyword"},
                "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "heading_path": {"type": "keyword"},
                "version": {"type": "keyword"},
                "last_updated": {"type": "keyword"},
                "ingested_at": {"type": "date"},
                "permissions": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "content": {"type": "text"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": vector_dims,
                    "index": True,
                    "similarity": "cosine",
                },
            }
        },
    )


def attach_embeddings(
    chunks: list[DocumentChunk],
    embeddings: list[list[float]],
) -> list[DocumentChunk]:
    return [
        replace(chunk, embedding=embedding)
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]


def bulk_upsert_chunks(
    client: Elasticsearch,
    index_name: str,
    chunks: list[DocumentChunk],
) -> tuple[int, list[object]]:
    actions = [
        {
            "_op_type": "update",
            "_index": index_name,
            "_id": chunk.chunk_id,
            "doc": asdict(chunk),
            "doc_as_upsert": True,
        }
        for chunk in chunks
    ]
    if not actions:
        return 0, []
    return helpers.bulk(client, actions, stats_only=False, raise_on_error=False)


def count_chunks(client: Elasticsearch, index_name: str) -> int:
    if not client.indices.exists(index=index_name):
        return 0
    result = client.count(index=index_name)
    return int(result["count"])
