"""Grounded answer generation.

Importable, with **no FastAPI coupling** (a later phase exposes this as an MCP
tool). Retrieves context, builds a prompt with numbered chunks each labeled with
its ``chunk_id`` and ``source_url``, instructs the model to answer ONLY from
context and cite each claim, then parses the response defensively and validates
that every citation references a chunk that was actually in context. When the
context doesn't support an answer, the insufficient-evidence path fires instead
of guessing.

No provider-specific code lives here — it talks to the abstract ``LLMProvider``.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ValidationError

from app.generation.models import Claim, GroundedAnswer, Source
from app.generation.providers.base import LLMProvider
from app.generation.providers.factory import get_provider
from app.retrieval.models import RetrievalResult

INSUFFICIENT_MESSAGE = (
    "The retrieved documentation does not contain enough information to answer "
    "this question."
)

SYSTEM_PROMPT = (
    "You are a precise assistant that answers strictly from the provided context.\n"
    "Rules:\n"
    "- Use ONLY the information in the context. Do not use prior knowledge.\n"
    "- Every factual claim MUST cite the chunk_id(s) it comes from, using the exact\n"
    "  chunk_id values shown in the context labels.\n"
    "- If the context does not contain enough information to answer, do NOT guess:\n"
    '  set "insufficient" to true and leave "claims" empty.\n'
    "Return ONLY a JSON object with this exact shape:\n"
    '{"answer": "<concise answer, or a note that evidence is insufficient>",\n'
    ' "claims": [{"text": "<one factual statement>", "citations": ["<chunk_id>"]}],\n'
    ' "insufficient": <true|false>}'
)

_STRICT_SUFFIX = "Return ONLY valid minified JSON. No markdown, no prose, no code fences."


class _RawClaim(BaseModel):
    text: str = ""
    citations: list[str] = []


class _RawAnswer(BaseModel):
    answer: str = ""
    claims: list[_RawClaim] = []
    insufficient: bool = False


class _ParseError(Exception):
    pass


def build_context(results: list[RetrievalResult]) -> str:
    """Numbered context blocks, each labeled with chunk_id and source_url."""
    return "\n\n".join(
        f"[{i}] chunk_id={r.chunk_id} source_url={r.source_url}\n{r.content}"
        for i, r in enumerate(results, start=1)
    )


def _build_messages(query: str, context: str, strict: bool = False) -> list[dict]:
    system = SYSTEM_PROMPT + (f"\n{_STRICT_SUFFIX}" if strict else "")
    user = f"Context:\n{context}\n\nQuestion: {query}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise _ParseError("no JSON object found")
    return text[start : end + 1]


def _parse(text: str) -> _RawAnswer:
    try:
        data = json.loads(_extract_json(text))
        return _RawAnswer.model_validate(data)
    except (json.JSONDecodeError, ValidationError, _ParseError) as exc:
        raise _ParseError(str(exc)) from exc


def _insufficient(answer: str = INSUFFICIENT_MESSAGE) -> GroundedAnswer:
    return GroundedAnswer(
        answer=answer, claims=[], sources=[], answered=False, insufficient=True
    )


def _assemble(raw: _RawAnswer, results: list[RetrievalResult]) -> GroundedAnswer:
    """Validate citations against retrieved chunks; drop invalid ones.

    If the model declared insufficiency, or no claim retains a valid citation,
    return the insufficient-evidence answer rather than an ungrounded one.
    """
    if raw.insufficient:
        return _insufficient(raw.answer or INSUFFICIENT_MESSAGE)

    valid_ids = {r.chunk_id for r in results}
    claims: list[Claim] = []
    cited: set[str] = set()
    for rc in raw.claims:
        good = [c for c in rc.citations if c in valid_ids]
        if good:
            claims.append(Claim(text=rc.text, citations=good))
            cited.update(good)

    if not claims:
        return _insufficient()

    sources = [
        Source(chunk_id=r.chunk_id, source_url=r.source_url, title=r.title)
        for r in results
        if r.chunk_id in cited
    ]
    return GroundedAnswer(
        answer=raw.answer, claims=claims, sources=sources, answered=True, insufficient=False
    )


def build_grounded_answer(
    query: str, results: list[RetrievalResult], provider: LLMProvider
) -> GroundedAnswer:
    """Generate and validate a grounded answer from already-retrieved results.

    Pure of retrieval/HTTP concerns — takes results and a provider, parses the
    model output defensively, and retries once on a parse failure.
    """
    if not results:
        return _insufficient()

    context = build_context(results)
    try:
        raw = _parse(provider.generate(_build_messages(query, context), json=True))
    except _ParseError:
        try:
            raw = _parse(
                provider.generate(_build_messages(query, context, strict=True), json=True)
            )
        except _ParseError:
            return _insufficient()
    return _assemble(raw, results)


def answer_question(
    query: str,
    k: int = 5,
    rerank: bool | None = None,
    caller_roles: list[str] | None = None,
    provider: LLMProvider | None = None,
    client=None,
    index: str | None = None,
) -> GroundedAnswer:
    """Retrieve context (phase-2 hybrid search) and produce a grounded answer."""
    from app.retrieval.retriever import search

    results = search(
        query, k=k, rerank=rerank, caller_roles=caller_roles, client=client, index=index
    )
    return build_grounded_answer(query, results, provider or get_provider())
