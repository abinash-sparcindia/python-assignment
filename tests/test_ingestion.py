"""Ingestion behavior against disposable databases and output directories."""

import csv
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utility_assets.ingestion import IngestionInputError, OutputPaths, ingest_csv
from utility_assets.models import Asset, SeedRun, Visit
from utility_assets.validation import EXPECTED_COLUMNS


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "survey_export.csv"
TODAY = date(2026, 9, 16)


def counts(engine) -> tuple[int, int]:
    with Session(engine) as session:
        return (
            session.scalar(select(func.count()).select_from(Asset)) or 0,
            session.scalar(select(func.count()).select_from(Visit)) or 0,
        )


def test_import_writes_outputs_and_keeps_all_bad_rows(db_session, tmp_path):
    paths = OutputPaths.in_directory(tmp_path / "output")
    result = ingest_csv(SAMPLE, paths=paths, engine=db_session.bind, today=TODAY)

    assert (result.rows_read, result.accepted, result.rejected) == (62, 51, 11)
    assert counts(db_session.bind) == (51, 51)
    with paths.rejects.open(newline="", encoding="utf-8") as file:
        rejects = list(csv.DictReader(file))
    assert len(rejects) == 11
    assert rejects[0]["latitude"] == "91.2"
    assert "latitude" in rejects[0]["reason"]
    assert rejects[2]["asset_id"] == "PL-0001"
    assert "already in use" in rejects[2]["reason"]

    geojson = json.loads(paths.map_file.read_text(encoding="utf-8"))
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 51
    first = geojson["features"][0]
    assert first["geometry"] == {"type": "Point", "coordinates": [85.7813, 20.2411]}
    assert first["properties"]["condition_band"] == "CRITICAL"
    assert first["properties"]["attributes"] == {"height_m": 9}
    summary = paths.summary.read_text(encoding="utf-8")
    assert "UTILITY ASSET SURVEY" in summary
    assert "Rows accepted: 51" in summary
    assert "Rows rejected: 11" in summary
    assert "Survey extent:" in summary
    assert "Need repair" in summary
    assert "status=completed read=62 accepted=51 rejected=11" in paths.log.read_text(encoding="utf-8")


def test_strict_mode_rolls_back_every_valid_row(db_session, tmp_path):
    paths = OutputPaths.in_directory(tmp_path / "output")
    result = ingest_csv(SAMPLE, paths=paths, engine=db_session.bind, strict=True, today=TODAY)

    assert result.aborted is True
    assert (result.rows_read, result.accepted, result.rejected) == (62, 0, 1)
    assert counts(db_session.bind) == (0, 0)
    assert paths.rejects.exists()
    assert not paths.map_file.exists()
    assert not paths.summary.exists()
    assert "status=strict-aborted" in paths.log.read_text(encoding="utf-8")


def test_missing_columns_stop_before_database_changes(db_session, tmp_path):
    source = tmp_path / "missing.csv"
    source.write_text("asset_id,name\nPL-0001,Test pole\n", encoding="utf-8")
    paths = OutputPaths.in_directory(tmp_path / "output")
    with pytest.raises(IngestionInputError, match="latitude"):
        ingest_csv(source, paths=paths, engine=db_session.bind, today=TODAY)
    assert counts(db_session.bind) == (0, 0)
    assert "status=invalid-input" in paths.log.read_text(encoding="utf-8")


def test_later_survey_adds_visit_without_duplicate_asset(db_session, tmp_path):
    source = tmp_path / "visits.csv"
    row = {
        "asset_id": "PL-0001",
        "name": "Pole one",
        "asset_type": "pole",
        "latitude": "20.25",
        "longitude": "85.82",
        "elevation_m": "",
        "surveyed_on": "2026-09-01",
        "surveyor": "Anita Das",
        "status": "active",
        "condition_score": "8",
        "attribute_json": '{"height_m":9}',
    }

    def write_row():
        with source.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=EXPECTED_COLUMNS)
            writer.writeheader()
            writer.writerow(row)

    write_row()
    paths = OutputPaths.in_directory(tmp_path / "output")
    first = ingest_csv(source, paths=paths, engine=db_session.bind, today=TODAY)
    assert first.accepted == 1
    row["surveyed_on"] = "2026-09-10"
    row["condition_score"] = "3"
    write_row()
    second = ingest_csv(source, paths=paths, engine=db_session.bind, today=TODAY)
    assert second.accepted == 1
    assert counts(db_session.bind) == (1, 2)
    with Session(db_session.bind) as session:
        asset = session.get(Asset, "PL-0001")
        assert asset is not None
        assert asset.condition_score == 3
        assert [score for score in session.scalars(select(Visit.condition_score).order_by(Visit.id))] == [8, 3]
    assert len(paths.log.read_text(encoding="utf-8").splitlines()) == 2


def test_seed_marker_makes_import_idempotent(db_session, tmp_path):
    paths = OutputPaths.in_directory(tmp_path / "output")
    first = ingest_csv(SAMPLE, paths=paths, engine=db_session.bind, today=TODAY, seed_key="review-v1")
    second = ingest_csv(SAMPLE, paths=paths, engine=db_session.bind, today=TODAY, seed_key="review-v1")
    assert first.accepted == 51
    assert second.skipped is True
    assert counts(db_session.bind) == (51, 51)
    with Session(db_session.bind) as session:
        assert session.get(SeedRun, "review-v1") is not None
    assert len(paths.log.read_text(encoding="utf-8").splitlines()) == 1


def test_strict_reimport_preserves_seeded_assets_and_visits(db_session, tmp_path):
    seed_paths = OutputPaths.in_directory(tmp_path / "seed")
    ingest_csv(SAMPLE, paths=seed_paths, engine=db_session.bind, today=TODAY, seed_key="review-v1")
    strict_paths = OutputPaths.in_directory(tmp_path / "strict")

    result = ingest_csv(SAMPLE, paths=strict_paths, engine=db_session.bind, today=TODAY, strict=True)

    assert result.aborted is True
    assert counts(db_session.bind) == (51, 51)
    assert strict_paths.rejects.exists()
    assert seed_paths.map_file.exists()
