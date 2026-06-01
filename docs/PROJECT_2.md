# Project 2 — `grounded-rag-assistant` — LangGraph + MCP layer

Adds an agentic layer on top of the Project 1 RAG service: the Phase 2 retriever
and Phase 3 answerer functions get exposed as **MCP tools**, and a **LangGraph**
agent orchestrates them — adding query planning, multi-step retrieval, and
self-reflection on insufficient evidence — while keeping the existing HTTP API
intact.

Same repository as Project 1. Same six-phase discipline.

## Why this is a separate project, not Phase 7

The split exists because Project 1 left a clean architectural boundary: every
function under `app/retrieval/` and `app/generation/answerer.py` was deliberately
kept free of FastAPI coupling so it could be wrapped as MCP tools without
rewriting. Project 2 cashes in that constraint. If Project 1's first phase here
struggles to import those functions cleanly, that's a Project 1 bug; it
shouldn't.

## How to use this file

- Run the phases **in order, one at a time, as separate Claude Code tasks**.
- After each phase, verify the **Acceptance criteria** before starting the next.
- Let Claude Code commit at the end of each phase. **Use a feature branch per
  phase**, open a PR, let CI go green, merge — the workflow Project 1's PR work
  established. No more direct commits to `main`.
- Do not paste multiple phases at once.

## Constraints (apply to EVERY phase)

- Zero paid services. The agent uses the same provider abstraction as Project 1
  (`LLM_PROVIDER=gemini` default with Ollama fallback). No paid LLM keys.
- Python 3.11. Reuse the existing virtualenv and dependency setup.
- Reuse Project 1's pure functions verbatim — `app/retrieval/retriever.py`,
  `app/generation/answerer.py`, the provider abstraction. **Do not** copy or
  rewrite them; import them.
- The new code lives in `app/mcp/` (the MCP server) and `app/agent/` (the
  LangGraph workflow). The existing `app/api/`, `app/retrieval/`, and
  `app/generation/` packages stay untouched, except for adding the agentic
  endpoint in Phase 4.
- The FastAPI-free rule still applies to `app/retrieval/` and
  `app/generation/answerer.py`. The new `app/agent/` and `app/mcp/` packages may
  use other frameworks, but they too must be importable without HTTP coupling so
  the agent can be tested directly.
- Observability from Project 1 Phase 6 carries through: structured JSON logging,
  OpenTelemetry traces, trace IDs propagated across agent → MCP tool calls.

---

## Phase 0 — Project 2 scaffold

```
You are starting Project 2 of grounded-rag-assistant: a LangGraph + MCP layer
on top of the Project 1 RAG service. This is phase 0 of 4: scaffolding ONLY.

Read docs/PROJECT_2.md (this file's "Constraints" section) before starting.

Constraints recap:
- Same repository, same Python 3.11 venv.
- New packages: app/mcp/ and app/agent/. Existing packages stay untouched
  except for an additive endpoint in Phase 4.
- Reuse — do not copy — Project 1's retriever and answerer functions.
- Feature-branch workflow: branch + PR per phase.

Deliverables:
1. Branch: feat/p2-phase-0-scaffold.
2. Package skeletons:
   - app/mcp/__init__.py
   - app/mcp/server.py (placeholder FastMCP server, no tools yet)
   - app/agent/__init__.py
   - app/agent/graph.py (placeholder LangGraph builder, no nodes yet)
   - app/agent/state.py (initial AgentState TypedDict)
3. Requirements added to pyproject.toml / requirements:
   - mcp (the official Python SDK, with FastMCP)
   - langgraph
   - langchain-mcp-adapters
   - langchain-core
   Pin the major versions; let minor versions float to current.
4. CLI placeholders wired through the existing Makefile:
   - `make mcp-server` — starts the FastMCP server on stdio (no tools yet,
     just so `claude mcp list` shows it connecting).
   - `make agent` — placeholder that prints "agent: not implemented yet"
     and exits 0.
5. New path-scoped rule .claude/rules/agent-mcp.md (see "Rules" appendix at
   the end of this file) — copy it verbatim into the repo.
6. README addendum or a new docs/AGENT.md stub describing the layer.

Acceptance criteria:
- `make lint && make test` green (no new test logic needed; nothing new to
  test yet, but the existing suite must still pass with new deps installed).
- `make mcp-server` starts without error and exits cleanly on Ctrl-C.
- `make agent` prints the expected message and exits 0.
- The path-scoped rule file exists at .claude/rules/agent-mcp.md.

Do not exceed this scope — no tools, no nodes, no orchestration yet.
Open a PR for the branch. Commit: "p2 phase 0: agent and mcp scaffold".
```

