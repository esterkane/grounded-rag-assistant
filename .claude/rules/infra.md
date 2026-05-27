---
paths:
  - "docker-compose.yml"
  - "docker-compose.*.yml"
  - "docker/**/*"
  - ".env.example"
  - "Makefile"
---

# Infrastructure rules — Docker, Elasticsearch, Postgres

These pin the local infrastructure. They **supersede** any version or memory
figure in the build prompts (`docs/BUILD_PHASES.md`), which were written against
Elasticsearch 8.x with ~2 GB of RAM.

## Elasticsearch

- Image: `docker.elastic.co/elasticsearch/elasticsearch:9.4.1` (pin this exact
  tag — do not use `:latest`).
- Single node, security disabled for local dev only:
  `discovery.type=single-node`, `xpack.security.enabled=false`,
  `xpack.security.http.ssl.enabled=false`.
- **Container memory limit: 4 GB** via `mem_limit: 4g`.
- **JVM heap: 2 GB** via `ES_JAVA_OPTS=-Xms2g -Xmx2g` — the standard 50%-of-container
  rule. Do not raise the heap above half the container limit.
- `bootstrap.memory_lock=true` with `memlock` ulimits set to unlimited, so the
  heap is never swapped.
- Persist data on a named volume so `make down` does not lose the index.
- Add a healthcheck hitting `/_cluster/health` so `/health` and dependent
  services can wait for readiness.

The canonical `elasticsearch` service block is the one in `docs/INFRA.md`. When
generating or editing `docker-compose.yml`, reproduce that block; do not
improvise different values.

## PostgreSQL

- A current stable Postgres image (for example `postgres:17`) is fine; pin the
  tag. Persist data on a named volume. Add a `pg_isready` healthcheck.

## Client/server version match

- The Python `elasticsearch` client in the project requirements must be a **9.x**
  release so it matches the 9.4.1 server. A major-version mismatch (8.x client
  against a 9.x server) is not supported.
- Hybrid retrieval relies on the native RRF retriever API, which is available in
  Elasticsearch 9.x; the Python RRF fallback still stays in the code for
  portability.

## Host requirements (call these out in the README / RUNBOOK)

- The Docker engine (or the WSL2 VM hosting it) must have enough memory for the
  4 GB Elasticsearch container **plus** Postgres and the API — budget at least
  6–8 GB total.
- The Linux host needs `vm.max_map_count` at 262144 or higher, or Elasticsearch
  will fail to start. On WSL2 this is set on the host side, not in Compose.

## Makefile

- `make up` / `make down` must not pass `-v` (do not destroy the ES and Postgres
  volumes). A separate, clearly named target may exist for a full reset.
- `make corpus` fetches the document corpus from the Elastic GitHub repos (see
  `docs/CORPUS.md`) and must run before `make ingest`. `data/sample_corpus/` is
  gitignored — keep it out of version control.
