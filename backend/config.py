"""All runtime configuration, read from environment variables (or .env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: str = "dev"
    HINDSIGHT_BASE_URL: str = ""
    HINDSIGHT_API_KEY: str | None = None
    GROQ_API_KEY: str = ""
    AGENT_MODEL: str = "openai/gpt-oss-120b"
    AGENT_FALLBACK_MODEL: str = "qwen/qwen3-32b"
    SLACK_BOT_TOKEN: str = ""
    SLACK_APP_TOKEN: str = ""
    SLACK_REVIEW_CHANNEL: str = "#cloudsense-review"
    DATABASE_URL: str = "sqlite:///cloudsense.db"
    CLOUDSENSE_PRINCIPAL_ARN: str = ""
    DEMO_LOOKBACK_HOURS: int | None = None
    DRY_RUN: bool = True


settings = Settings()
