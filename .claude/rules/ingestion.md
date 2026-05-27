---
paths:
  - "app/ingestion/**/*"
---

# Ingestion & indexing rules

The ingestion pipeline must be **idempotent**: re-running it over the same corpus
must produce the same chunk count with no duplicates. This is an acceptance
criterion, not a nice-to-have.

## Chunk identity

- Chunk IDs are a **deterministic hash** of `(source_path + heading_path + chunk_index)`.
  The same input always yields the same `chunk_id`.
- Bulk-upsert chunks keyed by `chunk_id` so re-ingest overwrites rather than
  duplicates.

## Chunking

- Markdown: **header-aware** — split on headings and keep the heading path.
- PDF: **size-based with overlap** (use `pypdf`).
- Target roughly 500–800 tokens per chunk with about 100 tokens of overlap.

## Per-chunk metadata

Every chunk carries: `chunk_id`, `doc_id`, `source_url`, `title`, `heading_path`,
`version`, `last_updated`, `ingested_at`, and `permissions` (a list of role
strings, default `["public"]`). Do not drop or rename these fields — retrieval,
permission filtering, and citations all depend on them.

## Embeddings & index

- `embedder.py` wraps `sentence-transformers` (`bge-small-en-v1.5`), batched and
  with normalized vectors.
- The `rag_chunks` ES index mapping must keep: text fields (`content`, `title`) for
  BM25, `keyword` fields for metadata, and a `dense_vector` field with the correct
  dimensions, `index: true`, and cosine similarity.
- The create-index function must be idempotent (safe to call when the index
  already exists).

## CLI

- The ingest CLI is `python -m app.ingestion.run --path <dir>`, wired to
  `make ingest`. It must print a summary: documents, chunks, failures.

## Corpus source

- The document corpus is fetched from public Elastic GitHub repositories by
  `app/ingestion/fetch_corpus.py` (run via `make corpus`), not scraped from the
  rendered docs website. See `docs/CORPUS.md` for the source repos, topic
  filter, and git-derived front-matter mapping.
- `data/sample_corpus/` is gitignored and reproducible: the repo holds the fetch
  script, not Elastic's content.
- `make corpus` runs before `make ingest`. Each fetched file must carry valid
  front-matter (`title`, `source_url`, `version`, `last_updated`) — ingestion
  depends on it, and `source_url` is the per-document attribution.
