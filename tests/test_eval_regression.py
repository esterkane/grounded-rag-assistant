"""Retrieval regression test.

Fails if hybrid MRR over the gold set drops below the configured threshold.
Requires Elasticsearch with the sample corpus ingested. Also asserts the guard
itself would fire on a deliberately degraded ranking.
"""

from pathlib import Path

import pytest

from app.api.dependencies import get_embedder, get_es_client
from app.config import get_settings
from app.eval.gold import load_gold
from app.eval.harness import evaluate_retrieval
from app.eval.metrics import mean, reciprocal_rank
from app.ingestion.index import count_chunks, ensure_index
from app.ingestion.run import ingest_path


@pytest.fixture(scope="module")
def populated_index() -> None:
    settings = get_settings()
    es = get_es_client()
    ensure_index(es, settings.elasticsearch_index, get_embedder().dimensions)
    if count_chunks(es, settings.elasticsearch_index) == 0:
        ingest_path(Path("data/sample_corpus"))
        es.indices.refresh(index=settings.elasticsearch_index)


def test_hybrid_mrr_meets_threshold(populated_index: None) -> None:
    settings = get_settings()
    gold = load_gold(settings.eval_gold_path)

    metrics = evaluate_retrieval(
        gold,
        client=get_es_client(),
        embedder=get_embedder(),
        reranker=None,
        index=settings.elasticsearch_index,
        k=settings.eval_k,
        settings=settings,
        modes=("hybrid",),
    )

    hybrid_mrr = metrics["hybrid"].mrr
    assert hybrid_mrr >= settings.eval_hybrid_mrr_threshold, (
        f"Hybrid MRR {hybrid_mrr:.3f} fell below threshold "
        f"{settings.eval_hybrid_mrr_threshold:.3f} — investigate the regression."
    )


def test_threshold_guard_fails_on_degraded_ranking() -> None:
    # Simulate a degraded retriever that never ranks the relevant chunk first.
    settings = get_settings()
    degraded_rankings = [[0, 0, 0, 1] for _ in range(10)]  # first relevant at rank 4
    degraded_mrr = mean([reciprocal_rank(r) for r in degraded_rankings])
    assert degraded_mrr < settings.eval_hybrid_mrr_threshold
