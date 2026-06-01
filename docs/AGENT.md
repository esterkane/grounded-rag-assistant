# Agent layer — `grounded-rag-assistant` (Project 2)

> **Status: Phase 1.** The MCP server now exposes three tools wrapping the
> Project 1 retriever and answerer. The LangGraph graph nodes and the HTTP
> endpoint are still to come (Phases 2–4). See `docs/PROJECT_2.md` for the phase
> definitions.

Project 2 adds an **agentic layer** on top of the Project 1 RAG service. The
Phase 2 retriever and Phase 3 answerer functions are exposed as **MCP tools**,
and a **LangGraph** agent orchestrates them — adding query planning, multi-step
retrieval, and self-reflection on insufficient evidence — while the Project 1
HTTP API stays intact.

## Why a separate layer

Project 1 deliberately kept everything under `app/retrieval/` and
`app/generation/answerer.py` free of FastAPI coupling. Project 2 cashes in that
boundary: the MCP tools and LangGraph nodes **import** those pure functions
rather than reimplementing them.

## Packages

| Package | Role |
| --- | --- |
| `app/mcp/` | FastMCP server (`server.py`) exposing the retriever/answerer as MCP tools. |
| `app/agent/` | LangGraph workflow: `state.py` (`AgentState`) and `graph.py` (the builder). Importable without HTTP. |

The existing `app/api/`, `app/retrieval/`, and `app/generation/` packages stay
untouched, except for the additive `/agent_ask` endpoint added in Phase 4.

## Planned architecture

```
                    ┌──────────────────────────────────────────┐
  query ──▶ plan ──▶│ retrieve ──▶ reflect ──┐                  │
                    │    ▲                    │ answer ──▶ END   │
                    │    └──── (more hops) ◀──┘                  │
                    └──────────────────────────────────────────┘
                          │ (MCP tools, stdio / streamable-HTTP)
                          ▼
                    retrieve_chunks · answer_with_citations · list_documents
                          │
                          ▼
                    Elasticsearch (BM25 + vector + hybrid RRF)
```

- **plan** — decide whether one retrieval pass suffices or to decompose into
  2–3 sub-queries.
- **retrieve** — call `retrieve_chunks` per sub-query; accumulate with
  dedup on `chunk_id`.
- **reflect** — "answer now" vs "need more retrieval", bounded by `max_hops`
  (default 2).
- **answer** — call `answer_with_citations` with the accumulated context.

## The insufficient-evidence contract (unchanged from Project 1)

If accumulated context does not support the question and `max_hops` is
exhausted, the agent returns the structured **insufficient-evidence** response.
It never hallucinates an answer.

## Tool catalog (Phase 1)

The FastMCP server is named `grounded-rag` (`app/mcp/server.py`). It exposes
three tools, each wrapping a Project 1 pure function — see the tool docstrings
in `app/mcp/server.py` for the full, MCP-client-facing descriptions.

| Tool | Wraps | Returns |
| --- | --- | --- |
| `retrieve_chunks(query, k=8, mode="hybrid", rerank=false, caller_roles=["public"])` | `app.retrieval.retriever` (`bm25` / `vector` / `hybrid`) | `{query, mode, rerank, count, chunks[]}` — each chunk has `chunk_id`, `content`, `score`, `methods`, and full metadata. |
| `answer_with_citations(query, k=8, rerank=false, caller_roles=["public"])` | `app.generation.answerer.answer_question` | A `GroundedAnswer`: `{answered, insufficient, answer, claims[], sources[], dropped_citations, model, usage}`. |
| `list_documents(prefix=None, limit=50)` | aggregation over `rag_chunks` | `{count, documents[]}` — distinct `{doc_id, title, source_url}`. |

### Structured errors

Tools never raise or leak a stack trace. On failure they return
`{isError: true, errorCategory, isRetryable, message, details}` where
`errorCategory` is one of `validation` (bad input — not retryable), `transient`,
`business` (e.g. matches exist but none are visible to `caller_roles` — not
retryable), or `permission`.

Note that `transient` covers two cases with **different** retryability: a
backend that is momentarily unreachable (`isRetryable: true`) and an unexpected
internal exception that was caught to avoid leaking a trace (`isRetryable:
false`). Clients should therefore branch on the `isRetryable` flag directly,
never infer retryability from `errorCategory` alone.

Insufficient evidence from `answer_with_citations` is a normal result
(`answered=false`), not an error.

### Observability

Every tool call opens an OpenTelemetry span (`mcp.<tool>`); because the Project 1
retriever and answerer are already instrumented, the trace_id propagates into
their child spans automatically.

## Commands

| Command | What it does |
| --- | --- |
| `make mcp-server` | Start the FastMCP server on stdio with the three tools registered. |
| `make agent` | Phase 0 placeholder (`agent: not implemented yet`). Becomes `python -m app.agent.run "<question>"` in Phase 2. |

## Configuration

- `LLM_PROVIDER` — `gemini` (default) or `ollama`, reusing Project 1's provider
  abstraction and the Gemini → Ollama fallback. No paid keys.
- `MCP_TRANSPORT` — `stdio` (default) or `http` (streamable-HTTP).
- `MCP_HTTP_HOST` / `MCP_HTTP_PORT` — bind address for the HTTP transport
  (default `0.0.0.0:8765`), used by the LangGraph client in Phase 2.

## Connecting a local Claude Code / Cursor instance

Point an MCP client at the server over stdio. Example `.mcp.json` for a
developer machine running the project via Docker Compose:

```json
{
  "mcpServers": {
    "grounded-rag": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "compose", "run", "--rm", "--no-deps", "-i",
        "api", "python", "-m", "app.mcp.server"
      ]
    }
  }
}
```

To run the server directly inside an environment that already has the
dependencies installed, use `command: "python"` with
`args: ["-m", "app.mcp.server"]` instead. For the HTTP transport, set
`MCP_TRANSPORT=http` and connect to `http://localhost:8765`.