---

## Phase 1 — Expose retrieval and generation as MCP tools

```
Phase 1 of 4: wrap Project 1's retrieval and generation functions as MCP tools.
Phase 0 scaffold exists.

Goal: a FastMCP server that exposes the existing pure functions as tools an
external client (a LangGraph agent, Claude Code, Cursor) can call. No agent
logic yet.

Branch: feat/p2-phase-1-mcp-tools.

Requirements:
1. In app/mcp/server.py, build a FastMCP server named "grounded-rag" exposing
   these tools by importing the existing functions — do not reimplement them:

   a. retrieve_chunks(query: str, k: int = 8, mode: str = "hybrid",
                      rerank: bool = false,
                      caller_roles: list[str] = ["public"])
      Wraps app.retrieval.retriever — bm25 / vector / hybrid as the `mode`
      switches. Returns a list of chunks with chunk_id, content, score,
      method tag, and the full metadata.

   b. answer_with_citations(query: str, k: int = 8, rerank: bool = false,
                            caller_roles: list[str] = ["public"])
      Wraps app.generation.answerer — full grounded-answer pipeline.
      Returns the structured object: answer text, claims with cited
      chunk_ids, sources, answered/insufficient boolean.

   c. list_documents(prefix: str | None = None, limit: int = 50)
      A simple catalog tool over the rag_chunks index — returns
      distinct doc_id / title / source_url tuples. Useful for the
      agent's planning step.

2. Tool descriptions are LONG and SPECIFIC. Each must include: what the
   tool does, when to use it, when NOT to use it, inputs, outputs, edge
   cases, and failure behavior. Detailed descriptions are the single
   biggest lever on tool-selection reliability.

3. Errors:
   - Validation errors (bad inputs, unknown mode) → return isError=true
     with errorCategory="validation", isRetryable=false.
   - Transient errors (ES not reachable) → errorCategory="transient",
     isRetryable=true.
   - Business errors (no chunks the caller's roles can see) →
     errorCategory="business", isRetryable=false.
   - Never let an internal stack trace leak into the tool result.

4. Transport: stdio by default (for local dev and Claude Code integration).
   Also support streamable-HTTP via env (MCP_TRANSPORT=http,
   MCP_HTTP_PORT=8765) for the LangGraph client in Phase 2.

5. Observability: every tool call emits an OpenTelemetry span; the trace_id
   propagates into the underlying retriever/answerer calls (they're already
   instrumented from Project 1 Phase 6).

6. Tests:
   - Unit tests calling each tool's underlying handler directly with a
     fake ES and fake provider — assert input validation and the
     structured-error shape.
   - One integration test that launches the server in-process over stdio,
     calls list_documents, and asserts a real response shape.

7. Add an example .mcp.json snippet to docs/AGENT.md showing how Claude Code
   on a developer's machine can connect to this server locally.

Acceptance criteria:
- `make mcp-server` starts the server; `claude mcp list` (or a smoke test
  script) reports three tools connected.
- All three tools callable end-to-end against the local stack.
- Stack traces never appear in tool results.
- Unit + integration tests pass.

Open PR. Commit: "p2 phase 1: expose retrieval and generation as MCP tools".
```

