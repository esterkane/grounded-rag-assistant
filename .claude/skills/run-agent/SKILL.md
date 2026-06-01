---
name: run-agent
description: >-
  Run the grounded-rag-assistant LangGraph agent against a query and surface the
  node-by-node execution — which sub-queries were planned, which MCP tools were
  called, what each retrieval hop returned, whether the reflect node decided to
  re-retrieve, and the final grounded answer. Use whenever the user wants to
  exercise the agent layer (Project 2), demo multi-hop reasoning, or compare
  agent answers to the plain /ask answers from Project 1.
argument-hint: "[query to ask the agent, optionally with thread_id]"
context: fork
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash(make agent *)
  - Bash(make agent_demo *)
  - Bash(python -m app.agent* *)
  - Bash(curl -s localhost:* *)
---

Run the agent and report the trace. Query: $ARGUMENTS

## Steps

1. Confirm the stack is up (ES + Postgres healthy) and the MCP server is
   reachable. If the agent CLI hangs on tool calls, the MCP server is the
   first place to check.
2. Confirm an LLM provider is configured. For demos, `LLM_PROVIDER=ollama`
   is the most reliable (no rate limits). For free-tier Gemini, expect
   per-call delays from rate limits across multi-hop runs — the Gemini→Ollama
   fallback rescues individual calls but a multi-hop batch can still struggle.
3. Run the agent via `make agent "<query>"` (or `python -m app.agent.run` with
   options for thread_id). Capture the node-level event stream — do not
   discard intermediate output.
4. Read the events.

## What to report

Present the run as a trace, not a raw dump:

- **Plan node** — did it issue one sub-query or decompose? Which sub-queries.
- **Retrieve hops** — for each hop: which sub-query, how many chunks, which
  retrieval mode (bm25 / vector / hybrid / +rerank), the top result's
  chunk_id and source_url.
- **Reflect node** — did it route to answer or re-retrieve? If re-retrieve,
  what follow-up sub-query and why. Whether max_hops was approached.
- **Answer node** — the structured answer object: claims, citations,
  `answered` vs `insufficient` flag.
- **Citations sanity check** — every cited chunk_id must appear in the
  accumulated retrieved set. Flag any that do not (that is a Project 1
  citation-validator regression and worth a `/rag-debug` follow-up).
- **Provider used** — which LLM, whether the fallback tripped.
- **Latency** — total wall time, plus the slowest single node if obvious.

End with a one-paragraph judgment: was the multi-hop behavior justified
by the question, or did the agent over-plan? Did insufficient-evidence
fire correctly, or did the agent hallucinate? Anything worth a follow-up
in `/debug-agent`.
