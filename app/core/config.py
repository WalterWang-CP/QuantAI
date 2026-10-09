from pydantic import Field, field_validator

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "QuantAI Data Engine"

    database_url: str

    alpha_vantage_api_key: str | None = None

    sec_user_agent: str | None = None
    sec_request_interval_seconds: float = Field(default=0.5, ge=0.2, le=10)
    sec_timeout_seconds: float = Field(default=30, gt=0, le=120)
    sec_max_attempts: int = Field(default=3, ge=1, le=5)
    sec_cache_ttl_seconds: int = Field(default=300, ge=0)
    sec_max_history_files: int = Field(default=20, ge=1, le=100)

    retrieval_max_attempts: int = Field(default=3, gt=0)

    retrieval_retry_base_seconds: int = Field(default=60, gt=0)

    retrieval_default_batch_limit: int = Field(default=5, gt=0)

    retrieval_stale_running_minutes: int = Field(default=10, gt=0)

    alpha_vantage_batch_daily_budget: int = Field(default=20, ge=0)

    alpha_vantage_compact_points: int = Field(default=100, gt=0)

    alpha_vantage_full_history_enabled: bool = False

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL must not be blank")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
