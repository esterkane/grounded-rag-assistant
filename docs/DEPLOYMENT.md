# Deployment

`grounded-rag-assistant` is designed to run as a small set of Docker containers.
Everything is local or free-tier — **no paid services** (no Elastic Cloud, no
Pinecone, no ELSER, no paid LLM keys).

## Topology

Three core services (`docker-compose.yml`):

- **elasticsearch** `9.4.1`, single node — BM25 + vector search (`rag_chunks`).
- **postgres** `16` — application data (`query_log`, `feedback`).
- **api** — the FastAPI app (`uvicorn app.main:app`).

One optional service, off by default, behind the `tracing` profile:

- **jaeger** — trace backend (UI `:16686`, OTLP/HTTP `:4318`).

## Resource needs

- **Elasticsearch**: container limited to **4 GB** (`mem_limit: 4g`) with a **2 GB
  JVM heap** (`ES_JAVA_OPTS=-Xms2g -Xmx2g`) — keep the heap at ~50% of the
  container limit. The original prompts targeted ~2 GB; this project pins 4 GB / 2
  GB heap.
- **Host**: budget **6–8 GB** total for ES + Postgres + API.
- **Linux/WSL2 host**: `vm.max_map_count` must be **≥ 262144**
  (`sudo sysctl -w vm.max_map_count=262144`), or Elasticsearch fails to start.

## Configuration (environment variables)

Copy `.env.example` to `.env` and adjust. Key variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `ELASTICSEARCH_URL` | `http://localhost:9200` | ES endpoint (compose sets `http://elasticsearch:9200`). |
| `ELASTICSEARCH_INDEX` | `rag_chunks` | Chunk index name. |
| `POSTGRES_HOST` / `_PORT` / `_DB` / `_USER` / `_PASSWORD` | local dev values | Application DB. |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local sentence-transformers model. |
| `LLM_PROVIDER` | `gemini` | `gemini` (free tier) or `ollama` (local). |
| `GEMINI_API_KEY` | _(empty)_ | Required for `gemini`. Store in gitignored `.env`. |
| `OLLAMA_BASE_URL` / `OLLAMA_MODEL` | local | For `ollama`. |
| `RERANK_ENABLED` | `false` | Optional cross-encoder rerank. |
| `LOG_FORMAT` | `json` | `json` (structured, trace ids) or `text`. |
| `OTEL_TRACES_ENABLED` | `true` | Toggle tracing. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | _(empty)_ | Empty = console; set to `http://jaeger:4318` to ship traces. |

Secrets (`.env`, `secrets/`) are gitignored — never commit `GEMINI_API_KEY`.

## LLM provider options

- **Gemini (default)** — free tier via Google AI Studio. Get a key (no card
  required), set `GEMINI_API_KEY`. Subject to free-tier rate/quota limits; the
  service degrades to the insufficient-evidence path on errors rather than
  failing.
- **Ollama (fully offline)** — install Ollama on the host, `ollama pull llama3.1`,
  set `LLM_PROVIDER=ollama` and `OLLAMA_BASE_URL` (from a container, typically
  `http://host.docker.internal:11434`).

## Deploy steps

```bash
cp .env.example .env          # set GEMINI_API_KEY or LLM_PROVIDER=ollama
make up                       # build + start (applies DB migrations on startup)
curl -s http://localhost:8000/health
make ingest                   # index the sample corpus
make demo                     # ingest + 3 example questions end to end
```

For a non-local deployment, run the same images behind a reverse proxy, point the
env vars at managed-but-self-hosted ES/Postgres if desired, ensure the host meets
the memory and `vm.max_map_count` requirements above, and supply secrets through
the platform's secret store rather than a committed file.

## CI

`.github/workflows/ci.yml` runs on push/PR with Elasticsearch and Postgres as
service containers: it lints, ingests the committed sample corpus, runs the test
suite, runs `python -m app.eval --no-answers` (retrieval metrics + the regression
guard; no LLM key in CI), and uploads the eval report as an artifact.
