from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./talent_library.db"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    es_index_name: str = "candidates"

    # Anthropic Claude API
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""

    # Google Gemini API (用于简历解析，更快)
    gemini_api_key: str = ""

    # Application
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # File Storage
    upload_dir: str = "./uploads"
    max_upload_size: int = 10485760  # 10MB

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
