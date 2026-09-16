"""Configuration supplied by the runtime environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    token_lifetime_minutes: int
    requests_per_minute: int


def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set")
    return Settings(
        database_url=database_url,
        cors_origins=tuple(
            item.strip()
            for item in os.environ.get("CORS_ORIGINS", "").split(",")
            if item.strip()
        ),
        token_lifetime_minutes=int(os.environ.get("TOKEN_LIFETIME_MINUTES", "60")),
        requests_per_minute=int(os.environ.get("REQUESTS_PER_MINUTE", "60")),
    )
