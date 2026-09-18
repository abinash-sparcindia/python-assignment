"""Regenerate the three review artifacts from the synthetic input CSV."""

from pathlib import Path
from tempfile import TemporaryDirectory
from shutil import copyfile

from sqlalchemy import create_engine

from utility_assets.db import Base, configure_sqlite_transactions
from utility_assets.ingestion import OutputPaths, ingest_csv
from utility_assets import models  # noqa: F401 - register tables


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "survey_export.csv"
DESTINATION = ROOT / "deliverables"


def main() -> None:
    with TemporaryDirectory(prefix="utility-assets-deliverables-") as directory:
        temporary = Path(directory)
        engine = create_engine(f"sqlite+pysqlite:///{temporary / 'review.sqlite3'}")
        configure_sqlite_transactions(engine)
        try:
            Base.metadata.create_all(engine)
            paths = OutputPaths.in_directory(temporary / "output")
            result = ingest_csv(SOURCE, paths=paths, engine=engine)
            if (result.rows_read, result.accepted, result.rejected) != (62, 51, 11):
                raise RuntimeError("synthetic fixture counts changed; review the outputs before publishing")
            DESTINATION.mkdir(exist_ok=True)
            for source, target in (
                (paths.rejects, DESTINATION / "rejects.csv"),
                (paths.map_file, DESTINATION / "map.geojson"),
                (paths.summary, DESTINATION / "summary.txt"),
            ):
                copyfile(source, target)
        finally:
            engine.dispose()
    print("Synthetic deliverables regenerated: 51 accepted, 11 rejected")


if __name__ == "__main__":
    main()
