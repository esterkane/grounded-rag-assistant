# MCP agent-access tools — `grounded-rag-assistant`

The repository ships a **FastMCP server** (`app/mcp/`) that exposes Project 1's
retrieval and generation core as three read-only MCP tools. Any MCP client — a
LangGraph agent, Claude Code, Cursor — can call them to retrieve evidence and
get grounded, cited answers without going through the HTTP API.

The server reuses the FastAPI-free core directly: the tool logic in
`app/mcp/tools.py` imports `app.retrieval.retriever` and
`app.generation.answerer` and never reimplements them. `app/mcp/server.py`
registers thin FastMCP wrappers that supply cached resource singletons
(Elasticsearch client, embedder, reranker, LLM provider) and open an
OpenTelemetry span around each call.

This document is the client-facing reference. The canonical, long tool
descriptions live in the docstrings in `app/mcp/server.py`; the agent-layer
reference (LangGraph orchestration) is `docs/AGENT.md`.

## Tools

The FastMCP server is named `grounded-rag` and registers three tools.

### `retrieve_chunks`

```
retrieve_chunks(
    query: str,
    k: int = 8,                       # 1..100
    mode: str = "hybrid",             # "bm25" | "vector" | "hybrid"
    rerank: bool = False,
    caller_roles: list[str] | None = None,   # defaults to ["public"]
) -> dict
```

Runs retrieval over the indexed Elasticsearch corpus and returns the top-`k`
chunks. `mode` selects lexical (`bm25`), semantic (`vector`), or RRF-fused
`hybrid` (recommended). `rerank=true` pulls a wider candidate pool, applies the
cross-encoder reranker, then trims to `k`. `caller_roles` enforces
permission-based visibility — chunks whose `permissions` do not intersect the
caller's roles are never returned.

Use it to gather raw evidence before reasoning yourself, or as the retrieval
step of a multi-hop plan. Use `answer_with_citations` instead when you want a
finished answer.

Success output:

```json
{
  "query": "how does vector search work",
  "mode": "hybrid",
  "rerank": false,
  "count": 2,
  "chunks": [
    {
      "chunk_id": "doc-1::0",
      "content": "Vector search uses dense embeddings ...",
      "score": 1.53,
      "methods": ["bm25", "vector"],
      "doc_id": "doc-1",
      "source_url": "https://example/vector",
      "title": "Vector search",
      "heading_path": "...",
      "version": "...",
      "chunk_index": 0,
      "permissions": ["public"]
    }
  ]
}
```

An empty `chunks` list with no error means nothing in the corpus matched.

### `answer_with_citations`

```
answer_with_citations(
    query: str,
    k: int = 8,                       # 1..100
    rerank: bool = False,
    caller_roles: list[str] | None = None,   # defaults to ["public"]
) -> dict
```

Runs the full pipeline — hybrid retrieval (optionally reranked) followed by
grounded generation. Every claim cites the `chunk_id`s that support it; citations
that do not map to a retrieved chunk are dropped. If the evidence does not
support an answer, the tool returns the explicit insufficient-evidence response
instead of guessing.

Success output (a `GroundedAnswer`):

```json
{
  "query": "how does vector search work",
  "answered": true,
  "insufficient": false,
  "answer": "Vector search uses dense embeddings ...",
  "claims": [
    {"text": "A grounded claim.", "citations": ["doc-1::0"]}
  ],
  "sources": [
    {"chunk_id": "doc-1::0", "source_url": "https://example/vector", "title": "Vector search"}
  ],
  "dropped_citations": [],
  "model": "gemini-2.5-flash",
  "usage": {"...": "..."}
}
```

Insufficient evidence is a **normal result**, not an error:
`answered=false`, `insufficient=true`, `claims=[]`, `sources=[]`.

### `list_documents`

```
list_documents(
    prefix: str | None = None,
    limit: int = 50,                  # 1..1000
    caller_roles: list[str] | None = None,   # defaults to ["public"]
) -> dict
```

Returns a catalog of distinct documents — `{doc_id, title, source_url}` —
aggregated from the index, ordered by `doc_id`. Use it during planning to
discover what documentation exists before deciding how to query. A whitespace-only
`prefix` is ignored. Only documents with at least one chunk visible to
`caller_roles` are listed, so the catalog never reveals restricted documents the
caller cannot see.

Success output:

```json
{
  "count": 2,
  "documents": [
    {"doc_id": "doc-1", "title": "Vector search", "source_url": "u1"},
    {"doc_id": "doc-2", "title": "Hybrid search", "source_url": "u2"}
  ]
}
```

## Structured error contract

Tools never raise or leak a stack trace. On failure they return a structured
error payload instead of a result:

