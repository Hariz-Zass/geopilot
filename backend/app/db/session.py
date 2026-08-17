from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Return the process-owned SQLAlchemy engine."""

    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_db_session() -> Generator[Session, None, None]:
    """Request-scoped transaction/session boundary.

    Domain services explicitly commit successful writes. The dependency always
    closes the session and never hides a failed transaction.
    """

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
