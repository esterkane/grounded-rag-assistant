"""Evaluation harness.

Runs the gold set through each retrieval mode (bm25, vector, hybrid,
hybrid+rerank) and computes Precision@k, Recall@k, MRR and nDCG@k, plus
retrieval latency. Optionally runs grounded generation over a sample of the gold
set to measure citation precision, insufficient-evidence accuracy, and /ask
latency.

Relevance is judged at the document level: a retrieved chunk is relevant if its
``source_path`` is in the gold item's ``relevant_doc_ids``. The recall
denominator is the number of chunks belonging to the relevant documents.

This module has no FastAPI dependency; it drives the pure retrieval/generation
functions directly.
"""

import logging
import time
from dataclasses import dataclass, field

from elasticsearch import Elasticsearch

from app.config import Settings
from app.eval.gold import GoldQuery
from app.eval.metrics import (
    mean,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.generation.answerer import generate_grounded_answer
from app.generation.providers import build_provider
from app.ingestion.embedder import SentenceTransformersEmbedder
from app.retrieval.models import RetrievedChunk
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.retriever import bm25_search, hybrid_search, vector_search

logger = logging.getLogger(__name__)

RETRIEVAL_MODES = ("bm25", "vector", "hybrid", "hybrid_rerank")


@dataclass
class ModeMetrics:
    mode: str
    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    latency_p50_ms: float
    latency_p95_ms: float
    queries: int


@dataclass
class AnswerMetrics:
    citation_precision: float = 0.0
    answerable_evaluated: int = 0
    insufficient_accuracy: float = 0.0
    nonanswerable_evaluated: int = 0
    ask_latency_p50_ms: float = 0.0
    ask_latency_p95_ms: float = 0.0
    skipped_reason: str | None = None


@dataclass
class EvalReport:
    k: int
    gold_size: int
    answerable: int
    non_answerable: int
    retrieval: dict[str, ModeMetrics] = field(default_factory=dict)
    answers: AnswerMetrics = field(default_factory=AnswerMetrics)
    hybrid_mrr_threshold: float = 0.0
    provider: str = ""


def doc_chunk_counts(client: Elasticsearch, index: str) -> dict[str, int]:
    """Map each document's source_path to its number of indexed chunks."""
    response = client.search(
        index=index,
        size=0,
        aggs={"by_doc": {"terms": {"field": "source_path", "size": 1000}}},
    )
    buckets = response["aggregations"]["by_doc"]["buckets"]
    return {b["key"]: b["doc_count"] for b in buckets}


def retrieve(
    mode: str,
    query: str,
    *,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder,
    reranker: CrossEncoderReranker | None,
    index: str,
    k: int,
    settings: Settings,
) -> list[RetrievedChunk]:
    if mode == "bm25":
        return bm25_search(client, query, k, index=index)
    if mode == "vector":
        return vector_search(client, embedder, query, k, index=index)
    if mode == "hybrid":
        return hybrid_search(
            client, embedder, query, k, index=index,
            rank_constant=settings.rrf_rank_constant, rank_window=settings.rrf_rank_window,
        )
    if mode == "hybrid_rerank":
        if reranker is None:
            reranker = CrossEncoderReranker(settings.rerank_model)
        pool = max(k, settings.rerank_candidate_pool)
        fused = hybrid_search(
            client, embedder, query, pool, index=index,
            rank_constant=settings.rrf_rank_constant, rank_window=settings.rrf_rank_window,
        )
        return reranker.rerank(query, fused, top_k=k)
    raise ValueError(f"Unknown retrieval mode: {mode}")


def _relevances(chunks: list[RetrievedChunk], relevant_docs: set[str]) -> list[int]:
    return [1 if chunk.source_path in relevant_docs else 0 for chunk in chunks]


def evaluate_retrieval(
    gold: list[GoldQuery],
    *,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder,
    reranker: CrossEncoderReranker | None,
    index: str,
    k: int,
    settings: Settings,
    modes: tuple[str, ...] = RETRIEVAL_MODES,
) -> dict[str, ModeMetrics]:
    """Compute retrieval metrics for each mode over the answerable gold items."""
    chunk_counts = doc_chunk_counts(client, index)
    answerable = [g for g in gold if g.expected_answerable and g.relevant_doc_ids]

    results: dict[str, ModeMetrics] = {}
    for mode in modes:
        precisions, recalls, rrs, ndcgs, latencies = [], [], [], [], []
        for item in answerable:
            relevant_docs = set(item.relevant_doc_ids)
            num_relevant = sum(chunk_counts.get(d, 0) for d in relevant_docs)

            start = time.perf_counter()
            chunks = retrieve(
                mode, item.query, client=client, embedder=embedder,
                reranker=reranker, index=index, k=k, settings=settings,
            )
            latencies.append((time.perf_counter() - start) * 1000.0)

            rels = _relevances(chunks, relevant_docs)
            precisions.append(precision_at_k(rels, k))
            recalls.append(recall_at_k(rels, num_relevant, k))
            rrs.append(reciprocal_rank(rels))
            ndcgs.append(ndcg_at_k(rels, num_relevant, k))

        results[mode] = ModeMetrics(
            mode=mode,
            precision_at_k=mean(precisions),
            recall_at_k=mean(recalls),
            mrr=mean(rrs),
            ndcg_at_k=mean(ndcgs),
            latency_p50_ms=percentile(latencies, 50),
            latency_p95_ms=percentile(latencies, 95),
            queries=len(answerable),
        )
    return results


def evaluate_answers(
    gold: list[GoldQuery],
    *,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder,
    index: str,
    k: int,
    settings: Settings,
) -> AnswerMetrics:
    """Citation precision, insufficient-evidence accuracy, and /ask latency.

    Uses the configured LLM provider. If a provider cannot be built or the first
    generation fails (no key, model unreachable), answer eval is skipped so the
    retrieval eval and regression test still run (e.g. in CI without an LLM).
    """
    if settings.eval_answer_sample <= 0:
        return AnswerMetrics(skipped_reason="disabled (eval_answer_sample=0)")

    try:
        provider = build_provider(settings)
    except Exception as exc:
        return AnswerMetrics(skipped_reason=f"provider unavailable: {exc}")

    answerable = [g for g in gold if g.expected_answerable and g.relevant_doc_ids][
        : settings.eval_answer_sample
    ]
    non_answerable = [g for g in gold if not g.expected_answerable][
        : settings.eval_answer_sample
    ]

    total_citations = 0
    relevant_citations = 0
    latencies: list[float] = []
    answerable_done = 0
    for item in answerable:
        relevant_docs = set(item.relevant_doc_ids)
        chunks = retrieve(
            "hybrid", item.query, client=client, embedder=embedder,
            reranker=None, index=index, k=k, settings=settings,
        )
        id_to_source = {c.chunk_id: c.source_path for c in chunks}
        try:
            start = time.perf_counter()
            answer = generate_grounded_answer(item.query, chunks, provider)
            latencies.append((time.perf_counter() - start) * 1000.0)
        except Exception as exc:
            if answerable_done == 0:
                return AnswerMetrics(skipped_reason=f"generation failed: {exc}")
            logger.warning("Generation failed for %r: %s", item.query, exc)
            continue
        answerable_done += 1
        for claim in answer.claims:
            for cid in claim.citations:
                total_citations += 1
                if id_to_source.get(cid) in relevant_docs:
                    relevant_citations += 1

    correct_insufficient = 0
    nonanswerable_done = 0
    for item in non_answerable:
        chunks = retrieve(
            "hybrid", item.query, client=client, embedder=embedder,
            reranker=None, index=index, k=k, settings=settings,
        )
        try:
            start = time.perf_counter()
            answer = generate_grounded_answer(item.query, chunks, provider)
            latencies.append((time.perf_counter() - start) * 1000.0)
        except Exception as exc:
            logger.warning("Generation failed for %r: %s", item.query, exc)
            continue
        nonanswerable_done += 1
        if answer.insufficient:
            correct_insufficient += 1

    return AnswerMetrics(
        citation_precision=(relevant_citations / total_citations) if total_citations else 0.0,
        answerable_evaluated=answerable_done,
        insufficient_accuracy=(correct_insufficient / nonanswerable_done)
        if nonanswerable_done
        else 0.0,
        nonanswerable_evaluated=nonanswerable_done,
        ask_latency_p50_ms=percentile(latencies, 50),
        ask_latency_p95_ms=percentile(latencies, 95),
        skipped_reason=None,
    )


def run_evaluation(
    gold: list[GoldQuery],
    *,
    client: Elasticsearch,
    embedder: SentenceTransformersEmbedder,
    settings: Settings,
    with_answers: bool = True,
    reranker: CrossEncoderReranker | None = None,
) -> EvalReport:
    index = settings.elasticsearch_index
    k = settings.eval_k

    retrieval = evaluate_retrieval(
        gold, client=client, embedder=embedder, reranker=reranker,
        index=index, k=k, settings=settings,
    )
    answers = (
        evaluate_answers(
            gold, client=client, embedder=embedder, index=index, k=k, settings=settings
        )
        if with_answers
        else AnswerMetrics(skipped_reason="answer eval disabled")
    )

    return EvalReport(
        k=k,
        gold_size=len(gold),
        answerable=len([g for g in gold if g.expected_answerable]),
        non_answerable=len([g for g in gold if not g.expected_answerable]),
        retrieval=retrieval,
        answers=answers,
        hybrid_mrr_threshold=settings.eval_hybrid_mrr_threshold,
        provider=settings.llm_provider,
    )
