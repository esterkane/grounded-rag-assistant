"""Live end-to-end agent test against the local stack.

Opt-in: requires Elasticsearch with the ingested corpus AND a working LLM
provider (Gemini key or local Ollama), and it spawns the MCP server subprocess.
It is skipped by default to keep `make test` deterministic and free of live-LLM
flakiness; CI exercises the agent with a fake provider in Phase 4. Run with:

    AGENT_LIVE=1 pytest tests/test_agent_live.py -q
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_LIVE") != "1",
    reason="live agent test; set AGENT_LIVE=1 (needs ES + corpus + an LLM provider)",
)


def test_agent_grounded_answer_against_stack():
    from app.agent.runner import run_agent

    final = asyncio.run(
        run_agent(
            "How does hybrid search combine BM25 and vector search with reciprocal rank fusion?",
            k=8,
            max_hops=2,
        )
    )
    answer = final["final_answer"]
    assert answer["answered"] is True
    cited = {c for claim in answer["claims"] for c in claim["citations"]}
    sources = {s["chunk_id"] for s in answer["sources"]}
    assert cited and cited <= sources


def test_agent_offcorpus_is_insufficient_against_stack():
    from app.agent.runner import run_agent

    final = asyncio.run(
        run_agent("What is the best recipe for chocolate lasagna?", k=8, max_hops=2)
    )
    answer = final["final_answer"]
    assert answer["answered"] is False
    assert answer["insufficient"] is True
