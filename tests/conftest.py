"""Use disposable SQLite by default or an explicitly named PostgreSQL test DB."""

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from utility_assets.db import Base, configure_sqlite_transactions
from utility_assets.report_cache import summary_cache
from utility_assets import models  # noqa: F401 - registers table metadata


@pytest.fixture
def db_session(tmp_path):
    test_url = os.environ.get("TEST_DATABASE_URL")
    if test_url:
        database_name = make_url(test_url).database or ""
        if not database_name.endswith("_test"):
            raise RuntimeError("TEST_DATABASE_URL must name an isolated database ending in _test")
    engine = create_engine(test_url or f"sqlite+pysqlite:///{tmp_path / 'test.sqlite3'}")
    configure_sqlite_transactions(engine)

    if test_url:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    summary_cache.clear()
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.rollback()
    if test_url:
        Base.metadata.drop_all(engine)
    engine.dispose()
