"""Ingest CLI: load corpus -> chunk -> embed -> upsert into Elasticsearch.

    python -m app.ingestion.run --path data/sample_corpus

Idempotent: chunks are keyed by deterministic ``chunk_id``, so re-running over the
same corpus yields the same chunk count with no duplicates.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import settings
from app.ingestion.chunking import chunk_document
from app.ingestion.embedder import Embedder
from app.ingestion.indexer import bulk_upsert, create_index, get_client
from app.ingestion.loaders import discover, load_document
from app.ingestion.models import Chunk


def ingest(path: str, index: str | None = None, batch_size: int = 32) -> dict:
    """Run the pipeline. Returns a summary dict (documents, chunks, failures)."""
    corpus_root = Path(path)
    if not corpus_root.exists():
        raise FileNotFoundError(
            f"corpus path not found: {corpus_root} (run `make corpus` first)"
        )
    index = index or settings.es_index

    embedder = Embedder(batch_size=batch_size)
    client = get_client()
    created = create_index(client, index, dims=embedder.dim())

    documents = 0
    failures = 0
    all_chunks: list[Chunk] = []
    for file, kind in discover(corpus_root):
        try:
            doc = load_document(file, kind, corpus_root)
            chunks = chunk_document(doc)
            all_chunks.extend(chunks)
            documents += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            failures += 1
            print(f"  ! failed to load {file}: {type(exc).__name__}: {exc}")

    if all_chunks:
        vectors = embedder.encode([c.content for c in all_chunks])
        for chunk, vector in zip(all_chunks, vectors, strict=True):
            chunk.embedding = vector
        indexed = bulk_upsert(client, index, all_chunks)
    else:
        indexed = 0

    return {
        "documents": documents,
        "chunks": len(all_chunks),
        "indexed": indexed,
        "failures": failures,
        "index": index,
        "index_created": created,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest the sample corpus into Elasticsearch.")
    parser.add_argument("--path", default="data/sample_corpus", help="Corpus directory.")
    parser.add_argument("--index", default=None, help="Target index (default from settings).")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    args = parser.parse_args(argv)

    summary = ingest(args.path, index=args.index, batch_size=args.batch_size)
    print(
        "Ingest summary: "
        f"documents={summary['documents']} chunks={summary['chunks']} "
        f"indexed={summary['indexed']} failures={summary['failures']} "
        f"index={summary['index']} (created={summary['index_created']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
