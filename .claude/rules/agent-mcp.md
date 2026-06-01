---
paths:
  - "app/agent/**/*"
  - "app/mcp/**/*"
---

# Agent & MCP layer rules

These two packages are the Project 2 add-on. They sit on top of Project 1's
retrieval and generation core.

## Reuse, don't reimplement

- Import Project 1's pure functions — `app.retrieval.retriever` and
  `app.generation.answerer` — directly. Do not copy their logic.
- The provider abstraction (`app.generation.providers`) is reused as-is for
  both the answerer call inside the MCP tool and the LLM the LangGraph nodes
  use for planning and reflection.

## MCP tool design

- Tool descriptions are long and specific: what the tool does, when to use
  it, when NOT to use it, inputs, outputs, edge cases, failure modes.
- Errors are structured: `{errorCategory, isRetryable, message, details}`,
  with `isError: true` on the response. Categories: transient | validation |
  permission | business.
- Never leak internal stack traces or ES/Postgres errors into a tool result.
- Filter before returning. Do not dump entire ES responses or full corpora;
  return the smallest structured shape that supports the next agent decision.

## Agent boundaries

- `app/agent/` is importable without HTTP — the graph and nodes can be
  exercised by tests and the CLI directly. The only place FastAPI touches
  this package is the `/agent_ask` endpoint in `app/api/`.
- Honor the insufficient-evidence contract from Project 1: if accumulated
  context doesn't support an answer and max_hops is exhausted, return the
  structured insufficient-evidence response. Never hallucinate.
- Bound the agent: a hard `max_hops` limit (default 2, configurable). The
  reflect node may not loop forever.

## Observability

- Every MCP tool call emits an OTel span; trace IDs propagate to the
  underlying retriever/answerer (already instrumented).
- Every LangGraph node emits a span as a child of the incoming trace.
- Token and cost recording extends the existing query_log conventions.
