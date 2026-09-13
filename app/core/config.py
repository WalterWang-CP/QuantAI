from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    app_name: str = "QuantAI Data Engine"

    database_url: str

    alpha_vantage_api_key: str | None = None

    retrieval_max_attempts: int = 3

    retrieval_retry_base_seconds: int = 60

    retrieval_default_batch_limit: int = 5

    retrieval_stale_running_minutes: int = 10

    alpha_vantage_batch_daily_budget: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()