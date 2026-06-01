"""LangGraph agent layer for grounded-rag-assistant (Project 2).

Orchestrates the MCP tools (which wrap Project 1's retriever and answerer) into
a plan → retrieve → reflect → answer workflow. Phase 0: scaffold only — the
graph has no nodes yet.

This package is importable without any HTTP coupling: the graph and its state
can be exercised directly from tests and the CLI. The only place FastAPI touches
the agent is the `/agent_ask` endpoint added in Phase 4.
"""
