"""Checked-in example artifacts agree with the synthetic ingestion pipeline."""

import json
from pathlib import Path

from sqlalchemy import create_engine

from utility_assets.db import Base, configure_sqlite_transactions
from utility_assets.ingestion import OutputPaths, ingest_csv
from utility_assets import models  # noqa: F401 - register tables


ROOT = Path(__file__).resolve().parents[1]


def _without_run_time(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("Run time:"))


def test_checked_in_outputs_match_synthetic_input(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'verification.sqlite3'}")
    configure_sqlite_transactions(engine)
    try:
        Base.metadata.create_all(engine)
        paths = OutputPaths.in_directory(tmp_path / "output")
        result = ingest_csv(ROOT / "data" / "survey_export.csv", paths=paths, engine=engine)
        assert (result.rows_read, result.accepted, result.rejected) == (62, 51, 11)
        delivered = ROOT / "deliverables"
        assert paths.rejects.read_text(encoding="utf-8") == (delivered / "rejects.csv").read_text(encoding="utf-8")
        assert json.loads(paths.map_file.read_text(encoding="utf-8")) == json.loads(
            (delivered / "map.geojson").read_text(encoding="utf-8")
        )
        assert _without_run_time(paths.summary.read_text(encoding="utf-8")) == _without_run_time(
            (delivered / "summary.txt").read_text(encoding="utf-8")
        )
    finally:
        engine.dispose()
