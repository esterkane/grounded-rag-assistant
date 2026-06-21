# Project guide for Claude Code — grounded-rag-assistant

## Project intent

This repository builds a production-style **RAG (retrieval-augmented generation)
assistant** over Elasticsearch and AI-search technical documentation. It answers
questions strictly grounded in retrieved documentation, with per-claim citations
and an explicit "insufficient evidence" path. It is greenfield Python, built in
six sequential phases.

Main stack:
- Runtime: Python 3.11
- API framework: FastAPI (+ uvicorn)
- Search: Elasticsearch **9.x** (pin **9.4.1**), self-hosted single node — used
  for **both** BM25 and vector search. There is no separate vector database.
  The Elasticsearch container is given a **4 GB memory limit** with a 2 GB JVM
  heap. Exact service config is in `.claude/rules/infra.md` and `docs/INFRA.md`.
- Application data: PostgreSQL
- Embeddings: local `sentence-transformers`, default model `BAAI/bge-small-en-v1.5`
- LLM generation: provider-abstracted — `gemini` (`google-genai`, `gemini-2.5-flash`,
  free tier) and `ollama` (local). Selected by the `LLM_PROVIDER` env var.
  (`gemini-2.0-flash` is deprecated and shuts down 2026-06-01.)
- Lint/format: `ruff`. Tests: `pytest`. Local infra: Docker Compose.

Important entry points:
- FastAPI app + `/health`: `app/main.py`
- HTTP routes (`/search`, `/ask`, admin/review): `app/api/`
- Retrieval core (BM25, vector, hybrid RRF, rerank): `app/retrieval/`
- Generation core (provider abstraction, grounded answerer): `app/generation/`
- MCP agent-access tools (FastMCP server reusing the core): `app/mcp/` (see `docs/mcp.md`)
- Ingestion (loaders, chunking, embedder, indexer): `app/ingestion/`
- Evaluation harness: `app/eval/`
- Database + migrations: `app/db/`
- Observability (logging, tracing, cost): `app/observability/`
- Tests: `tests/`  · Sample corpus: `data/sample_corpus/`  · Gold set: `data/gold/`
- Build phase definitions: `docs/BUILD_PHASES.md`
- Infrastructure spec: `docs/INFRA.md`  · Corpus spec: `docs/CORPUS.md`

The document corpus is fetched from public Elastic GitHub repositories
(`elastic/elasticsearch-labs`, `elastic/docs-content`) by a fetch script
(`make corpus`), not scraped from the docs website. `data/sample_corpus/` is
gitignored and reproducible. See `docs/CORPUS.md`.

## Architecture (5 lines)

1. A single FastAPI service (`app/api/`) over Elasticsearch 9.4.1 (BM25 **and** dense-vector kNN, RRF-fused — no separate vector DB) and PostgreSQL 16 (query logs, feedback).
2. Local `sentence-transformers` embeddings (`BAAI/bge-small-en-v1.5`); generation is provider-abstracted — `gemini` free tier or local `ollama`, with per-request fallback.
3. Retrieval (`app/retrieval/`) and the grounded answerer (`app/generation/answerer.py`) are FastAPI-free importable functions; the MCP agent-access layer (`app/mcp/`, "Project 2") reuses them unchanged — a thin FastMCP server exposing `retrieve_chunks` / `answer_with_citations` / `list_documents` with structured errors (the LangGraph orchestration over those tools is partially built).
4. Ingestion (`app/ingestion/`) chunks the fetched Elastic-docs corpus with deterministic hash-based chunk IDs (idempotent re-ingest); the eval harness (`app/eval/`) guards retrieval MRR against regression.
5. Cross-cutting observability (`app/observability/`): JSON logs with trace ids, OpenTelemetry spans, and per-`/ask` token + cost accounting surfaced at `/metrics`.

## Invariants — never break

- **Provenance on every chunk / grounded answers.** Every chunk carries `chunk_id` + `source_url`; every citation in an `/ask` answer must validate against a chunk that was actually retrieved. No valid citation → downgrade to the insufficient-evidence path. Never emit an ungrounded claim.
- **Determinism & reproducibility.** Chunk IDs are deterministic hashes — re-ingest stays idempotent (same corpus → same chunk count, no duplicates). The eval harness stays reproducible; when the agent/planner layer (Project 2) lands, its node sequence must be deterministic for a fixed input.
- **Quality gates stay green.** `ruff check .`, `pytest`, and `python -m app.eval` (hybrid MRR ≥ `EVAL_HYBRID_MRR_THRESHOLD`, currently `0.38`) must all pass. Lower the threshold only after investigating a *real* regression. No static type-checker is configured — `ruff` + pydantic runtime validation are the gate.
- **Hybrid retrieval only.** Search fuses BM25 + vector via RRF. No keyword-only or vector-only search endpoint.
- **The FastAPI-free core boundary.** No `fastapi` imports in `app/retrieval/` or `app/generation/answerer.py` (enforced by `.claude/rules/retrieval-generation.md`). The MCP layer (`app/mcp/`) is the agent-access surface: thin wrappers that reuse the FastAPI-free core, return the structured error contract (`{isError, errorCategory, isRetryable, message, details}`), and never leak stack traces (`.claude/rules/agent-mcp.md`).
- **No secrets in git.** Secrets live only in the gitignored `.env`; `.env.example` documents every variable with an empty value. `GEMINI_API_KEY` is injected at runtime, never committed. Zero paid services (no Pinecone, Elastic Cloud, ELSER, or paid LLM keys).
- **Infra is pinned.** Elasticsearch `9.4.1`, single node; the Python `elasticsearch` client stays on the 9.x line. Never `docker compose down -v` — it wipes the ES and Postgres volumes.

