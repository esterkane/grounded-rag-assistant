"""Grounded answer generation.

Importable, **no FastAPI coupling** (a later phase exposes this as an MCP tool).

Two entry points:

- :func:`generate_grounded_answer` — the pure core. Given a query, the retrieved
  chunks, and an :class:`LLMProvider`, it builds a grounded prompt, parses the
  model output defensively (retrying once), validates every citation against the
  chunks actually placed in context, and returns a :class:`GroundedAnswer`.
- :func:`answer_question` — orchestrator. Runs Phase-2 hybrid retrieval (with
  optional reranking) and then calls :func:`generate_grounded_answer`.

The model is instructed to answer **only** from context and to set
``answered=false`` when the evidence is insufficient. Grounding is enforced in
code: an answer with no valid citation is downgraded to the insufficient path so
a hallucination can never slip through as a grounded answer.
"""

import json
import logging

from pydantic import BaseModel, Field, ValidationError

from app.generation.models import Claim, GroundedAnswer, Source
from app.generation.providers.base import LLMProvider, Message
from app.retrieval.models import RetrievedChunk
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.retriever import DEFAULT_K, hybrid_search

logger = logging.getLogger(__name__)

INSUFFICIENT_MESSAGE = (
    "I don't have enough grounded evidence in the retrieved documentation to "
    "answer this question."
)

SYSTEM_PROMPT = """You are a grounded question-answering assistant for technical \
documentation. Answer ONLY using the numbered context passages provided below. \
Each passage is labeled with its chunk_id and source_url.

Rules:
- Use only information present in the context passages. Do NOT use prior knowledge.
- Attach a citation to every claim using the exact chunk_id(s) of the passage(s) \
that support it.
- If the context does not contain enough information to answer the question, you \
MUST set "answered" to false and briefly explain that the evidence is \
insufficient. Never guess or fabricate.

Respond with a SINGLE JSON object and nothing else, in exactly this shape:
{"answered": <true|false>, "answer": "<string>", "claims": [{"text": "<string>", \
"citations": ["<chunk_id>", ...]}]}"""


class _RawClaim(BaseModel):
    text: str = ""
    citations: list[str] = Field(default_factory=list)


class _RawAnswer(BaseModel):
    answered: bool
    answer: str = ""
    claims: list[_RawClaim] = Field(default_factory=list)


def build_context_block(chunks: list[RetrievedChunk]) -> str:
    """Render numbered context passages labeled with chunk_id and source_url."""
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        header = f"[{i}] (chunk_id={chunk.chunk_id} source_url={chunk.source_url})"
        blocks.append(f"{header}\n{chunk.content}")
    return "\n\n".join(blocks)


def build_messages(query: str, chunks: list[RetrievedChunk]) -> list[Message]:
    user = (
        f"Question: {query}\n\n"
        f"Context passages:\n{build_context_block(chunks)}\n\n"
        "Return only the JSON object."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _parse_raw_answer(text: str) -> _RawAnswer | None:
    """Parse the model's text into a :class:`_RawAnswer`, defensively."""
    candidate = text.strip()
    if candidate.startswith("```"):
        # Strip a ```json ... ``` fence if present.
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:]
        candidate = candidate.strip()

    data = None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                data = None

    if data is None:
        return None
    try:
        return _RawAnswer.model_validate(data)
    except ValidationError:
        return None


def _insufficient(
    query: str,
    answer: str = INSUFFICIENT_MESSAGE,
    *,
    dropped: list[str] | None = None,
) -> GroundedAnswer:
    return GroundedAnswer(
        query=query,
        answered=False,
        insufficient=True,
        answer=answer,
        claims=[],
        sources=[],
        dropped_citations=dropped or [],
    )


def _build_answer(
    query: str, raw: _RawAnswer, chunks: list[RetrievedChunk]
) -> GroundedAnswer:
    """Validate citations against context and assemble the GroundedAnswer."""
    by_id = {chunk.chunk_id: chunk for chunk in chunks}

    claims: list[Claim] = []
    dropped: list[str] = []
    cited_ids: list[str] = []
    for raw_claim in raw.claims:
        valid = [cid for cid in raw_claim.citations if cid in by_id]
        dropped.extend(cid for cid in raw_claim.citations if cid not in by_id)
        for cid in valid:
            if cid not in cited_ids:
                cited_ids.append(cid)
        claims.append(Claim(text=raw_claim.text, citations=valid))

    # Enforce grounding: a "yes" answer with zero valid citations cannot be
    # trusted, so fall back to the insufficient-evidence path.
    if not raw.answered or not cited_ids:
        answer_text = raw.answer if not raw.answered and raw.answer else INSUFFICIENT_MESSAGE
        return _insufficient(query, answer_text, dropped=dropped)

    sources = [
        Source(
            chunk_id=by_id[cid].chunk_id,
            source_url=by_id[cid].source_url,
            title=by_id[cid].title,
        )
        for cid in cited_ids
    ]
    return GroundedAnswer(
        query=query,
        answered=True,
        insufficient=False,
        answer=raw.answer,
        claims=claims,
        sources=sources,
        dropped_citations=dropped,
    )


def generate_grounded_answer(
    query: str,
    chunks: list[RetrievedChunk],
    provider: LLMProvider,
    *,
    max_retries: int = 1,
) -> GroundedAnswer:
    """Generate a grounded, cited answer from ``chunks`` (pure; no retrieval)."""
    if not chunks:
        return _insufficient(query)

    messages = build_messages(query, chunks)
    raw: _RawAnswer | None = None
    for attempt in range(max_retries + 1):
        try:
            text = provider.generate(messages)
        except Exception:
            logger.exception("LLM generation failed on attempt %d", attempt + 1)
            text = ""
        raw = _parse_raw_answer(text)
        if raw is not None:
            break
        logger.warning("Could not parse model output (attempt %d/%d)", attempt + 1, max_retries + 1)

    if raw is None:
        # Parsing failed after retry: never guess — return insufficient.
        return _insufficient(query)

    return _build_answer(query, raw, chunks)


def answer_question(
    query: str,
    *,
    client: object,
    embedder: object,
    provider: LLMProvider,
    index: str,
    k: int = DEFAULT_K,
    caller_roles: list[str] | None = None,
    rerank: bool = False,
    reranker: CrossEncoderReranker | None = None,
    rank_constant: int = 60,
    rank_window: int = 50,
    rerank_candidate_pool: int = 50,
) -> GroundedAnswer:
    """Run Phase-2 retrieval then generate a grounded answer."""
    pool = max(k, rerank_candidate_pool) if rerank else k
    chunks = hybrid_search(
        client,
        embedder,
        query,
        pool,
        index=index,
        caller_roles=caller_roles,
        rank_constant=rank_constant,
        rank_window=rank_window,
    )
    if rerank and reranker is not None:
        chunks = reranker.rerank(query, chunks, top_k=k)
    else:
        chunks = chunks[:k]

    return generate_grounded_answer(query, chunks, provider)
