---
paths:
  - "app/api/**/*"
  - "app/main.py"
---

# API boundary rules

This is the only layer allowed to depend on FastAPI. It adapts HTTP to the pure
retrieval and generation functions — it does not reimplement their logic.

- Validate every request body and query parameter with a Pydantic model at the
  boundary. Reject malformed input before calling into the core.
- Endpoints **call** `app/retrieval/` and `app/generation/` functions; they must
  not contain retrieval or ranking logic of their own.
- Preserve existing response shapes unless the task explicitly changes the
  contract. `/search`, `/ask`, and the admin endpoints have callers.
- Use the project's standard error format. Do not leak internal exception messages,
  stack traces, or Elasticsearch/Postgres errors to clients.
- `/search` and `/ask` accept an optional `caller_roles` list. Pass it through so
  the retrieval layer can filter chunks by `permissions`. Never return a chunk the
  caller's roles do not cover.
- `/health` must actually check Elasticsearch and PostgreSQL connectivity and
  return 200 only when both are healthy.
- Every `/ask` call must write a `query_log` row (see `app/db/`); flag
  insufficient or low-confidence answers.
- Add or update API contract tests whenever endpoint behavior changes.
- Check authorization and tenant/account scoping for any change that touches data
  access.
