# Build phases

The six sequential build phases for `grounded-rag-assistant` are defined in the
**codex prompts file** (`project1-codex-prompts.md`).

**Action required:** copy the contents of `project1-codex-prompts.md` into this
file (`docs/BUILD_PHASES.md`), replacing this placeholder — but keep the
"Infrastructure overrides" section below at the top, above the pasted prompts.

## Infrastructure overrides (these supersede the build prompts)

The original build prompts were written against Elasticsearch 8.x with ~2 GB of
RAM. The current project uses:

- **Elasticsearch `9.4.1`** — image `docker.elastic.co/elasticsearch/elasticsearch:9.4.1`.
- **A 4 GB memory limit** on the Elasticsearch container, with a **2 GB JVM heap**.
- The Python `elasticsearch` client must be a **9.x** release to match.

Wherever a phase prompt says "Elasticsearch 8.x" or "~2 GB RAM", use the values
above instead. The exact `docker-compose.yml` service block is in `docs/INFRA.md`
and is enforced by `.claude/rules/infra.md`. Phase 0 must build against these.

## Corpus override (Phase 1)

The original Phase 1 prompt has you hand-place 3–6 sample docs in
`data/sample_corpus/`. Instead, the corpus is built from public Elastic GitHub
repositories via a fetch script. Phase 1 must additionally:

- Implement `app/ingestion/fetch_corpus.py`, wired to a `make corpus` target,
  that shallow-clones the source repos, selects topic-relevant `.md` files, and
  writes them into `data/sample_corpus/` with git-derived front-matter.
- Treat `data/sample_corpus/` as **gitignored** and reproducible — the repo
  contains the fetch script, not Elastic's content.

Full specification — source repos, topic filter, front-matter mapping, and
licensing notes — is in `docs/CORPUS.md`. The `make corpus` step runs before
`make ingest`.

---

# Project 1 — `grounded-rag-assistant` — Codex prompts

A production-style RAG assistant over Elasticsearch and AI-search technical
documentation. Greenfield, Python. Replaces and consolidates the archived
`elastic-repo-inventory` and `elastic-ai-search-decision-lab`.

## How to use this file

- Run the phases **in order, one at a time, as separate Codex tasks**.
- After each phase, verify the **Acceptance criteria** before starting the next.
- Let Codex commit at the end of each phase.
- Do not paste multiple phases at once — agentic tools drift when scope is too large.

## Before Phase 0 — reuse prior work as data

From the repos you are about to archive, copy these into the new repo (data only,
no code):

- From `elastic-ai-search-decision-lab`: any practitioner-question / judgment-set
  files → these become the Phase 4 gold evaluation set.
- From `elastic-repo-inventory`: any saved Elasticsearch / AI-search documentation
  used as a corpus → these become the Phase 1 sample corpus.

If those files are messy, just keep them aside; Phase 1 and Phase 4 prompts also
describe how to generate fresh sample data.

---

## Phase 0 — Scaffold