## Definition of done

- [ ] `make test` (pytest) passes — every behaviour change has a test.
- [ ] `make lint` (`ruff check .`) passes and `ruff format .` is applied.
- [ ] `make eval` passes the MRR regression guard when retrieval / ingestion / eval changed.
- [ ] Provenance intact: citations validate against retrieved chunks and the insufficient-evidence path still fires.
- [ ] CI (`.github/workflows/ci.yml`: lint + tests + eval against ES + Postgres) is green.
- [ ] README / `docs/` updated when commands, services, env vars, or architecture changed.
- [ ] MCP tools changed (`app/mcp/`) → `docs/mcp.md` and the MCP tests (`tests/test_mcp_tools.py`, `tests/test_mcp_server.py`) are updated to match the tool signatures, error contract, and outputs.
- [ ] No secrets added to git; `.env.example` updated if a new variable was introduced.

## Commands

Use these unless the user gives different instructions:

- Start local stack (ES + Postgres + API): `make up`
- Stop the stack: `make down`  *(never run `docker compose down -v` — it wipes the ES and Postgres volumes)*
- Tail logs: `make logs`
- Run all tests: `make test`
- Run one test file or case: `pytest tests/<path>.py -k <name>`
- Lint: `make lint`  (or `ruff check .`)
- Format: `ruff format .`
- Ingest the sample corpus: `make ingest`  (or `python -m app.ingestion.run --path data/sample_corpus`)
- Run the evaluation harness: `make eval`
- End-to-end demo: `make demo`
- Start the MCP agent-access server (stdio): `make mcp-server`  (or `python -m app.mcp.server`; see `docs/mcp.md`)

## Working rules

### Build discipline (this project is built in phases)
- The project is built in **six sequential phases**, defined in `docs/BUILD_PHASES.md`.
- Work **one phase at a time**. Do not start a phase until the previous phase's
  acceptance criteria pass.
- **Do not exceed the scope of the current phase.** Agentic drift on over-scoped
  tasks is the main failure mode here.
- Commit at the end of each phase using the **exact commit message** the phase spec
  gives (for example, `phase 0: project scaffold`).
- Use the `/implement-phase` skill to run a phase.

### The single most important architectural constraint
- Code in `app/retrieval/` and in `app/generation/answerer.py` must stay **free of
  any FastAPI coupling** — no `fastapi` imports, no request/response objects, no
  dependency-injection decorators. These must be plain, importable functions and
  data models, because a later project ("Project 2") wraps them as MCP tools and a
  LangGraph layer **without rework**. The `.claude/rules/retrieval-generation.md`
  rule enforces this for matching files; honor it.

### General
- For broad, architectural, multi-file, or ambiguous tasks: start in **plan mode**.
- For simple, well-scoped, single-file fixes: execute directly.
- Prefer `Grep` and `Glob` before reading many files.
- Inspect nearby implementation and tests before editing.
- Make the smallest coherent change that satisfies the request.
- Add or update tests for every behavior change.
- Run the narrowest relevant test first, then `make test` / `make lint`.
- **Zero paid services.** No Pinecone, no Elastic Cloud, no ELSER, no paid LLM keys.
  Everything runs locally via Docker or free-tier APIs.
- **Infrastructure is pinned.** Elasticsearch is `9.4.1`, single node, security
  disabled for local dev, with a 4 GB container memory limit and a 2 GB JVM heap.
  The Python `elasticsearch` client must be a 9.x release to match the server.
  Follow `.claude/rules/infra.md` exactly when creating or editing
  `docker-compose.yml`.
- Never edit secrets (`.env`, `secrets/`), generated files, lockfiles, applied DB
  migrations, or destructive scripts unless explicitly instructed.
- Before major changes, explain the risks and wait for approval.
- After changes, summarize files changed, tests run, and remaining risks.

## Review criteria

When reviewing code, report only actionable issues:
- Correctness bugs
- Security or data-leak risks (including chunk-permission filtering and prompt-injection
  surfaces in retrieved content)
- Broken tests, or missing regression coverage for changed behavior
- API/contract incompatibilities (`/search`, `/ask`, admin endpoints)
- Grounding failures: a citation that does not map to a retrieved chunk, or a
  hallucinated answer where the insufficient-evidence path should have fired
- Violations of the FastAPI-free constraint in `app/retrieval/` or `app/generation/`
- Ingestion that is not idempotent (re-ingest changes chunk count or creates duplicates)
- Performance regressions with a concrete cause

Skip low-value style comments unless they affect correctness, maintainability,
accessibility, or security.
