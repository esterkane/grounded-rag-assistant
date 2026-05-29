# Architecture

`grounded-rag-assistant` answers questions strictly grounded in retrieved
documentation, with per-claim citations and an explicit insufficient-evidence
path. It is a single FastAPI service backed by Elasticsearch (BM25 **and** vector
search) and PostgreSQL (application data), with local embeddings and a
provider-abstracted LLM.

## Component overview

```
                        ┌─────────────────────────────────────────────┐
                        │                FastAPI (app/api)             │
   HTTP client ───────▶ │  /search  /ask  /admin/*  /review/*  /metrics │
                        │           /health                            │
                        └───────┬───────────────┬───────────────┬──────┘
                                │               │               │
                  retrieval ◀───┘     generation┘        DB / repository
              (app/retrieval)      (app/generation)         (app/db)
                    │                     │                     │
          ┌─────────┴─────────┐   ┌───────┴────────┐    ┌───────┴───────┐
          │  Elasticsearch    │   │  LLM provider  │    │  PostgreSQL   │
          │  rag_chunks       │   │ gemini│ollama  │    │ query_log     │
          │  BM25 + dense_vec │   └────────────────┘    │ feedback      │
          └───────────────────┘                         └───────────────┘
                    ▲
          local sentence-transformers (bge-small-en-v1.5) embeddings
```

Cross-cutting (`app/observability`): structured JSON logging with a trace id, and
OpenTelemetry spans around retrieval and generation (console exporter by default,
OTLP/Jaeger optional).

## The core boundary (most important constraint)

`app/retrieval/` and `app/generation/answerer.py` are **free of any FastAPI
coupling** — plain importable functions taking ordinary arguments and returning
Pydantic models. The `app/api/` layer is the only place that depends on FastAPI;
it validates requests and adapts these functions to HTTP. This keeps the
retrieval and generation core reusable as MCP tools / a LangGraph layer later,
without rework. The rule is enforced by `.claude/rules/retrieval-generation.md`.

## Request flow

### `POST /search`
1. `app/api/search.py` validates the request (`query`, `k`, `rerank?`,
   `caller_roles?`).
2. `app/retrieval/retriever.hybrid_search` runs BM25 + kNN and fuses with RRF
   (native Elasticsearch RRF retriever when available, Python fallback otherwise).
   Permission filtering drops chunks whose `permissions` don't intersect the
   caller's roles.
3. Optional cross-encoder rerank (`RERANK_ENABLED`).
4. Returns chunks with metadata and method tags.

### `POST /ask`
1. `app/api/ask.py` validates input and calls
   `app/generation/answerer.answer_question`.
2. The answerer retrieves (as above), builds a prompt with numbered context
   chunks labeled by `chunk_id`/`source_url`, and calls the configured LLM
   provider.
3. Output is parsed defensively (one retry); **every citation is validated**
   against the chunks actually in context — invalid ones are dropped and an
   answer with no valid citation is downgraded to the insufficient path.
4. The result (answer, claims, sources, token usage, model) is returned and a
   `query_log` row is written (best-effort), flagging insufficient/low-confidence
   answers for the review UI. Estimated cost is computed from a static price
   table.

### Review UI and metrics
- `app/api/review.py` renders a server-side queue of flagged queries and a detail
  page with a feedback form (Jinja2, no Node/build step). `app/api/admin.py`
  exposes the same data as JSON.
- `app/api/metrics.py` (`GET /metrics`) aggregates `query_log`: counts, token
  totals/averages, estimated cost, and latency p50/p95.

## Data stores

- **Elasticsearch `rag_chunks`** — text fields (`content`, `title`) for BM25,
  keyword metadata, and a `dense_vector` (`embedding`, cosine). Chunk IDs are a
  deterministic hash so re-ingest is idempotent.
- **PostgreSQL** — `query_log` (one row per `/ask`, with tokens/cost/latency) and
  `feedback`. Schema is applied by the forward-only runner in `app/db/migrate.py`
  (auto-run on API startup).

## Observability

- **Logging** — `app/observability/logging.py` emits one JSON object per log
  line, enriched with the active span's `trace_id`/`span_id`.
- **Tracing** — `app/observability/tracing.py` installs an OpenTelemetry
  `TracerProvider`. Spans: `retrieval.{bm25,vector,hybrid}_search`,
  `generation.{answer_question,generate}`. Default exporter is the console; set
  `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g. the Jaeger OTLP port) to ship traces.
- **Cost** — `app/observability/cost.py` estimates would-be USD cost from a
  static public price table, recorded even on free tiers.
