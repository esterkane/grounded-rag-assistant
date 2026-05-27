# grounded-rag-assistant

A production-style retrieval-augmented generation (RAG) assistant over
Elasticsearch and AI-search technical documentation. It answers questions
strictly grounded in retrieved documentation, with per-claim citations and an
explicit "insufficient evidence" path when the corpus does not support an answer.

## Overview

The assistant retrieves relevant documentation chunks (hybrid BM25 + vector
search over a single Elasticsearch node), then generates an answer that cites the
specific chunks it used. If retrieval does not surface enough evidence, it says
so rather than guessing.

The project is built in six sequential phases (see `docs/BUILD_PHASES.md`).
**Phase 0 (this scaffold) is complete; Phases 1–6 are not implemented yet.**

## Architecture

```
            ┌────────────┐
  query ──▶ │  FastAPI    │  /search, /ask, /health, admin/review
            │  app/api    │
            └─────┬──────┘
                  │ calls (no FastAPI coupling)
        ┌─────────┴───────────┐
        ▼                     ▼
┌────────────────┐    ┌────────────────┐
│ app/retrieval  │    │ app/generation │
│ BM25 + vector  │    │ provider-abstr.│
│ hybrid (RRF)   │    │ grounded answer│
│ optional rerank│    │ + citations    │
└───────┬────────┘    └───────┬────────┘
        │                     │
        ▼                     ▼
┌────────────────┐    ┌────────────────┐
│ Elasticsearch  │    │  LLM provider  │
│ (BM25+vectors) │    │ gemini / ollama│
└────────────────┘    └────────────────┘

  PostgreSQL — application data (query logs, feedback)
```

`app/retrieval/` and `app/generation/answerer.py` are deliberately free of any
FastAPI coupling so a later project can expose them as MCP tools and drive them
from a LangGraph layer without rework.

## Stack

- Python 3.11, FastAPI + uvicorn
- Elasticsearch 9.4.1 (single node) — both BM25 and vector search; no separate vector DB
- PostgreSQL 17 — application data
- Embeddings: local `sentence-transformers` (`BAAI/bge-small-en-v1.5`)
- LLM generation: provider-abstracted — `gemini` (free tier) or `ollama` (local)
- Tooling: `ruff` (lint/format), `pytest`, Docker Compose

## Quickstart

> Detail expands as later phases land. Phase 0 gets the stack up and `/health` green.

1. Ensure the host meets the infra prerequisites (`vm.max_map_count >= 262144`,
   6–8 GB for the Docker/WSL VM). See `docs/INFRA.md`.
2. Configure the environment:
   ```bash
   cp .env.example .env
   # set GEMINI_API_KEY, or set LLM_PROVIDER=ollama to run fully local
   ```
3. Start the stack:
   ```bash
   make up
   ```
4. Check health (expects 200 once ES and Postgres are ready):
   ```bash
   curl -i http://localhost:8000/health
   ```
5. Run lint and tests:
   ```bash
   make lint
   make test
   ```

Stop the stack with `make down` (data volumes are preserved).

## Not implemented yet

- Phase 1 — ingestion and indexing (`make ingest`)
- Phase 2 — hybrid retrieval and `/search`
- Phase 3 — grounded generation and `/ask`
- Phase 4 — evaluation harness (`make eval`)
- Phase 5 — review UI and feedback capture
- Phase 6 — observability, cost tracking, CI, deployment docs