---

## Phase 2 — LangGraph agent over the MCP tools

```
Phase 2 of 4: build the LangGraph agent that orchestrates the MCP tools.

Branch: feat/p2-phase-2-langgraph.

Requirements:
1. In app/agent/state.py, define AgentState (TypedDict) with at minimum:
   - query: str
   - sub_queries: list[str]
   - retrieved: list[dict]   # accumulated chunks across hops
   - draft_answer: dict | None
   - final_answer: dict | None
   - hop: int
   - max_hops: int
   - trace_id: str

2. In app/agent/graph.py, build the LangGraph workflow. Use
   langchain-mcp-adapters to convert this project's MCP tools into
   LangChain BaseTools. Nodes:

   a. plan — given a query, decide whether one retrieval pass is enough
      or whether to decompose into 2–3 sub-queries. Outputs sub_queries.
   b. retrieve — for each sub-query, call the retrieve_chunks MCP tool;
      accumulate results in state.retrieved with deduplication on
      chunk_id.
   c. reflect — given accumulated chunks, decide: "answer now" or
      "need more retrieval" (bounded by max_hops, default 2). If
      "more", produce one targeted follow-up sub-query and route back
      to retrieve.
   d. answer — call the answer_with_citations MCP tool with the
      accumulated context. Returns the structured answer.
   e. END.

3. The reflect node MUST honor the existing insufficient-evidence
   contract. If accumulated chunks don't support the question and
   max_hops is exhausted, route to a no-answer terminal that returns
   the structured insufficient-evidence response — never a hallucinated
   answer.

4. Use the same LLM provider abstraction the answerer uses — read
   LLM_PROVIDER and produce a LangChain chat model from it. Reuse the
   Gemini→Ollama fallback that exists in the project.

5. Checkpointing: use LangGraph's MemorySaver for now. Threads keyed by
   trace_id. (Persistent checkpointing comes in Phase 3.)

6. CLI: `make agent` becomes a real entry point —
   `python -m app.agent.run "your question"` — that streams node-level
   events to stdout for debugging.

7. Tests:
   - Pure unit tests on plan / reflect with mocked LLM and fake tool
     results. Cover the "single hop is enough" and "needs follow-up"
     paths, plus the "exhausted, insufficient evidence" path.
   - One integration test that runs the full graph against the local
     stack and asserts a valid grounded-answer object.

Acceptance criteria:
- `make agent "<question>"` returns a valid grounded answer with
  citations that map to real retrieved chunks.
- An adversarial off-corpus question triggers the insufficient-evidence
  path, not a hallucination.
- Unit tests cover plan / reflect routing logic.
- LLM provider fallback works end-to-end through the agent.

Open PR. Commit: "p2 phase 2: langgraph agent over mcp tools".
```

---

## Phase 3 — Persistent checkpointing, conversation memory, and observability

