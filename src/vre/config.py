"""Configuration, read once from the environment.

Values come from real environment variables first, then from a local `.env`
file. Anything required but missing raises immediately at import time, which is
far easier to debug than a `None` surfacing three calls later.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # tolerate unrelated variables in .env
    )

    # Field names map to env vars case-insensitively:
    # `database_url` is populated from DATABASE_URL.
    database_url: str


settings = Settings()  # type: ignore[call-arg]
