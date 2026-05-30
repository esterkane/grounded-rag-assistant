"""Pure retrieval metric functions.

Each function takes a ranked list of binary relevance labels (``relevances[i]``
is 1 if the item at rank ``i`` is relevant, else 0) and returns a float. They
have no dependency on Elasticsearch and are unit-tested with fixed inputs.
"""

from math import log2


def precision_at_k(relevances: list[int], k: int) -> float:
    """Fraction of the top-k retrieved items that are relevant."""
    if k <= 0:
        return 0.0
    return sum(relevances[:k]) / k


def recall_at_k(relevances: list[int], num_relevant: int, k: int) -> float:
    """Fraction of all relevant items that appear in the top-k."""
    if num_relevant <= 0:
        return 0.0
    return min(sum(relevances[:k]), num_relevant) / num_relevant


def reciprocal_rank(relevances: list[int]) -> float:
    """1 / rank of the first relevant item (0 if none are relevant)."""
    for rank, rel in enumerate(relevances, start=1):
        if rel:
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevances: list[int], k: int) -> float:
    return sum(rel / log2(rank + 2) for rank, rel in enumerate(relevances[:k]))


def ndcg_at_k(relevances: list[int], num_relevant: int, k: int) -> float:
    """Normalized DCG@k with binary gains."""
    dcg = dcg_at_k(relevances, k)
    ideal = [1] * min(num_relevant, k)
    idcg = dcg_at_k(ideal, k)
    return dcg / idcg if idcg > 0 else 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (e.g. pct=95 for p95). Returns 0.0 if empty."""
    if not values:
        return 0.0
    ordered = sorted(values)
    import math

    rank = max(1, min(len(ordered), math.ceil(pct / 100 * len(ordered))))
    return ordered[rank - 1]
