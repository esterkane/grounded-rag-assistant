---
paths:
  - "app/retrieval/**/*"
  - "app/generation/**/*"
---

# Retrieval & generation core rules

These two packages are the reusable heart of the project. A later project wraps
them as **MCP tools** and drives them from a **LangGraph** layer. Keeping them
clean now avoids a painful rewrite later.

## The non-negotiable rule: no FastAPI coupling

- Do **not** import `fastapi`, `starlette`, or any web-framework symbol in these
  files.
- Do **not** accept or return `Request`/`Response` objects, and do not use
  `Depends`, route decorators, or framework-specific exceptions.
- Public functions must be **plain, importable, synchronous-or-async functions**
  that take ordinary arguments (strings, ints, lists, Pydantic models) and return
  ordinary data (Pydantic models or dataclasses).
- The FastAPI layer in `app/api/` is the only place allowed to call these
  functions and adapt them to HTTP. Logic lives here; HTTP adaptation lives there.

If a task seems to need a FastAPI object in these files, stop and surface the
conflict instead of importing it.

## Retrieval (`app/retrieval/`)

- `retriever.py` exposes `bm25_search`, `vector_search`, and `hybrid_search` as
  pure functions. `hybrid_search` uses Elasticsearch native RRF when available and
  **auto-detects** and falls back to a Python RRF implementation otherwise.
- Every result object carries: `chunk_id`, `score`, `content`, the full chunk
  metadata, and a tag for **which method(s)** retrieved it.
- `reranker.py` (optional cross-encoder) is gated by the `RERANK_ENABLED` config
  flag. Toggling it must change ordering without errors and without changing the
  result schema.
- Permission filtering (drop chunks whose `permissions` do not intersect the
  caller's roles) is a retrieval-layer concern and must not be skipped.

## Generation (`app/generation/`)

- Provider abstraction lives in `providers/`: a base `LLMProvider` interface plus
  `GeminiProvider` and `OllamaProvider`. A factory selects the provider via
  `LLM_PROVIDER`. No provider-specific code may leak into `answerer.py`.
- `answerer.py` builds prompts with **numbered context chunks**, each labeled with
  its `chunk_id` and `source_url`, and instructs the model to answer **only** from
  context.
- Every citation in the output must reference a `chunk_id` that was actually placed
  in the prompt context. Validate this; drop or flag invalid citations.
- The structured answer object must include an explicit `answered` / `insufficient`
  boolean. When context does not support an answer, return the
  insufficient-evidence response — never guess or fabricate.
- Parse model output defensively with a Pydantic model and retry once on a parse
  failure.

## Tests for these packages

- Unit-test RRF fusion with fixed inputs (no live ES needed).
- Keep retrieval/generation unit tests free of FastAPI's test client; call the
  functions directly. That is the point of the layering.
