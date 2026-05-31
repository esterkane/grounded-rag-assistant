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

    # A known chunk from the fetched corpus (data/sample_corpus/<repo_slug>/...).
    known_path = "data/sample_corpus/docs-content/solutions/search/rag.md"
    response = client.search(
        index=settings.elasticsearch_index,
        query={"term": {"source_path": known_path}},
        size=1,
    )

    assert summary.docs >= 4
    assert summary.chunks >= 4
    assert response["hits"]["hits"]
    source = response["hits"]["hits"][0]["_source"]
    assert source["source_path"] == known_path
    assert source["title"] == "RAG [_retrieval_augmented_generation]"
    assert source["source_url"].startswith("https://github.com/elastic/")
    assert source["permissions"] == ["public"]
    assert source["embedding"]
