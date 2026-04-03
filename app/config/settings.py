from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "genai-recon"
    env: str = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/recon_db"
    vector_dim: int = 1536

    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    llm_api_key: str = "replace_me"
    llm_temperature: float = 0.0
    llm_top_p: float = 0.1
    llm_seed: int = 42
    llm_reconciliation_batch_size: int = 100
    llm_normalization_batch_size: int = 100
    llm_row_enrichment_enabled: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
