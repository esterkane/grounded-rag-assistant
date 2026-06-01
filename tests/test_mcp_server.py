"""Integration tests for the MCP server.

Requires Elasticsearch (real Phase-2 retrieval). The stdio test launches the
FastMCP server as a subprocess and drives it with the MCP client, asserting the
three tools are connected and that `list_documents` responds with a real shape.
The answer tests call the handler directly against the live index with a
deterministic fake provider, covering the grounded and insufficient-evidence
paths without a live LLM.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from app.generation.providers.base import LLMProvider
from app.ingestion.index import count_chunks, ensure_index
from app.ingestion.run import ingest_path
from app.mcp.resources import get_embedder, get_es_client
from app.mcp.tools import answer_with_citations_impl


class FirstChunkCitingProvider(LLMProvider):
    """Cites the first chunk_id found in the prompt — simulating a grounded model."""

    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        user = next(m["content"] for m in messages if m["role"] == "user")
        match = re.search(r"chunk_id=(\S+)", user)
        chunk_id = match.group(1) if match else "none"
        return json.dumps(
            {
                "answered": True,
                "answer": "Grounded answer from context.",
                "claims": [{"text": "A grounded claim.", "citations": [chunk_id]}],
            }
        )


class InsufficientProvider(LLMProvider):
    def generate(self, messages, *, temperature=0.0, json_output=True, **opts) -> str:
        return json.dumps({"answered": False, "answer": "Not enough evidence.", "claims": []})


@pytest.fixture(scope="module")
def populated_index() -> None:
    settings = get_settings()
    es = get_es_client()
    ensure_index(es, settings.elasticsearch_index, get_embedder().dimensions)
    if count_chunks(es, settings.elasticsearch_index) == 0:
        ingest_path(Path("data/sample_corpus"))
        es.indices.refresh(index=settings.elasticsearch_index)


def test_server_lists_three_tools_and_serves_list_documents(populated_index: None) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp.server"],
            env={**os.environ},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {"retrieve_chunks", "answer_with_citations", "list_documents"}

                result = await session.call_tool("list_documents", {"limit": 5})
                assert result.isError is False
                data = json.loads(result.content[0].text)
                assert isinstance(data["documents"], list)
                assert data["count"] == len(data["documents"])

    asyncio.run(run())


def test_answer_with_citations_grounded(populated_index: None) -> None:
    settings = get_settings()
    result = answer_with_citations_impl(
        "How does vector search work?",
        k=4,
        client=get_es_client(),
        embedder=get_embedder(),
        provider=FirstChunkCitingProvider(),
        index=settings.elasticsearch_index,
    )
    assert result.get("isError", False) is False
    assert result["answered"] is True
    cited = {cid for claim in result["claims"] for cid in claim["citations"]}
    assert cited
    source_ids = {s["chunk_id"] for s in result["sources"]}
    assert cited <= source_ids


def test_answer_with_citations_offcorpus_is_insufficient(populated_index: None) -> None:
    settings = get_settings()
    result = answer_with_citations_impl(
        "What is the best recipe for lasagna?",
        k=4,
        client=get_es_client(),
        embedder=get_embedder(),
        provider=InsufficientProvider(),
        index=settings.elasticsearch_index,
    )
    assert result.get("isError", False) is False
    assert result["answered"] is False
    assert result["insufficient"] is True
    assert result["claims"] == []
