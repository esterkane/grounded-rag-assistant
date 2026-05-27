---
name: rag-debug
description: >-
  Diagnose a wrong, ungrounded, or low-quality answer from grounded-rag-assistant
  by tracing the pipeline from query to retrieval to generation, and classify the
  failure as a retrieval, generation, or grounding problem. Use when a /ask or
  /search result looks wrong or irrelevant, when a citation does not map to a real
  chunk, when the assistant hallucinates, or when the insufficient-evidence path
  fires (or fails to fire) incorrectly.
argument-hint: "[the failing query, and what was wrong with the answer]"
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(python -m app.* *)
  - Bash(curl -s localhost:* *)
  - Bash(make logs *)
---

Diagnose this RAG failure: $ARGUMENTS

This is a diagnosis, not a fix. Trace the pipeline stage by stage and isolate
where it broke.

## Stage 1 — Retrieval

Reproduce the query through retrieval (call `/search`, or the `app.retrieval`
functions directly). Inspect:
- Which chunks came back, with `score` and the method tag (bm25 / vector /
  hybrid / rerank)?
- Were the chunks that *should* answer the query retrieved at all? If not, the
  failure is **retrieval** — the right content never reached the model.
- Did permission filtering wrongly drop a relevant chunk?
- Compare modes: does `bm25` or `vector` alone surface the right chunk while
  `hybrid` buries it? Does rerank help or hurt here?

If the relevant chunk is missing from retrieval entirely, stop here — the fix is
in ingestion (chunking, embeddings, index mapping) or retrieval (RRF weighting,
`k`, rerank), not in generation.

## Stage 2 — Generation

If retrieval did surface the right chunks, inspect generation:
- Was the prompt actually built with those chunks (right `chunk_id`s, right
  `source_url`s, numbered context)?
- Are the citations valid — does each cited `chunk_id` exist in the prompt
  context? Invalid citations point to a citation-validation bug.
- Did the model hallucinate content not in any chunk? That is a **generation /
  grounding** failure — check the prompt's "answer only from context"
  instruction and the defensive parsing.
- Did the insufficient-evidence path fire when it should not have, or fail to
  fire when context truly did not support an answer?
- Does the failure depend on `LLM_PROVIDER` (gemini vs ollama)?

## Output

Return a diagnosis with this shape:

- **Failure stage**: retrieval | generation | grounding | ingestion-upstream
- **Evidence**: the concrete observations (chunks, scores, citations, prompt
  contents) that locate the failure.
- **Root cause hypothesis**: one paragraph.
- **Recommended fix**: where to change code, and what to verify with `/run-eval`
  afterward.
