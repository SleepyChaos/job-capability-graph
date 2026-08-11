from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    app_name: str = "具身智能岗位与能力图谱系统"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+pysqlite:///./.local/dev.db"
    log_level: str = "INFO"
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[3])


@lru_cache
def get_settings() -> Settings:
    return Settings()
