"""Pure unit tests for retrieval metrics and gold loading (no Elasticsearch)."""

from app.eval.metrics import (
    mean,
    ndcg_at_k,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_precision_at_k() -> None:
    assert precision_at_k([1, 0, 1, 0], 4) == 0.5
    assert precision_at_k([1, 1, 0], 2) == 1.0
    assert precision_at_k([0, 0], 0) == 0.0


def test_recall_at_k() -> None:
    # 2 relevant retrieved in top-4 out of 3 total relevant.
    assert recall_at_k([1, 0, 1, 0], num_relevant=3, k=4) == 2 / 3
    # Capped at 1.0 even if more relevant hits than the known total.
    assert recall_at_k([1, 1, 1], num_relevant=2, k=3) == 1.0
    assert recall_at_k([1, 1], num_relevant=0, k=2) == 0.0


def test_reciprocal_rank() -> None:
    assert reciprocal_rank([0, 0, 1]) == 1 / 3
    assert reciprocal_rank([1, 0, 0]) == 1.0
    assert reciprocal_rank([0, 0, 0]) == 0.0


def test_ndcg_at_k_perfect_vs_worst() -> None:
    # All relevant items first -> nDCG 1.0.
    assert ndcg_at_k([1, 1, 0, 0], num_relevant=2, k=4) == 1.0
    # Relevant items last rank lower than ideal.
    worse = ndcg_at_k([0, 0, 1, 1], num_relevant=2, k=4)
    assert 0.0 < worse < 1.0
    assert ndcg_at_k([0, 0], num_relevant=0, k=2) == 0.0


def test_mean_and_percentile() -> None:
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert mean([]) == 0.0
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([], 95) == 0.0
