---
name: debug-agent
description: >-
  Diagnose a wrong, looping, hallucinated, or insufficient-evidence-misfiring
  agent run in grounded-rag-assistant Project 2 by tracing the LangGraph
  execution and classifying the failure as a plan / retrieve / reflect /
  answer node problem, an MCP tool problem, or an underlying retriever or
  generation problem. Use when an agent run looks wrong, the agent hits max_hops
  without answering questions it should have answered, the agent hallucinates,
  or the insufficient-evidence path fires when it should not (or vice versa).
argument-hint: "[the failing query, and what was wrong with the agent's run]"
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(make agent *)
  - Bash(python -m app.agent* *)
  - Bash(curl -s localhost:* *)
  - Bash(make logs *)
---

Diagnose this agent failure: $ARGUMENTS

This is a layered failure space — five places a problem can live. Isolate it
from outer to inner.

## Layer 1 — Plan node

Did the plan node produce sensible sub-queries? Common failures:

- **Over-decomposition.** A simple lookup question split into 3+ sub-queries
  the corpus answers in one place. Often a planning-prompt issue, not a
  retrieval issue.
- **Under-decomposition.** A multi-part question issued as one literal
  sub-query, missing one of its facets.
- **Drifted sub-queries.** Sub-queries that look related but lose the
  original intent — common when the planner LLM is rate-limited or weak.

If the sub-queries themselves are wrong, the rest of the trace is downstream
noise. Fix the planner, then re-run.

## Layer 2 — Retrieve hops (MCP tool calls)

For each hop, did the `retrieve_chunks` MCP tool return relevant chunks?

- If the tool returned an `isError: true` response — what category? Transient
  (re-run); validation (the agent passed bad inputs); business (permission
  filtering dropped all results).
- If the tool returned chunks but they were irrelevant — this is a Project 1
  retrieval issue, not an agent issue. Drop to `/rag-debug` on the failing
  sub-query directly.
- If two hops returned overlapping chunks with little new — the dedup logic
  may be working, but the planner is asking variations of the same question.

## Layer 3 — Reflect node

Did reflect make the right routing call?

- If it routed to `answer` when retrieval was clearly insufficient → the
  reflect prompt is too eager. The agent will end up hallucinating in the
  answer node.
- If it routed to `retrieve` repeatedly without convergence and hit
  `max_hops` → the reflect prompt is too cautious, or the planner can't
  produce a useful follow-up sub-query.
- If `max_hops` was hit and the agent terminated *without* producing the
  insufficient-evidence response, that is a contract regression — the
  agent must take the insufficient-evidence path in this case.

## Layer 4 — Answer node

If reflect routed correctly but the final answer is wrong:

- Was `answer_with_citations` called with the accumulated chunks, or did
  state get truncated?
- Does every cited `chunk_id` exist in the accumulated retrieved set?
  Invalid citations → citation-validator regression (Project 1 answerer
  contract).
- Did the answerer hallucinate content not in any chunk? → grounding
  failure; check the prompt the underlying answerer built.

## Layer 5 — Provider / fallback

- Which provider produced the answer? Did the Gemini→Ollama fallback trip
  in the middle of the run? Mixed providers across hops can produce
  inconsistent behavior.
- Was the planner using one provider and the answerer another? That is
  fine, but worth noting in the diagnosis.

## Output

- **Failure layer**: plan | retrieve | reflect | answer | provider | project-1
- **Evidence**: the concrete observations (sub-queries, chunks, scores,
  routing decisions, citations, provider) that locate the failure.
- **Root cause hypothesis**: one paragraph.
- **Recommended fix**: where to change code, and what to verify with
  `/run-agent` and `make agent_eval` afterward.
- **Project-1 follow-up?**: if the root cause is in Project 1's retriever,
  answerer, or citation validator, say so plainly — Project 2 should not
  paper over Project 1 bugs.
