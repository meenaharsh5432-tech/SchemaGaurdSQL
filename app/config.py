from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr

PROJECT_ROOT=Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    database_url: SecretStr
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-coder:3b"
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6380/0")
    result_cache_ttl_seconds: int = Field(default=60, ge=1, le=300)
    audit_database_url: SecretStr
    model_config=SettingsConfigDict(
        env_file=PROJECT_ROOT/".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    schema_retrieval_enabled: bool = False


settings=Settings()
