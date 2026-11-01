"""Database engine, session management and SQLAlchemy base.

The data-access layer is intentionally thin and URL-driven so the SQLite
database can be replaced with PostgreSQL by changing DATABASE_URL.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from flask import g, has_app_context
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _enable_sqlite_pragmas(dbapi_connection, _record) -> None:
    # SQLite ignores foreign keys unless enabled per connection.
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_engine(database_url: str) -> Engine:
    """Create (or recreate) the engine. Safe to call from tests."""
    global _engine, _session_factory  # noqa: PLW0603

    if _engine is not None:
        _engine.dispose()

    connect_args: dict = {}
    engine_kwargs: dict = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        if ":memory:" in database_url:
            # One shared connection keeps an in-memory DB visible to all sessions.
            engine_kwargs["poolclass"] = StaticPool
            connect_args["timeout"] = 30

    _engine = create_engine(
        database_url,
        future=True,
        connect_args=connect_args,
        pool_pre_ping=True,
        **engine_kwargs,
    )

    if database_url.startswith("sqlite"):
        event.listen(_engine, "connect", _enable_sqlite_pragmas)
        if ":memory:" not in database_url:
            # WAL improves concurrent read behaviour for the local dev server.
            @event.listens_for(_engine, "connect")
            def _wal(dbapi_connection, _record):  # pragma: no cover - pragma only
                if isinstance(dbapi_connection, sqlite3.Connection):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=5000")
                    cursor.close()

    _session_factory = sessionmaker(
        bind=_engine, expire_on_commit=False, autoflush=False, future=True
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database engine has not been initialised")
    return _engine


def new_session() -> Session:
    if _session_factory is None:
        raise RuntimeError("Database session factory has not been initialised")
    return _session_factory()


def get_session() -> Session:
    """Return the request-scoped session (created lazily)."""
    if not has_app_context():
        return new_session()
    if "db_session" not in g:
        g.db_session = new_session()
    return g.db_session


def close_session(_exc: BaseException | None = None) -> None:
    if not has_app_context():
        return
    session = g.pop("db_session", None)
    if session is not None:
        try:
            if _exc is not None:
                session.rollback()
        finally:
            session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for scripts and tests (not tied to a Flask request)."""
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    # Import models so they are registered on Base.metadata.
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
