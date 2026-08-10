from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://aegis:aegis@localhost:5432/aegis"
    openai_api_key: str | None = None
    openai_model_name: str = "gpt-4o-mini"
    # auto | crewai | deterministic
    aegis_agent_mode: str = "auto"
    aegis_verbose: bool = True
    max_actions_per_incident: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()