"""Optional local cross-encoder reranker.

Gated by ``RERANK_ENABLED`` (the caller decides whether to invoke it). Reranks a
fused candidate set down to ``top_k`` by scoring (query, passage) pairs with
``cross-encoder/ms-marco-MiniLM-L-6-v2``. Reordering only — the result schema is
unchanged; ``score`` becomes the cross-encoder relevance score.
"""

from __future__ import annotations

from app.retrieval.models import RetrievalResult

DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_model = None


def _get_model(model_name: str = DEFAULT_MODEL):
    global _model
    if _model is None:
        from sentence_transformers import CrossEncoder

        _model = CrossEncoder(model_name)
    return _model


def rerank_results(
    query: str, results: list[RetrievalResult], top_k: int | None = None
) -> list[RetrievalResult]:
    """Return results reordered by cross-encoder relevance, truncated to top_k."""
    if not results:
        return []
    model = _get_model()
    scores = model.predict([(query, r.content) for r in results])
    reranked = [
        r.model_copy(update={"score": float(s)})
        for r, s in sorted(zip(results, scores, strict=True), key=lambda rs: rs[1], reverse=True)
    ]
    return reranked[:top_k] if top_k else reranked
