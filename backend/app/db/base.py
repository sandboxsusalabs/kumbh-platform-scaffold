"""Database engine and session plumbing.

One database holds the single source of truth for the visitor app, the command
dashboard and the field app. Geometry is stored as `lat`/`lon` doubles so the
scaffold also runs on SQLite for tests; the Alembic migration adds a PostGIS
`geography(Point,4326)` column plus a GiST index on PostgreSQL for nearest-facility
queries at Kumbh scale.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For workers and CLI scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Dev convenience only — production schema changes go through Alembic."""
    from app import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
