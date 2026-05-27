"""Embeddings via local sentence-transformers (default ``BAAI/bge-small-en-v1.5``).

No external API — the model runs locally and is downloaded on first use. Vectors
are L2-normalized so Elasticsearch cosine similarity behaves like a dot product.
"""

from __future__ import annotations

from app.config import settings

_DEFAULT_BATCH_SIZE = 32


class Embedder:
    """Lazy wrapper around a SentenceTransformer model."""

    def __init__(self, model_name: str | None = None, batch_size: int = _DEFAULT_BATCH_SIZE):
        self.model_name = model_name or settings.embedding_model
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def dim(self) -> int:
        # Newer sentence-transformers renamed this method; support both.
        get_dim = getattr(self.model, "get_embedding_dimension", None) or (
            self.model.get_sentence_embedding_dimension
        )
        return int(get_dim())

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, batched and L2-normalized."""
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()
