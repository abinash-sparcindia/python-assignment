"""Configuration supplied by the runtime environment."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    token_lifetime_minutes: int
    requests_per_minute: int
    signing_secret: str | None


def parse_cors_origins(raw: str) -> tuple[str, ...]:
    origins = tuple(item.strip() for item in raw.split(",") if item.strip())
    for origin in origins:
        parts = urlsplit(origin)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.path
            or parts.query
            or parts.fragment
            or parts.username
            or parts.password
            or "*" in origin
        ):
            raise ValueError("CORS_ORIGINS must contain exact http(s) origins without paths or wildcards")
    return origins


def request_limit() -> int:
    try:
        value = int(os.environ.get("REQUESTS_PER_MINUTE", "60"))
    except ValueError as exc:
        raise ValueError("REQUESTS_PER_MINUTE must be a positive integer") from exc
    if value <= 0:
        raise ValueError("REQUESTS_PER_MINUTE must be a positive integer")
    return value


def get_settings() -> Settings:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set")
    return Settings(
        database_url=database_url,
        cors_origins=parse_cors_origins(os.environ.get("CORS_ORIGINS", "")),
        token_lifetime_minutes=int(os.environ.get("TOKEN_LIFETIME_MINUTES", "60")),
        requests_per_minute=request_limit(),
        signing_secret=os.environ.get("SIGNING_SECRET"),
    )
