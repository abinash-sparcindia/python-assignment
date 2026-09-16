"""SQLAlchemy engine and declarative base."""

from functools import lru_cache

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from utility_assets.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    configure_sqlite_transactions(engine)
    return engine


def configure_sqlite_transactions(engine: Engine) -> None:
    """Make SQLite savepoints participate in an outer transaction.

    SQLite's legacy driver mode can release a savepoint before a real BEGIN,
    leaving rows behind after strict-mode rollback. PostgreSQL needs no hook.
    """

    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def on_connect(connection, _record):
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")

    @event.listens_for(engine, "begin")
    def on_begin(connection):
        connection.exec_driver_sql("BEGIN")


def session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
