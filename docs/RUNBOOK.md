# Runbook

Operational guide for running `grounded-rag-assistant` locally via Docker Compose.

## Start / stop

```bash
make up        # build + start elasticsearch, postgres, api (detached)
make logs      # tail logs
make down      # stop containers (keeps the ES + Postgres volumes)
```

`make up`/`make down` never pass `-v`. **Do not run `docker compose down -v`** — it
wipes the `es-data` and `postgres-data` volumes (the index and all query logs).

Check health (200 only when both ES and Postgres are reachable):

```bash
curl -s http://localhost:8000/health
```

## Ingest / re-ingest the corpus

```bash
make ingest    # python -m app.ingestion.run --path data/sample_corpus
```

Ingestion is **idempotent**: chunk IDs are a deterministic hash of
`(source_path + heading_path + chunk_index)`, so re-running produces the same
chunk count with no duplicates. Verify:

```bash
curl -s http://localhost:9200/rag_chunks/_count
```

## Database migrations

Tables are applied automatically on API startup. To apply them manually:

```bash
make migrate   # python -m app.db.migrate (forward-only, idempotent)
```

## Evaluation

```bash
make eval                 # retrieval metrics across all modes + answer quality
                          # writes a timestamped report to eval_reports/
```

The hybrid-MRR regression test (`tests/test_eval_regression.py`) fails if hybrid
MRR drops below `EVAL_HYBRID_MRR_THRESHOLD`. Investigate regressions; do not lower
the threshold to make a run pass.

## Tracing

Spans go to the console by default (visible in `make logs`). To use Jaeger:

```bash
docker compose --profile tracing up -d
# set OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318 for the api service, then
docker compose up -d api
# open the UI:
open http://localhost:16686
```

## Metrics

```bash
curl -s http://localhost:8000/metrics    # counts, tokens, cost, latency p50/p95
```

## Common failures and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| ES container exits / `max virtual memory areas vm.max_map_count too low` | Host `vm.max_map_count` below 262144 | `sudo sysctl -w vm.max_map_count=262144` (on WSL2, set on the host/`.wslconfig`). |
| `docker compose up` OOM-kills ES | Docker has < ~6 GB | Raise Docker's memory limit to 6–8 GB. |
| `/ask` returns 500, logs show `GEMINI_API_KEY is not set` | Gemini selected without a key | Set `GEMINI_API_KEY` (gitignored `.env`) or set `LLM_PROVIDER=ollama`. |
| `/ask` answers are all "insufficient", logs show `429 RESOURCE_EXHAUSTED` | Gemini free-tier quota exhausted | Set `LLM_FALLBACK=ollama` (auto-degrades to local Ollama; see Provider notes), or switch primary to `ollama`. |
| `/health` 503 on `postgres` | Postgres not ready | `make logs`; wait for the healthcheck, then retry. |
| Review UI empty after asking | query_log write failed (DB down at ask time) | Check `make logs` for "Failed to write query_log"; verify Postgres health. |

## Provider notes

The Gemini free tier can return `429` with `quota=0` even on the first request of
the day; this depends on account state, not just request volume. Do not treat a
first-request 429 as a bug.

The verified fallback is local Ollama. Pull the default model with
`ollama pull llama3.1`. Either run it as the primary (`LLM_PROVIDER=ollama`), or
leave it as the automatic fallback: with `LLM_FALLBACK=ollama` (the default in
`.env.example`), `/ask` keeps Gemini as primary but degrades to Ollama when
Gemini's tokens are unavailable — a 429 / `RESOURCE_EXHAUSTED` quota error, or no
`GEMINI_API_KEY` at all. The fallback needs `OLLAMA_BASE_URL` reachable and the
model pulled; a non-quota error (e.g. a malformed request) is not masked.

CI and the integration tests override the LLM provider with a deterministic
in-process fake, so `/ask` is reproducible without any live LLM call.

## Backup / restore

The data lives in two named Docker volumes: `grounded-rag-assistant_es-data` and
`grounded-rag-assistant_postgres-data`.

Postgres logical backup:

```bash
docker compose exec postgres pg_dump -U grounded_rag grounded_rag > backup.sql
# restore:
cat backup.sql | docker compose exec -T postgres psql -U grounded_rag -d grounded_rag
```

Elasticsearch: the `rag_chunks` index is reproducible from the corpus — prefer
`make ingest` over restoring ES. For a raw volume backup, stop the stack and
archive the named volume with a throwaway container.
