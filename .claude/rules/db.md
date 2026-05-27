---
paths:
  - "app/db/**/*"
---

# Database rules

Application data lives in PostgreSQL. Schema changes go through migrations.

- Never hand-edit a migration that has already been applied. To change schema,
  add a new migration.
- Treat migrations as off-limits unless the task explicitly asks for a schema
  change; flag the risk before running one.
- Core tables (introduced in Phase 5):
  - `query_log` — `id`, `query`, `answer`, `answered`, `latency_ms`, `provider`,
    `retrieval_mode`, `created_at`. Phase 6 also records token counts and an
    estimated cost on this table.
  - `feedback` — `id`, `query_log_id`, `rating`, `correction_text`, `reviewer`,
    `created_at`.
- Every `/ask` call writes a `query_log` row. Insufficient or low-confidence
  answers must be flagged so the review UI can isolate them.
- Keep DB access importable and free of FastAPI coupling, consistent with the
  retrieval/generation layering.
- Add or update tests when schema or query behavior changes; integration tests
  need a running Postgres (`make up`).
