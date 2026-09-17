"""Review-stack entrypoint: migrate, seed once, and start the API."""

import os
import secrets
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from utility_assets.auth import hash_password
from utility_assets.db import get_engine
from utility_assets.ingestion import OutputPaths, ingest_csv
from utility_assets.models import User


SEED_KEY = "synthetic-survey-v1"
REVIEW_ADMIN_USERNAME = "review-admin"


def initialize_review_database() -> None:
    command.upgrade(Config(str(Path.cwd() / "alembic.ini")), "head")
    source = Path(os.environ.get("SURVEY_CSV", "data/survey_export.csv"))
    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    result = ingest_csv(
        source,
        paths=OutputPaths.in_directory(output_dir),
        seed_key=SEED_KEY,
    )
    if result.skipped:
        print("Review database already seeded; starting API.", flush=True)
    else:
        print(
            f"Review seed: read={result.rows_read} accepted={result.accepted} "
            f"rejected={result.rejected}; rejects={result.paths.rejects}",
            flush=True,
        )


def initialize_review_identity() -> Path:
    """Issue fresh review credentials without putting a secret in source or logs."""

    os.environ.setdefault("SIGNING_SECRET", secrets.token_urlsafe(48))
    if len(os.environ["SIGNING_SECRET"]) < 32:
        raise RuntimeError("SIGNING_SECRET must be at least 32 characters")
    password = secrets.token_urlsafe(24)
    with Session(get_engine()) as session, session.begin():
        user = session.scalar(select(User).where(User.username == REVIEW_ADMIN_USERNAME))
        if user is None:
            session.add(
                User(
                    username=REVIEW_ADMIN_USERNAME,
                    password_hash=hash_password(password),
                    role="administrator",
                )
            )
        else:
            user.password_hash = hash_password(password)
            user.role = "administrator"

    path = Path(os.environ.get("REVIEW_CREDENTIALS_FILE", "/run/utility-assets/review-admin.txt"))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        file.write(f"username={REVIEW_ADMIN_USERNAME}\npassword={password}\n")
    os.chmod(path, 0o600)
    print(f"Review administrator ready; credentials are in {path}", flush=True)
    return path


def main() -> None:
    if os.environ.get("REVIEW_MODE", "false").casefold() == "true":
        initialize_review_database()
        initialize_review_identity()
    else:
        if len(os.environ.get("SIGNING_SECRET", "")) < 32:
            raise RuntimeError("SIGNING_SECRET must be supplied outside review mode")
        command.upgrade(Config(str(Path.cwd() / "alembic.ini")), "head")
    uvicorn.run("utility_assets.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
