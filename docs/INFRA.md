# Infrastructure reference — `grounded-rag-assistant`

This file is the **canonical specification** for the local infrastructure. When
Phase 0 generates `docker-compose.yml`, it must reproduce the Elasticsearch
service below. These values supersede the "Elasticsearch 8.x" and "~2 GB RAM"
figures in the original build prompts.

## Pinned versions

- Elasticsearch: **9.4.1** (`docker.elastic.co/elasticsearch/elasticsearch:9.4.1`)
- PostgreSQL: a current stable tag, e.g. `postgres:17`
- Python `elasticsearch` client: a **9.x** release (must match the 9.4.1 server)

## Elasticsearch container

- Memory limit: **4 GB** (`mem_limit: 4g`)
- JVM heap: **2 GB** (`-Xms2g -Xmx2g`) — 50% of the container limit
- Single node, security disabled (local dev only)
- Memory locked so the heap is never swapped
- Data on a named volume; healthcheck on `/_cluster/health`

## Canonical `docker-compose.yml` Elasticsearch + Postgres services

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:9.4.1
    container_name: grag-elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.security.http.ssl.enabled=false
      - bootstrap.memory_lock=true
      - "ES_JAVA_OPTS=-Xms2g -Xmx2g"
    ulimits:
      memlock:
        soft: -1
        hard: -1
    mem_limit: 4g
    ports:
      - "9200:9200"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -fs http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 10s
      retries: 12

  postgres:
    image: postgres:17
    container_name: grag-postgres
    environment:
      - POSTGRES_USER=${POSTGRES_USER:-grag}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-grag}
      - POSTGRES_DB=${POSTGRES_DB:-grag}
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-grag}"]
      interval: 10s
      timeout: 5s
      retries: 10

  api:
    build: .
    container_name: grag-api
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      elasticsearch:
        condition: service_healthy
      postgres:
        condition: service_healthy

volumes:
  es_data:
  pg_data:
```

Notes:
- `mem_limit` is the simple, reliable way to cap a container's memory under plain
  `docker compose up`. Keep the JVM heap at half of it.
- The `api` service block is indicative; Phase 0 may adjust its build context and
  command, but the `depends_on ... service_healthy` gating should stay so the API
  waits for Elasticsearch and Postgres.

## Host prerequisites

The Docker engine — or, on Windows, the WSL2 VM that backs Docker Desktop — must
have enough memory for the 4 GB Elasticsearch container plus Postgres plus the
API. **Budget at least 6–8 GB** for the Docker/WSL VM.

Elasticsearch also needs the host kernel setting `vm.max_map_count >= 262144`, or
it will fail to start. This is set on the host, not in Compose:

- Linux: `sudo sysctl -w vm.max_map_count=262144` (and add it to
  `/etc/sysctl.conf` to persist).
- WSL2: set it inside the WSL distro the same way, or persist it via WSL config.
  See the implementation steps.
