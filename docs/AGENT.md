# Agent layer — `grounded-rag-assistant` (Project 2)

> **Status: scaffold (Phase 0).** Packages and entry points exist; tools, graph
> nodes, and the HTTP endpoint are not implemented yet. This document fills in
> over Phases 1–4. See `docs/PROJECT_2.md` for the phase definitions.

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

## Commands

| Command | What it does |
| --- | --- |
| `make mcp-server` | Start the FastMCP server on stdio. Phase 0: no tools registered yet. |
| `make agent` | Phase 0 placeholder (`agent: not implemented yet`). Becomes `python -m app.agent.run "<question>"` in Phase 2. |

## Configuration

- `LLM_PROVIDER` — `gemini` (default) or `ollama`, reusing Project 1's provider
  abstraction and the Gemini → Ollama fallback. No paid keys.
- `MCP_TRANSPORT` / `MCP_HTTP_PORT` — stdio by default; streamable-HTTP added in
  Phase 1 for the LangGraph client.

A `.mcp.json` snippet for connecting a local Claude Code / Cursor instance lands
in Phase 1.
