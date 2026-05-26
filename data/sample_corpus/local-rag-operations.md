---
title: Local RAG Operations with Elasticsearch and PostgreSQL
source_url: https://www.elastic.co/guide/en/elasticsearch/reference/current/docker.html
version: 9.4
last_updated: 2026-05-11
---

# Local RAG Operations with Elasticsearch and PostgreSQL

Local development should use self-hosted services so contributors can run the
assistant without paid infrastructure. Elasticsearch stores searchable chunks and
vectors. PostgreSQL stores application data such as conversations, evaluation
runs, and audit records in later phases.

## Elasticsearch Service

For local development, Elasticsearch runs as a single node with security disabled
inside Docker Compose. The container has a memory limit so indexing and search
behavior are more predictable on developer machines.

## PostgreSQL Service

PostgreSQL runs alongside the API and is checked by the `/health` endpoint. The
ingestion phase does not write application records yet, but keeping Postgres in
the stack validates connectivity before later phases add persistence.

## API Service

The API imports configuration from environment variables and exposes health
checks. Retrieval and generation remain separate importable modules so they can
later be exposed through LangGraph and MCP tools.