```
Phase 3 of 4: make the agent stateful across turns and observable.

Branch: feat/p2-phase-3-state-and-observability.

Requirements:
1. Replace MemorySaver with a persistent checkpointer backed by Postgres.
   Use LangGraph's Postgres checkpoint integration. Add a migration for
   the checkpoint tables alongside the existing query_log / feedback
   migrations.

2. Conversation memory: a `thread_id` becomes a first-class concept.
   The agent loads prior turns from the checkpointer; sub-queries and
   follow-up retrievals can refer to "the document you mentioned earlier"
   by including the previous turn's retrieved chunk_ids in context.

3. Per-turn logging:
   - Extend query_log (or add agent_turn_log) to record:
     thread_id, hops_used, tools_called (list), final_answered_flag,
     latency_ms, total_tokens, estimated_cost.
   - The /metrics endpoint exposes aggregate agent stats too.

4. Observability:
   - Every node in the graph emits an OTel span as a child of the
     incoming trace.
   - Span attributes include node name, hop number, tool calls made,
     and token counts.
   - The Jaeger profile from Project 1 Phase 6 visualizes the full
     agent trace.

5. Eval harness extension:
   - Add an agent_eval target: runs the existing gold set through the
     agent (not just /ask) and reports the same metrics — citation
     precision, insufficient-evidence accuracy, latency p50/p95 —
     plus agent-specific ones: average hops, % of queries that
     re-planned, % that hit max_hops without answering.
   - Add a separate regression threshold for agent citation precision;
     do not weaken the existing /ask threshold.

6. Tests:
   - Checkpoint round-trip: a multi-turn conversation, recreated agent,
     state restored from checkpointer.
   - Off-corpus follow-up: a relevant first turn, then a follow-up the
     corpus can't answer; the agent must take the insufficient-evidence
     path for the follow-up without poisoning future state.

Acceptance criteria:
- A multi-turn conversation persists across agent restarts.
- `make agent_eval` produces an agent metrics report alongside the
  existing `make eval` report.
- Traces in Jaeger show the full agent → tool → ES path.
- All thresholds still pass.

Open PR. Commit: "p2 phase 3: persistent checkpointing and agent observability".
```

---

## Phase 4 — HTTP endpoint, CI, demo, docs

```
Phase 4 of 4: expose the agent over HTTP, wire it into CI, finalize docs.
This is the "make it production-grade and shippable" phase.

Branch: feat/p2-phase-4-http-ci-docs.

Requirements:
1. New endpoint in app/api/: POST /agent_ask
   - Body: {query, thread_id?, k?, rerank?, caller_roles?}
   - Streams node-level events as Server-Sent Events
     (Content-Type: text/event-stream) with the final answer event
     terminating the stream. A non-streaming JSON response is the
     default; streaming is opt-in via Accept: text/event-stream.
   - This is the ONLY place app/agent/ gets touched by FastAPI;
     the agent module itself stays HTTP-free (importable for tests
     and for the CLI). The api endpoint adapts the agent the same
     way Project 1's /ask adapts the answerer.

2. CI:
   - GitHub Actions workflow gains a new job `agent_eval` that runs
     after the existing eval job. Uses the fake provider so it does
     not depend on a live LLM.
   - Upload the agent eval report as a separate artifact.
   - The new vm.max_map_count hardening from Project 1 still applies.

3. docs/AGENT.md becomes the canonical agent reference:
   - Architecture diagram (graph nodes + MCP tools + ES).
   - Tool catalog with descriptions.
   - Configuration env vars.
   - How to connect a local Claude Code / Cursor instance to the
     project's MCP server (.mcp.json snippet, transport options).
   - The insufficient-evidence contract, restated.

4. README updates:
   - Architecture section gains the agent layer.
   - Quickstart shows both `make demo` (Project 1) and a new agent demo
     (Project 2) — at least one multi-hop question that triggers
     reflect → re-retrieve → answer.
   - "Not implemented yet" updated.

5. Make target `agent_demo`: a short scripted multi-turn conversation
   demonstrating tool use, follow-up reasoning, and the
   insufficient-evidence path.

Acceptance criteria:
- POST /agent_ask returns valid grounded answers; SSE streaming works.
- CI passes: lint, unit tests, retrieval eval, agent eval — all green.
- `make agent_demo` produces a readable, end-to-end transcript.
- docs/AGENT.md is complete; README quickstart works on a clean clone.

Open PR. Commit: "p2 phase 4: agent http endpoint, ci, docs, demo".
```

---

## After Phase 4

- Update the project's public README screenshot/diagram to show the agent layer.
- Run the `humanize-prose` pass on docs/AGENT.md and the updated README.
- The single repo now demonstrates: production-style RAG + agentic orchestration
  + MCP integration + LangGraph + observability. That's the portfolio story.

## Rules appendix — copy this to `.claude/rules/agent-mcp.md`

```markdown
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
```
