from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "grounded-rag-assistant"
    app_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"
    # Structured logging: "json" (one JSON object per line, with trace ids) or
    # "text" (plain human-readable lines).
    log_format: str = "json"

    # Observability (Phase 6)
    otel_service_name: str = "grounded-rag-assistant"
    otel_traces_enabled: bool = True
    # Empty -> spans go to the console exporter. Set to an OTLP/HTTP endpoint
    # (e.g. http://jaeger:4318) to export there instead.
    otel_exporter_otlp_endpoint: str = ""

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "rag_chunks"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "grounded_rag"
    postgres_user: str = "grounded_rag"
    postgres_password: str = Field(default="grounded_rag", repr=False)

    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Retrieval / reranking
    retrieval_k: int = 10
    rrf_rank_constant: int = 60
    rrf_rank_window: int = 50
    rerank_enabled: bool = False
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_candidate_pool: int = 50

    # Evaluation harness
    eval_k: int = 10
    eval_gold_path: str = "data/gold/queries.jsonl"
    eval_report_dir: str = "eval_reports"
    # Regression threshold: hybrid MRR must stay at or above this.
    # Calibrated 2026 from baseline 0.448 on the realigned 18-query gold set over
    # the fetched namespaced corpus; ~0.07 headroom (about 2-3 queries of drift).
    # Lower only after investigating a real regression.
    eval_hybrid_mrr_threshold: float = 0.38
    # Cap on how many answerable/non-answerable gold items hit the (slow) LLM
    # during answer-quality eval. 0 disables answer eval entirely.
    eval_answer_sample: int = 6

    llm_provider: str = "gemini"
    # Fallback provider used when the primary's tokens/quota are unavailable
    # (e.g. Gemini free-tier 429). Empty disables fallback. See FallbackProvider.
    llm_fallback: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_api_key: str = Field(default="", repr=False)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
