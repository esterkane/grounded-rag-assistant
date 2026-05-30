# grounded-rag-assistant

A production-style RAG (retrieval-augmented generation) assistant over
Elasticsearch and AI-search technical documentation. It answers questions
**strictly grounded in retrieved documentation**, with per-claim citations and an
explicit "insufficient evidence" path — it never guesses when the corpus does not
support an answer.

## Overview

- **Hybrid retrieval** over Elasticsearch: BM25 + dense-vector kNN fused with
  Reciprocal Rank Fusion (native ES RRF when available, Python fallback
  otherwise), with optional cross-encoder reranking.
- **Grounded generation**: numbered context chunks, every citation validated
  against the chunks actually retrieved; an answer with no valid citation is
  downgraded to the insufficient-evidence path.
- **Review UI + feedback**: a server-rendered queue of flagged/low-confidence
  answers and a feedback form; every `/ask` is logged.
- **Observability**: structured JSON logs with trace ids, OpenTelemetry tracing,
  and per-`/ask` token + cost tracking surfaced at `/metrics`.
- **Zero paid services**: local embeddings, self-hosted Elasticsearch, free-tier
  Gemini or fully-local Ollama.

## Architecture

API delivery is kept separate from retrieval and generation logic: code in
`app/retrieval/` and `app/generation/answerer.py` has **no FastAPI coupling**, so
the same functions can later be exposed through LangGraph and MCP without rework.
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Stack

- Python 3.11, FastAPI + uvicorn
- Elasticsearch 9.4.1 (single node) — BM25 **and** vector search; no separate
  vector DB
- PostgreSQL for application data (query logs, feedback)
- Local `sentence-transformers` embeddings (`BAAI/bge-small-en-v1.5`)
- Provider-abstracted generation: Gemini free tier or local Ollama
- OpenTelemetry tracing; Docker Compose for local development

## Quickstart

Requirements: Docker with 6–8 GB available, and `vm.max_map_count >= 262144` on
the host (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).

```bash
cp .env.example .env                       # set GEMINI_API_KEY, or LLM_PROVIDER=ollama
make up                                     # build + start ES, Postgres, API
curl -s http://localhost:8000/health        # 200 when ES + Postgres are healthy
make corpus                                 # fetch the corpus from Elastic GitHub repos
make ingest                                 # index the sample corpus (idempotent)

# Ask a grounded question:
curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"query":"How does vector search work in Elasticsearch?","k":6}'

# Review queue (HTML) and operational metrics:
open http://localhost:8000/review
curl -s http://localhost:8000/metrics
```

## Demo

`make demo` brings the stack up, ingests the corpus, and runs three example
questions end to end, then prints the metrics summary:

```bash
make demo
```

Example questions (`app/demo.py`):
1. "How does vector search work in Elasticsearch?"
2. "What is reciprocal rank fusion and how does hybrid search combine results?"
3. "How should I chunk documents before indexing them for retrieval?"

## Screenshots

_Placeholder — add screenshots of the review queue and a detail page:_

- `docs/img/review-queue.png` — flagged-query queue
- `docs/img/review-detail.png` — query, retrieved chunks, answer + citations,
  feedback form

## Development

```bash
make test     # pytest (pure unit tests + ES/Postgres integration tests)
make lint     # ruff check .
make eval     # evaluation harness -> eval_reports/
make logs     # tail logs
make down     # stop (keeps volumes; never use `down -v`)
```

CI (`.github/workflows/ci.yml`) runs lint, tests, and `make eval` against
Elasticsearch + Postgres service containers on every push/PR.

## Docs

- [Architecture](docs/ARCHITECTURE.md) · [Runbook](docs/RUNBOOK.md) ·
  [Deployment](docs/DEPLOYMENT.md)
- [Build phases](docs/BUILD_PHASES.md) · [Corpus](docs/CORPUS.md) ·
  [Infra](docs/INFRA.md)

The corpus itself is not committed: `make corpus` fetches it reproducibly from
public Elastic GitHub repos into the gitignored `data/sample_corpus/` (see
[docs/CORPUS.md](docs/CORPUS.md)). Run it before `make ingest`.

## Not implemented yet

- The LangGraph + MCP layer ("Project 2") that wraps the retrieval and generation
  functions as tools is future work — the core is kept FastAPI-free to enable it.
