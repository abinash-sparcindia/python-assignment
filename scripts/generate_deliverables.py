"""Regenerate the checked-in ingestion outputs with the operator CLI.

The assignment's file-load deliverable is one run of ``utility-assets-import``.
This script prepares a throwaway database, then calls that command so
``deliverables/`` is the rejects file, map, summary, and run log from that run.
"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from utility_assets import models  # noqa: F401 - register tables
from utility_assets.cli import main as import_csv
from utility_assets.db import Base, get_engine


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "survey_export.csv"
DESTINATION = ROOT / "deliverables"


def main() -> None:
    os.chdir(ROOT)
    DESTINATION.mkdir(exist_ok=True)
    log_path = DESTINATION / "ingestion.log"
    log_path.unlink(missing_ok=True)
    with TemporaryDirectory(prefix="utility-assets-deliverables-") as directory:
        database = Path(directory) / "review.sqlite3"
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{database.as_posix()}"
        get_engine.cache_clear()
        engine = get_engine()
        try:
            Base.metadata.create_all(engine)
            exit_code = import_csv(
                [
                    "data/survey_export.csv",
                    "--rejects",
                    str(DESTINATION / "rejects.csv"),
                    "--map",
                    str(DESTINATION / "map.geojson"),
                    "--summary",
                    str(DESTINATION / "summary.txt"),
                    "--log",
                    str(log_path),
                ]
            )
            if exit_code != 0:
                raise RuntimeError(f"utility-assets-import exited with code {exit_code}")
            log_line = log_path.read_text(encoding="utf-8").strip()
            if "status=completed" not in log_line or "read=62" not in log_line:
                raise RuntimeError(f"unexpected ingestion log: {log_line}")
            if "accepted=51" not in log_line or "rejected=11" not in log_line:
                raise RuntimeError(f"unexpected ingestion log: {log_line}")
        finally:
            get_engine().dispose()
            get_engine.cache_clear()
    print("Deliverables written by utility-assets-import: 51 accepted, 11 rejected")


if __name__ == "__main__":
    main()
