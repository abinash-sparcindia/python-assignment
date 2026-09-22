"""Checks for one-command startup and operator-facing CLI behavior."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from utility_assets.cli import main as cli_main
from utility_assets.db import get_engine
from utility_assets.models import Asset, Visit
from utility_assets.startup import initialize_review_database
from utility_assets import startup


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "survey_export.csv"


def test_startup_migrates_seeds_and_skips_repeated_seed(tmp_path, monkeypatch):
    database = tmp_path / "review.sqlite3"
    output = tmp_path / "output"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database.as_posix()}")
    monkeypatch.setenv("SURVEY_CSV", str(SAMPLE))
    monkeypatch.setenv("OUTPUT_DIR", str(output))
    get_engine.cache_clear()
    try:
        initialize_review_database()
        initialize_review_database()
        with Session(get_engine()) as session:
            assert session.scalar(select(func.count()).select_from(Asset)) == 51
            assert session.scalar(select(func.count()).select_from(Visit)) == 51
        assert output.joinpath("rejects.csv").exists()
        assert output.joinpath("map.geojson").exists()
        assert output.joinpath("summary.txt").exists()
        assert len(output.joinpath("ingestion.log").read_text(encoding="utf-8").splitlines()) == 1
    finally:
        get_engine().dispose()
        get_engine.cache_clear()


def test_cli_creates_local_database_from_csv_path_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database = tmp_path / "survey.sqlite3"
    monkeypatch.setattr("utility_assets.cli.LOCAL_DATABASE", database)
    get_engine.cache_clear()
    try:
        exit_code = cli_main([str(SAMPLE)])
        text = capsys.readouterr().out
        assert exit_code == 0
        assert "Rows read: 62" in text
        assert "Rows accepted: 51" in text
        assert "Rows rejected: 11" in text
        assert database.exists()
        assert Path("output/rejects.csv").exists()
        assert Path("output/map.geojson").exists()
        assert Path("output/summary.txt").exists()
    finally:
        get_engine().dispose()
        get_engine.cache_clear()


def test_cli_help_and_run_summary(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as help_exit:
        cli_main(["--help"])
    assert help_exit.value.code == 0
    assert "--strict" in capsys.readouterr().out

    database = tmp_path / "cli.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    from utility_assets.db import Base
    from utility_assets import models  # noqa: F401

    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database.as_posix()}")
    get_engine.cache_clear()
    output = tmp_path / "output"
    try:
        exit_code = cli_main(
            [
                str(SAMPLE),
                "--rejects", str(output / "rejects.csv"),
                "--map", str(output / "map.geojson"),
                "--summary", str(output / "summary.txt"),
                "--log", str(output / "ingestion.log"),
                "--nearest", "20.2411", "85.7813",
                "--surveyors-on", "2026-09-02",
            ]
        )
        text = capsys.readouterr().out
        assert exit_code == 0
        assert "Rows read: 62" in text
        assert "Rows accepted: 51" in text
        assert "Rows rejected: 11" in text
        assert "Nearest asset: PL-0001 (0.000 km)" in text
        assert "Surveyors on 2026-09-02:" in text
    finally:
        get_engine().dispose()
        get_engine.cache_clear()


def test_review_entrypoint_migrates_seeds_identity_then_starts_api(tmp_path, monkeypatch):
    database = tmp_path / "entrypoint.sqlite3"
    credentials = tmp_path / "review-admin.txt"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database.as_posix()}")
    monkeypatch.setenv("SURVEY_CSV", str(SAMPLE))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("REVIEW_CREDENTIALS_FILE", str(credentials))
    monkeypatch.setenv("REVIEW_MODE", "true")
    monkeypatch.delenv("SIGNING_SECRET", raising=False)
    started = []
    monkeypatch.setattr(startup.uvicorn, "run", lambda *args, **kwargs: started.append((args, kwargs)))
    get_engine.cache_clear()
    try:
        startup.main()
        assert credentials.exists()
        assert started == [(("utility_assets.main:app",), {"host": "0.0.0.0", "port": 8000, "access_log": False})]
        with Session(get_engine()) as session:
            assert session.scalar(select(func.count()).select_from(Asset)) == 51
    finally:
        get_engine().dispose()
        get_engine.cache_clear()
