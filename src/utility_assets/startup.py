"""Review-stack entrypoint: migrate, seed once, and start the API."""

import os
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from utility_assets.ingestion import OutputPaths, ingest_csv


SEED_KEY = "synthetic-survey-v1"


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


def main() -> None:
    initialize_review_database()
    uvicorn.run("utility_assets.main:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
