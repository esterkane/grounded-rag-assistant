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

    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "rag_documents"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "grounded_rag"
    postgres_user: str = "grounded_rag"
    postgres_password: str = Field(default="grounded_rag", repr=False)

    embedding_model: str = "BAAI/bge-small-en-v1.5"

    llm_provider: str = "gemini"
    gemini_model: str = "gemini-2.0-flash"
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
