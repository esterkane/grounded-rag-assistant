from collections.abc import Sequence

from sentence_transformers import SentenceTransformer


class SentenceTransformersEmbedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimensions = int(self.model.get_embedding_dimension())

    def embed(self, texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [embedding.astype(float).tolist() for embedding in embeddings]
