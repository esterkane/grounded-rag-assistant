"""Plan and reflect reasoning for the agent (Project 2 Phase 2).

These are pure functions over the existing ``LLMProvider`` abstraction — no
LangGraph or MCP coupling — so the routing logic can be unit-tested with a fake
provider and fake chunk lists. They reuse ``build_provider`` (and therefore the
Gemini→Ollama fallback) wherever a provider is constructed by the caller.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.generation.providers import LLMProvider

logger = logging.getLogger(__name__)

MAX_SUBQUERIES = 3
# How many accumulated chunks to summarize for the reflect decision.
REFLECT_CONTEXT_CHUNKS = 8

# Routing actions emitted by reflect().
ANSWER = "answer"
RETRIEVE = "retrieve"
INSUFFICIENT = "insufficient"


@dataclass
class ReflectDecision:
    action: str  # ANSWER | RETRIEVE | INSUFFICIENT
    follow_up: str | None = None
    reason: str = ""


def _extract_json(text: str) -> dict[str, Any] | None:
    """Best-effort parse of a JSON object from a model response."""
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, TypeError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def plan_subqueries(provider: LLMProvider, query: str) -> list[str]:
    """Decide whether one retrieval pass suffices or to decompose the query.

    Returns 1–3 sub-queries. Falls back to ``[query]`` on any LLM/parse failure,
    so planning can never block the pipeline.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You plan retrieval for a documentation Q&A system. Decide whether "
                "the user question needs a single retrieval pass or should be split "
                "into 2-3 focused sub-queries (only split genuinely multi-part "
                "questions). Reply ONLY with JSON: "
                '{"sub_queries": ["...", "..."]}. Use one entry for simple questions.'
            ),
        },
        {"role": "user", "content": query},
    ]
    try:
        raw = provider.generate(messages, json_output=True)
    except Exception:  # noqa: BLE001 - planning must never hard-fail
        logger.exception("plan: LLM call failed; falling back to single query")
        return [query]

    parsed = _extract_json(raw)
    subs = parsed.get("sub_queries") if parsed else None
    if not isinstance(subs, list):
        return [query]
    cleaned = [s.strip() for s in subs if isinstance(s, str) and s.strip()]
    if not cleaned:
        return [query]
    return cleaned[:MAX_SUBQUERIES]


def _summarize_chunks(chunks: list[dict[str, Any]]) -> str:
    lines = []
    for i, c in enumerate(chunks[:REFLECT_CONTEXT_CHUNKS], 1):
        title = c.get("title", "") or "(untitled)"
        snippet = (c.get("content", "") or "").strip().replace("\n", " ")[:200]
        lines.append(f"[{i}] {title}: {snippet}")
    return "\n".join(lines) if lines else "(no chunks retrieved)"


def reflect(
    provider: LLMProvider,
    query: str,
    chunks: list[dict[str, Any]],
    hop: int,
    max_hops: int,
) -> ReflectDecision:
    """Decide whether to answer now, retrieve more, or give up (insufficient).

    The hop bound is enforced here: a "need more" decision at the last allowed
    hop becomes INSUFFICIENT rather than an infinite loop. With no chunks at all
    and no hops left, the decision is INSUFFICIENT. On an LLM/parse failure with
    some chunks present, we default to ANSWER and let the grounded answerer make
    the final (never-hallucinated) call.
    """
    exhausted = hop >= max_hops

    if not chunks:
        if exhausted:
            return ReflectDecision(INSUFFICIENT, reason="no chunks retrieved and hops exhausted")
        return ReflectDecision(RETRIEVE, follow_up=query, reason="no chunks yet; retry retrieval")

    messages = [
        {
            "role": "system",
            "content": (
                "You judge whether the retrieved documentation context is sufficient "
                "to answer the question. Reply ONLY with JSON: "
                '{"sufficient": true|false, "follow_up_query": "<a single focused '
                'query if more retrieval is needed, else empty>"}.'
            ),
        },
        {
            "role": "user",
            "content": f"Question: {query}\n\nContext:\n{_summarize_chunks(chunks)}",
        },
    ]
    try:
        raw = provider.generate(messages, json_output=True)
    except Exception:  # noqa: BLE001
        logger.exception("reflect: LLM call failed; defaulting to answer")
        return ReflectDecision(ANSWER, reason="reflect LLM failed; defer to grounded answerer")

    parsed = _extract_json(raw)
    if not parsed:
        return ReflectDecision(ANSWER, reason="unparseable reflect output; defer to answerer")

    sufficient = bool(parsed.get("sufficient"))
    if sufficient:
        return ReflectDecision(ANSWER, reason="context judged sufficient")

    if exhausted:
        return ReflectDecision(INSUFFICIENT, reason="still insufficient and hops exhausted")

    follow_up = parsed.get("follow_up_query")
    follow_up = follow_up.strip() if isinstance(follow_up, str) and follow_up.strip() else query
    return ReflectDecision(RETRIEVE, follow_up=follow_up, reason="needs more retrieval")
