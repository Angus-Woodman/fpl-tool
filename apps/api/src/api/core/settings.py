from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_log_level: str = Field(default="INFO", alias="API_LOG_LEVEL")
    database_url: str = Field(
        default="postgresql+psycopg://fpl:fpl@localhost:5432/fpl",
        alias="DATABASE_URL",
    )
    fpl_api_base_url: str = Field(
        default="https://fantasy.premierleague.com/api",
        alias="FPL_API_BASE_URL",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
