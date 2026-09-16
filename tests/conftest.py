"""Each test gets an isolated temporary SQLite database for schema-level tests.

PostgreSQL integration checks will use an isolated Compose test service later.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from utility_assets.db import Base
from utility_assets import models  # noqa: F401 - registers table metadata


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()