```
You are setting up a new project "grounded-rag-assistant", a production-style RAG
assistant over Elasticsearch and AI-search technical documentation.
This is phase 0 of 6: scaffolding ONLY. Do not implement retrieval or generation yet.

Constraints (apply to EVERY phase):
- Zero paid services. No Pinecone, no Elastic Cloud, no ELSER, no paid LLM keys
  assumed. Everything runs locally via Docker or free-tier APIs only.
- Python 3.11, FastAPI.
- Elasticsearch 8.x self-hosted single node for BOTH BM25 and vector search.
  No separate vector DB.
- PostgreSQL for application data.
- Embeddings: local sentence-transformers, default model BAAI/bge-small-en-v1.5.
  No API for embeddings.
- LLM generation: provider-abstracted, two providers — "gemini" (google-genai,
  gemini-2.5-flash, free tier) and "ollama" (local). Default = gemini, configurable
  via env. (gemini-2.0-flash was retired by Google on 2026-03-03.)
- IMPORTANT: a later phase will add a LangGraph + MCP layer on top of this repo.
  Keep retrieval and generation as cleanly separated, importable functions with
  no FastAPI coupling, so they can later be exposed as MCP tools without rework.

Deliverables:
1. Repo structure: app/{api,ingestion,retrieval,generation,eval,db,observability},
   tests/, docker/, docs/, data/sample_corpus/, data/gold/.
2. docker-compose.yml: elasticsearch (single node, security disabled for local dev),
   postgres, api.
3. requirements/pyproject with: fastapi, uvicorn, elasticsearch, sentence-transformers,
   psycopg[binary], pydantic, pydantic-settings, google-genai, httpx, pytest, ruff.
4. app/config.py via pydantic-settings reading .env; include a fully documented
   .env.example.
5. app/main.py: FastAPI app + /health endpoint that checks ES and Postgres
   connectivity.
6. Makefile targets: up, down, logs, test, lint, ingest, eval.
7. README.md skeleton: Overview, Architecture, Stack, Quickstart (detail TBD).

Acceptance criteria:
- `docker compose up` starts ES, Postgres, API with no errors.
- GET /health returns 200 with both ES and Postgres healthy.
- `make lint` and `make test` run (one placeholder passing test is fine).

Do not exceed this scope. Commit: "phase 0: project scaffold".
```

---

## Phase 1 — Ingestion and indexing

```
Phase 1 of 6: ingestion and indexing. The phase-0 scaffold exists.
Goal: ingest documents into Elasticsearch with stable IDs, provenance/version
metadata, and keyword + vector fields.

Requirements:
1. Loaders in app/ingestion/ for Markdown (.md) and PDF (.pdf, use pypdf). Add
   3-6 realistic sample docs to data/sample_corpus/ — Elasticsearch / AI-search
   documentation saved as Markdown, or generated technical KB articles — each with
   front-matter: title, source_url, version, last_updated.
2. Chunking: header-aware for Markdown (split on headings, keep the heading path);
   size-based with overlap for PDF. ~500-800 tokens per chunk, ~100 token overlap.
3. Stable chunk IDs: deterministic hash of (source_path + heading_path + chunk_index)
   so re-ingest is idempotent.
4. Per-chunk metadata: chunk_id, doc_id, source_url, title, heading_path, version,
   last_updated, ingested_at, permissions (list of role strings, default ["public"]).
5. app/ingestion/embedder.py wrapping sentence-transformers (bge-small-en-v1.5),
   batched, normalized.
6. ES index "rag_chunks": mapping with text fields (content, title) for BM25,
   keyword fields for metadata, and a dense_vector field (correct dims, index:true,
   similarity: cosine). Idempotent create-index function.
7. Bulk upsert chunks keyed by chunk_id.
8. CLI: `python -m app.ingestion.run --path data/sample_corpus`, wired to
   `make ingest`. Print a summary: docs, chunks, failures.

Acceptance criteria:
- Running ingest twice yields the same chunk count, no duplicates.
- A test queries ES and asserts a known chunk exists with a non-empty vector.

Commit: "phase 1: ingestion and indexing".
```

---

## Phase 2 — Hybrid retrieval

