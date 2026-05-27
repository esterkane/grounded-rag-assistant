"""Application configuration, loaded from environment / .env via pydantic-settings.

This is the single source of truth for runtime configuration. Every other module
should import ``settings`` from here rather than reading ``os.environ`` directly.
Field names map to upper-case environment variables (e.g. ``es_url`` -> ``ES_URL``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Defaults are chosen so the app runs against the local Docker Compose stack
    with no .env edits. Secrets (e.g. GEMINI_API_KEY) default to empty and must be
    provided via the environment or .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General ---------------------------------------------------------------
    app_env: str = Field(default="local", description="Deployment environment name.")
    log_level: str = Field(default="INFO", description="Python log level.")

    # --- Elasticsearch ---------------------------------------------------------
    # Defaults to the host-mapped port; inside Compose the api service overrides
    # this to http://elasticsearch:9200.
    es_url: str = Field(default="http://localhost:9200")
    es_index: str = Field(default="rag_chunks", description="Index holding chunk docs.")

    # --- PostgreSQL ------------------------------------------------------------
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_user: str = Field(default="grag")
    postgres_password: str = Field(default="grag")
    postgres_db: str = Field(default="grag")

    # --- Embeddings (Phase 1) --------------------------------------------------
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5")

    # --- LLM generation (Phase 3) ----------------------------------------------
    # Provider-abstracted: "gemini" (free tier) or "ollama" (local). Default gemini.
    llm_provider: str = Field(default="gemini")
    gemini_api_key: str = Field(default="", description="Google AI Studio key.")
    gemini_model: str = Field(default="gemini-2.0-flash")
    ollama_host: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="llama3.1")

    # --- Retrieval (Phase 2) ---------------------------------------------------
    rerank_enabled: bool = Field(default=False)

    @property
    def postgres_dsn(self) -> str:
        """libpq connection string for psycopg."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


# Module-level convenience instance.
settings = get_settings()
