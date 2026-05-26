# grounded-rag-assistant

## Overview

`grounded-rag-assistant` is a production-style RAG assistant over Elasticsearch
and AI-search technical documentation. Phase 0 provides only the project
scaffold, local services, configuration, and health checks.

## Architecture

The application keeps API delivery separate from retrieval and generation logic
so later phases can expose those same functions through LangGraph and MCP
without FastAPI coupling.

## Stack

- Python 3.11
- FastAPI
- Elasticsearch 9.x, self-hosted single node for BM25 and vector search
- PostgreSQL for application data
- Local sentence-transformers embeddings, default `BAAI/bge-small-en-v1.5`
- Provider-abstracted generation: Gemini free tier or local Ollama
- Docker Compose for local development

## Quickstart

Details will be expanded in later phases.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
curl http://localhost:8000/health
make lint
make test
```
