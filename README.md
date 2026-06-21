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
the same functions are also exposed through MCP (and, in progress, LangGraph)
without rework. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Agent Access (MCP)

A FastMCP server (`app/mcp/`) exposes the retrieval and generation core as three
**read-only** MCP tools that any MCP client (a LangGraph agent, Claude Code,
Cursor) can call:

- `retrieve_chunks` — hybrid / BM25 / vector retrieval over the corpus.
- `answer_with_citations` — the full grounded-answer pipeline.
- `list_documents` — a catalog of indexed documents for planning.

The tools reuse the same FastAPI-free functions the HTTP API uses, return
structured errors, and never leak stack traces. Start the server with
`make mcp-server` (stdio) and register it via a `.mcp.json` snippet. See
[docs/mcp.md](docs/mcp.md) for the tool signatures, the error contract, transport
options, and client registration.

## Stack

- Python 3.11, FastAPI + uvicorn
- Elasticsearch 9.4.1 (single node) — BM25 **and** vector search; no separate
  vector DB
- PostgreSQL for application data (query logs, feedback)
- Local `sentence-transformers` embeddings (`BAAI/bge-small-en-v1.5`)
- Provider-abstracted generation: Gemini free tier (`gemini-2.5-flash`) or local
  Ollama, with automatic Ollama fallback when Gemini's quota is exhausted
  (`LLM_FALLBACK`; `gemini-2.0-flash` is deprecated and shuts down 2026-06-01)
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
- [Agent access (MCP)](docs/mcp.md) · [Agent layer](docs/AGENT.md)

The corpus itself is not committed: `make corpus` fetches it reproducibly from
public Elastic GitHub repos into the gitignored `data/sample_corpus/` (see
[docs/CORPUS.md](docs/CORPUS.md)). Run it before `make ingest`.

## Not implemented yet

- True per-file `last_updated` dates. `make corpus` uses a `--depth 1` clone, so
  every fetched file is stamped with the corpus fetch date (UTC). A partial clone
  (`--filter=blob:none`) would give real per-file commit dates — future work.
- The **MCP tools layer** ("Project 2") that wraps the retrieval and generation
  functions as agent-callable tools is **implemented** (`app/mcp/`,
  three tools — see [docs/mcp.md](docs/mcp.md)). The **LangGraph** agent that
  orchestrates those tools is **partially built** (plan → retrieve → reflect →
  answer; persistent checkpointing, the `/agent_ask` HTTP endpoint, and the agent
  demo are still in progress — see [docs/AGENT.md](docs/AGENT.md)).

## Caveats

- The Gemini-to-Ollama fallback works per request, so it does not rescue a full
  batch eval: the answer-quality pass still exhausts Gemini's free-tier rate limit
  faster than the fallback trips on each call. For a clean eval pass, set
  `LLM_PROVIDER=ollama` and run the eval directly against the local model.
- `gemini-2.0-flash` is deprecated and shuts down on 2026-06-01, so the project
  defaults to `gemini-2.5-flash`. Override the model with `GEMINI_MODEL`.
