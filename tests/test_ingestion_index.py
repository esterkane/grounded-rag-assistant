from pathlib import Path

from elasticsearch import Elasticsearch

from app.config import get_settings
from app.ingestion.run import ingest_path


def test_ingest_indexes_known_chunk_with_vector() -> None:
    settings = get_settings()
    client = Elasticsearch(settings.elasticsearch_url, request_timeout=30)
    if client.indices.exists(index=settings.elasticsearch_index):
        client.indices.delete(index=settings.elasticsearch_index)

    summary = ingest_path(Path("data/sample_corpus"))

    response = client.search(
        index=settings.elasticsearch_index,
        query={"match": {"title": "Elasticsearch Vector Search for RAG"}},
        size=1,
    )

    assert summary.docs >= 4
    assert summary.chunks >= 4
    assert response["hits"]["hits"]
    source = response["hits"]["hits"][0]["_source"]
    assert source["title"] == "Elasticsearch Vector Search for RAG"
    assert source["source_url"].startswith("https://www.elastic.co/")
    assert source["permissions"] == ["public"]
    assert source["embedding"]