```
Phase 2 of 6: hybrid retrieval. Phases 0-1 exist; rag_chunks is populated.
Goal: retrieval combining BM25 and vector search with RRF, plus optional reranking.

Requirements:
1. app/retrieval/retriever.py — pure, importable functions with NO FastAPI
   dependency (a later phase exposes these as MCP tools):
   - bm25_search(query, k): ES match over content + title.
   - vector_search(query, k): embed query with the bge model, ES kNN on dense_vector.
   - hybrid_search(query, k): use Elasticsearch native RRF (retriever/rrf API).
     If the ES version lacks it, fall back to a Python RRF implementation —
     detect automatically.
2. app/retrieval/reranker.py: optional local cross-encoder
   (cross-encoder/ms-marco-MiniLM-L-6-v2), toggled by config flag RERANK_ENABLED;
   reranks fused top-N to top-k.
3. Each result carries: chunk_id, score, content, all metadata, and which method(s)
   retrieved it.
4. API: POST /search accepting {query, k, rerank?}. Support an optional caller_roles
   list and filter out chunks whose permissions don't intersect.
5. Tests: unit test RRF fusion with fixed inputs; integration test that /search
   returns relevant results for a sample-corpus query.

Acceptance criteria:
- /search returns relevant chunks with metadata and method tags.
- Toggling RERANK_ENABLED changes ordering without errors.
- Permissions filter excludes chunks the caller's roles don't cover.

Commit: "phase 2: hybrid retrieval with RRF and optional rerank".
```

---

## Phase 3 — Grounded generation with citations

```
Phase 3 of 6: grounded answer generation.
Goal: answers strictly grounded in retrieved chunks, with per-claim citations and
an explicit "insufficient evidence" path.

Requirements:
1. Provider abstraction in app/generation/providers/: base LLMProvider interface
   with generate(messages, **opts). Implement GeminiProvider (google-genai,
   gemini-2.5-flash, reads GEMINI_API_KEY) and OllamaProvider (local HTTP).
   Factory selects via LLM_PROVIDER env. The app must run end to end with either
   provider.
2. app/generation/answerer.py — importable, no FastAPI dependency: takes a query,
   runs phase-2 retrieval, builds a prompt with numbered context chunks each
   labeled with chunk_id and source_url. Instructs the model to answer ONLY from
   context, attach a citation (chunk_id) to each claim, and return an explicit
   insufficient-evidence answer when context doesn't support one — never guess.
3. Returns a structured object: answer text, claims (each with cited chunk_ids),
   sources used, and an answered/insufficient boolean.
4. Validate output: every citation must reference a chunk_id that was actually in
   context — drop or flag invalid ones. Use a Pydantic model, parse defensively,
   retry once on parse failure.
5. API: POST /ask accepting {query, k, rerank?, caller_roles?}.
6. Tests: an answerable query returns valid citations; an off-topic query returns
   the insufficient-evidence response.

Acceptance criteria:
- /ask produces cited answers; every citation maps to a real retrieved chunk.
- Off-corpus questions yield the insufficient-evidence path, not a hallucination.
- LLM_PROVIDER works set to both gemini and ollama.

Commit: "phase 3: grounded generation with citations".
```

---

## Phase 4 — Evaluation harness

```
Phase 4 of 6: evaluation harness.
Goal: a reproducible eval suite for retrieval and answer quality, runnable in CI.

Requirements:
1. Gold set data/gold/queries.jsonl, ~15-25 items: query, relevant_chunk_ids
   (or doc_ids), expected_answerable (bool), notes. Build it against the sample
   corpus. If practitioner-question / judgment-set files were carried over from
   the old decision-lab repo, adapt them into this format instead of writing
   from scratch.
2. Retrieval metrics in app/eval/: Precision@k, Recall@k, MRR, nDCG@k — computed
   over the gold set for bm25, vector, hybrid, and hybrid+rerank; print a
   comparison table.
3. Citation accuracy: for answerable queries, run /ask and check citations point
   to gold-relevant chunks; report citation precision.
4. Insufficient-evidence accuracy: for non-answerable items, check the insufficient
   flag is set.
5. Latency: p50/p95 for retrieval and for full /ask.
6. Output a JSON report + human-readable summary to eval_reports/ with a timestamp.
7. Regression test: a pytest test failing if hybrid MRR drops below a configurable
   threshold (set the threshold from the current baseline).
8. Wire to `make eval`.

Acceptance criteria:
- `make eval` prints a metrics table across all retrieval modes and saves a report.
- The regression test passes now and would fail on a deliberate degradation.

Commit: "phase 4: evaluation harness".
```

