---
title: Hybrid Search Patterns for Technical Assistants
source_url: https://www.elastic.co/search-labs/blog/hybrid-search-elasticsearch
version: 9.4
last_updated: 2026-05-10
---

# Hybrid Search Patterns for Technical Assistants

Technical assistants usually need both lexical and semantic search. Lexical
search is strong for product names, configuration keys, and exact exceptions.
Vector search is strong for conceptual questions where the user's words differ
from the documentation.

## Keyword Recall

BM25 retrieval should index chunk content and titles as text. It can surface
exact matches for terms such as `xpack.security.enabled`, `dense_vector`, and
`pg_isready`. These exact matches are important when an answer must cite a
setting name or command exactly.

## Semantic Recall

Semantic retrieval embeds each chunk with a local sentence-transformers model.
The default model for this project is `BAAI/bge-small-en-v1.5`, which is small
enough for local development and produces normalized vectors suitable for cosine
similarity.

## Fusion

A later retrieval phase can combine BM25 and vector candidates with reciprocal
rank fusion or another transparent ranker. The ingestion phase only needs to
preserve fields that make both retrieval modes possible.
