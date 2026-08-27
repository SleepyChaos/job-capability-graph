from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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
    # LLM 网关（OpenAI 兼容）：无 Key 时全部调用降级为规则输出（需确认清单 Q1）
    llm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("APP_LLM_API_KEY", "OPENAI_API_KEY"),
    )
    llm_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        validation_alias=AliasChoices("APP_LLM_BASE_URL", "OPENAI_BASE_URL"),
    )
    llm_model: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("APP_LLM_MODEL", "LLM_MODEL"),
    )
    llm_timeout_seconds: int = 30
    # 认证（D5）：生产部署必须改为随机密钥
    auth_secret: str = ""
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[3])


@lru_cache
def get_settings() -> Settings:
    return Settings()
