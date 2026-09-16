"""SQLAlchemy engine and declarative base."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from utility_assets.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
