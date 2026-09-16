"""Each test gets an isolated temporary SQLite database for schema-level tests.

PostgreSQL integration checks will use an isolated Compose test service later.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from utility_assets.db import Base, configure_sqlite_transactions
from utility_assets import models  # noqa: F401 - registers table metadata


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}")
    configure_sqlite_transactions(engine)

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()
