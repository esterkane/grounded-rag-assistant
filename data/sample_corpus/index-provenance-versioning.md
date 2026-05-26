---
title: Provenance and Versioning for Indexed Documentation
source_url: https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html
version: 9.4
last_updated: 2026-05-09
---

# Provenance and Versioning for Indexed Documentation

A grounded assistant must show where an answer came from. Every indexed chunk
should carry the source URL, document title, version, last updated date, heading
path, and permissions. This metadata allows the assistant to cite the right
source and avoid mixing public and restricted content.

## Stable Identifiers

Stable chunk identifiers make ingestion idempotent. A reliable identifier can be
derived from the source path, heading path, and chunk index. If the same corpus is
ingested again, the bulk operation updates the same `_id` in Elasticsearch.

## Version Metadata

Documentation changes over time. Version and last updated fields should be
stored as keywords so retrieval code can filter or boost recent documentation.
The content text remains independent from these filters, which keeps ranking
behavior easier to explain.
