"""Optional cross-encoder reranking.

Gated by the ``RERANK_ENABLED`` config flag. When enabled, a local
cross-encoder rescores the fused top-N candidates and returns the top-k in the
new order. Reranking only changes ordering and scores — it does not change the
:class:`RetrievedChunk` schema. No FastAPI coupling.
"""

import logging

from app.retrieval.models import RetrievedChunk

logger = logging.getLogger(__name__)

DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Reranks retrieved chunks with a local sentence-transformers CrossEncoder."""

    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL) -> None:
        self.model_name = model_name
        self._model = None  # lazy-loaded on first use

    @property
    def model(self):
        if self._model is None:
            # Imported lazily so importing this module is cheap and dependency-light.
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Rescore ``chunks`` against ``query`` and return the top ``top_k``.

        Each returned chunk's ``score`` is replaced with the cross-encoder score
        and ``"rerank"`` is appended to its ``methods`` tag.
        """
        if not chunks:
            return []

        pairs = [(query, chunk.content) for chunk in chunks]
        scores = self.model.predict(pairs)

        reranked = [
            chunk.model_copy(
                update={
                    "score": float(score),
                    "methods": [*chunk.methods, "rerank"]
                    if "rerank" not in chunk.methods
                    else chunk.methods,
                }
            )
            for chunk, score in zip(chunks, scores, strict=True)
        ]
        reranked.sort(key=lambda chunk: chunk.score, reverse=True)
        return reranked[:top_k] if top_k is not None else reranked