---

## Phase 5 — Review UI and feedback

```
Phase 5 of 6: admin/review UI and feedback capture.
Goal: capture failed/low-confidence queries and human feedback.

Requirements:
1. Postgres schema (migrations in app/db/): query_log (id, query, answer, answered,
   latency_ms, provider, retrieval_mode, created_at) and feedback (id,
   query_log_id, rating, correction_text, reviewer, created_at).
2. Every /ask call writes a query_log row; insufficient/low-confidence answers
   are flagged.
3. Admin API: list query logs with filters (flagged only, date range); get one
   log with its retrieved chunks; submit feedback (up/down + optional correction).
4. Lightweight review UI: FastAPI + Jinja2 templates + vanilla JS or HTMX — NO
   Node frontend, no build step. Pages: a queue of flagged/failed queries; a detail
   page showing query, retrieved chunks, generated answer + citations, and a
   feedback form.
5. Tests: posting feedback persists; the flagged-queue endpoint returns only
   flagged items.

Acceptance criteria:
- Asking a question then opening the review UI shows that query; feedback persists.
- The flagged queue isolates failed/low-confidence queries.

Keep it minimal and server-rendered. Commit: "phase 5: review UI and feedback".
```

---

## Phase 6 — Observability, CI, deployment docs

```
Phase 6 of 6: observability, cost tracking, CI, deployment docs.
Goal: make the project look production-ready and reproducible.

Requirements:
1. Structured JSON logging across the app with a trace id propagated through
   retrieval and generation.
2. Tracing: instrument retrieval and generation with the OpenTelemetry SDK.
   Default exporter = console; allow an OTLP endpoint via env. Add an optional,
   profile-gated Jaeger service to docker-compose (off by default).
3. Cost + token tracking: per /ask, record LLM token counts and an estimated cost
   from a static public price table (log the would-be cost even though gemini
   free tier / ollama cost nothing). Store on query_log; expose /metrics
   summarizing totals, averages, p50/p95 latency.
4. GitHub Actions: on push/PR run ruff, pytest, and `make eval` against the sample
   corpus (ES + Postgres as service containers); upload the eval report as an
   artifact.
5. docs/: ARCHITECTURE.md (with diagram), RUNBOOK.md (start/stop, re-ingest,
   common failures + fixes, backup/restore), DEPLOYMENT.md (Docker deploy, env
   vars, resource needs — note ES needs ~2GB RAM and explain the options).
   Finalize README with quickstart, screenshot placeholders, and a demo script
   (exact command/query sequence).
6. Make target `demo`: ingests the sample corpus and runs 3 example questions
   end to end.

Acceptance criteria:
- CI passes on a clean checkout: lint, tests, eval all green.
- /metrics returns latency, token, and cost summaries.
- Traces appear in the console (and Jaeger when the profile is enabled).
- A new user can follow README quickstart and reach a working /ask quickly.

Commit: "phase 6: observability, CI, and deployment docs".
```

---

## After Phase 6

- Archive `elastic-repo-inventory` and `elastic-ai-search-decision-lab` on GitHub
  (Settings → Archive) and unpin them, so the profile shows one retrieval flagship
  instead of three.
- Write the README in the honest, scoped voice of `kcs-control-plane` — include a
  "Not implemented yet" section. Avoid "control plane", "lab", "release-intelligence",
  and noun-phrase bullet fragments.
- When ready, ask for the "Project 2" prompts: the LangGraph + MCP layer added on
  top of this same repo, reusing the Phase 2 retriever and Phase 3 answerer
  functions as MCP tools.

## Practical setup notes

- Get a free Gemini API key from Google AI Studio (no card required).
- To run fully offline, install Ollama and set `LLM_PROVIDER=ollama`.
- ES needs ~2GB RAM; if `docker compose up` fails, raise Docker's memory limit.
