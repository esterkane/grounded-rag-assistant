import argparse
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embedder import SentenceTransformersEmbedder
from app.ingestion.index import (
    attach_embeddings,
    bulk_upsert_chunks,
    count_chunks,
    create_client,
    ensure_index,
)
from app.ingestion.loaders import load_documents


@dataclass(frozen=True)
class IngestionSummary:
    docs: int
    chunks: int
    failures: int
    indexed_chunks: int
    total_index_chunks: int


def ingest_path(path: Path) -> IngestionSummary:
    settings = get_settings()
    documents, load_failures = load_documents(path)
    chunks = [chunk for document in documents for chunk in chunk_document(document)]

    embedder = SentenceTransformersEmbedder(settings.embedding_model)
    embeddings = embedder.embed([chunk.content for chunk in chunks])
    embedded_chunks = attach_embeddings(chunks, embeddings)

    client = create_client(settings)
    ensure_index(client, settings.elasticsearch_index, embedder.dimensions)
    indexed_chunks, index_errors = bulk_upsert_chunks(
        client,
        settings.elasticsearch_index,
        embedded_chunks,
    )
    client.indices.refresh(index=settings.elasticsearch_index)

    failures = len(load_failures) + len(index_errors)
    return IngestionSummary(
        docs=len(documents),
        chunks=len(chunks),
        failures=failures,
        indexed_chunks=indexed_chunks,
        total_index_chunks=count_chunks(client, settings.elasticsearch_index),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into Elasticsearch.")
    parser.add_argument("--path", type=Path, required=True, help="File or directory to ingest.")
    args = parser.parse_args()

    from app.observability import configure_logging

    configure_logging(get_settings())
    summary = ingest_path(args.path)
    print(
        "Ingest summary: "
        f"docs={summary.docs} chunks={summary.chunks} "
        f"indexed={summary.indexed_chunks} failures={summary.failures} "
        f"total_index_chunks={summary.total_index_chunks}"
    )


if __name__ == "__main__":
    main()
