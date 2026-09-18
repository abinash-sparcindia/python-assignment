"""Measure assignment targets with the synthetic CSV and disposable SQLite.

This is a local development check, not the final Docker/PostgreSQL benchmark.
"""

import os
import platform
import secrets
import statistics
import tempfile
from pathlib import Path
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from utility_assets.auth import get_session, hash_password
from utility_assets.db import Base, configure_sqlite_transactions
from utility_assets.ingestion import OutputPaths, ingest_csv
from utility_assets.main import create_app
from utility_assets.models import User


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "survey_export.csv"


def measure(client: TestClient, path: str, headers: dict[str, str], repeats: int = 20) -> tuple[float, float]:
    durations = []
    server_durations = []
    for _ in range(repeats):
        started = perf_counter()
        response = client.get(path, headers=headers)
        durations.append((perf_counter() - started) * 1000)
        assert response.status_code == 200, (path, response.status_code, response.text)
        server_durations.append(float(response.headers["x-response-time-ms"]))
    return max(durations), statistics.median(server_durations)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="utility-assets-benchmark-") as directory:
        temporary = Path(directory)
        database_url = f"sqlite+pysqlite:///{temporary / 'benchmark.sqlite3'}"
        os.environ["DATABASE_URL"] = database_url
        os.environ["SIGNING_SECRET"] = secrets.token_urlsafe(48)
        os.environ["REQUESTS_PER_MINUTE"] = "1000"
        engine = create_engine(database_url)
        configure_sqlite_transactions(engine)
        Base.metadata.create_all(engine)

        started = perf_counter()
        result = ingest_csv(SAMPLE, paths=OutputPaths.in_directory(temporary / "output"), engine=engine)
        ingestion_seconds = perf_counter() - started
        assert (result.rows_read, result.accepted, result.rejected) == (62, 51, 11)

        password = secrets.token_urlsafe(24)
        with Session(engine) as session:
            session.add(User(username="benchmark-user", password_hash=hash_password(password), role="surveyor"))
            session.commit()

        app = create_app()

        def test_session():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = test_session
        with TestClient(app) as client:
            login = client.post("/auth/login", json={"username": "benchmark-user", "password": password})
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            client.get("/reports/summary", headers=headers)  # warm the cache
            timings = {
                "asset page of 25": ("/assets?limit=25", 500),
                "single asset": (f"/assets/{result.accepted_records[0].asset_id}", 200),
                "cached summary": ("/reports/summary", 100),
            }
            print(f"Environment: {platform.platform()} | Python {platform.python_version()} | SQLite/TestClient")
            print(f"Synthetic input: {result.rows_read} rows, {result.accepted} accepted, {result.rejected} rejected")
            for label, (path, target) in timings.items():
                maximum, server_median = measure(client, path, headers)
                print(f"{label}: max client {maximum:.2f} ms; median app {server_median:.2f} ms; target < {target} ms")
            print(f"62-row ingestion: {ingestion_seconds:.3f} s; target < 5 s")
        engine.dispose()


if __name__ == "__main__":
    main()