```json
{
  "isError": true,
  "errorCategory": "validation",
  "isRetryable": false,
  "message": "<safe, human-readable summary>",
  "details": { }
}
```

`errorCategory` is one of:

| Category | When | `isRetryable` |
| --- | --- | --- |
| `validation` | bad input — unknown `mode`, `k`/`limit` out of range, non-boolean `rerank`, non-string `prefix`, empty `query` | `false` |
| `transient` | search backend momentarily unreachable | `true` |
| `transient` | unexpected internal exception, caught so no trace leaks | `false` |
| `business` | a valid request that cannot be satisfied — e.g. documents match but none are visible to `caller_roles` | `false` |
| `permission` | the caller is not permitted to perform the request | `false` |

`transient` therefore covers two cases with **different** retryability. Clients
should branch on the `isRetryable` flag directly, never infer retryability from
`errorCategory` alone. Stack traces and raw Elasticsearch/Postgres errors are
never returned; unexpected exceptions are logged server-side only.

Note: insufficient evidence from `answer_with_citations` is **not** an error — it
is a normal success result with `answered=false`.

## Running the server

The transport is selected by the `MCP_TRANSPORT` env var: `stdio` (default, for
local dev and Claude Code) or `http` (streamable-HTTP, for the LangGraph client).

```bash
# stdio (default) inside Docker Compose — the standard way to run it:
make mcp-server
#   -> docker compose run --rm --no-deps -i api python -m app.mcp.server

# Or directly, in an environment that already has the dependencies installed:
python -m app.mcp.server

# HTTP (streamable-HTTP) transport:
MCP_TRANSPORT=http python -m app.mcp.server
```

| Env var | Default | Purpose |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` | `stdio` or `http` (streamable-HTTP). |
| `MCP_HTTP_HOST` | `0.0.0.0` | Bind host, used only when `MCP_TRANSPORT=http`. |
| `MCP_HTTP_PORT` | `8765` | Bind port, used only when `MCP_TRANSPORT=http`. |

The stdio transport needs neither Elasticsearch nor Postgres to *start*
(`--no-deps`), but the tools themselves query Elasticsearch when called, so the
local stack (`make up`) plus an ingested corpus (`make ingest`) must be running
for real results.

## Registering with a client

### Claude Code / Cursor (`.mcp.json`, stdio)

Point an MCP client at the server over stdio. For a developer machine running
the project via Docker Compose:

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

In an environment that already has the project dependencies installed, run the
module directly instead:

```json
{
  "mcpServers": {
    "grounded-rag": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "app.mcp.server"]
    }
  }
}
```

### LangGraph (streamable-HTTP)

The LangGraph agent layer (`app/agent/`, see `docs/AGENT.md`) connects via
`langchain-mcp-adapters`. Over stdio it spawns the same `python -m app.mcp.server`
command; over HTTP, start the server with `MCP_TRANSPORT=http` and point the
client at `http://localhost:8765` (the streamable-HTTP endpoint, host/port from
`MCP_HTTP_HOST` / `MCP_HTTP_PORT`).

## Example calls

```text
retrieve_chunks(query="how does hybrid search combine results", k=4, mode="hybrid")
  -> {"query": ..., "mode": "hybrid", "count": 4, "chunks": [ ... ]}

answer_with_citations(query="How does vector search work in Elasticsearch?", k=6)
  -> {"answered": true, "answer": "...", "claims": [ ... ], "sources": [ ... ]}

list_documents(prefix="elasticsearch-labs", limit=10)
  -> {"count": 3, "documents": [ {"doc_id": ..., "title": ..., "source_url": ...} ]}

retrieve_chunks(query="x", mode="fuzzy")
  -> {"isError": true, "errorCategory": "validation", "isRetryable": false,
      "message": "`mode` must be one of ('bm25', 'vector', 'hybrid')."}
```

## Observability

Every tool call opens an OpenTelemetry span (`mcp.<tool>`). Because the Project 1
retriever and answerer are already instrumented, the `trace_id` propagates into
their child spans automatically, giving an end-to-end trace from the MCP call
down to Elasticsearch.

## Tests

- `tests/test_mcp_tools.py` — mock-based unit tests over the tool handlers
  (fake Elasticsearch client and fake LLM provider). They assert input
  validation, the structured-error shape, permission filtering, and that
  insufficient evidence is passed through as a normal result. No live services.
- `tests/test_mcp_server.py` — integration tests that require a live
  Elasticsearch index: they launch the server over stdio, assert the three tools
  connect, and exercise `list_documents` and the grounded / insufficient-evidence
  answer paths against the real index. Run these with the local stack up
  (`make up` + `make ingest`).
