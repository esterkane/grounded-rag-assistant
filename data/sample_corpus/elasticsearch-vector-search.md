---
title: Elasticsearch Vector Search for RAG
source_url: https://www.elastic.co/guide/en/elasticsearch/reference/current/dense-vector.html
version: 9.4
last_updated: 2026-05-12
---

# Elasticsearch Vector Search for RAG

Elasticsearch can store dense vector embeddings next to searchable text fields in
the same document. For retrieval augmented generation, this means a single
`rag_chunks` index can support keyword recall, semantic recall, metadata filters,
and provenance lookup without a separate vector database.

## Dense Vector Mapping

A production RAG chunk should store the raw text, stable provenance metadata, and
an embedding in a `dense_vector` field. The vector field needs a fixed dimension
that matches the embedding model. When the field is indexed with cosine
similarity, Elasticsearch can use approximate nearest neighbor search to return
semantically similar passages.

## Operational Notes

Chunk IDs should be deterministic so repeated ingestion updates existing
documents instead of creating duplicates. Keep permissions and version metadata
as keyword fields so filters can be applied before generation. The text fields
remain useful because BM25 often finds exact API names, settings, and error
messages that vector search may smooth over.
