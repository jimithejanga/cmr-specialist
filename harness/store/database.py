"""SQLAlchemy engine/session factory.

PostgreSQL is the system of record (DATABASE_URL=postgresql+psycopg://...).
SQLite is the zero-ops local fallback (DATABASE_URL=sqlite:///...).
"""
from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1).split("?")[0]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def build_engine(database_url: str | None = None):
    from configs.settings import settings

    url = database_url or os.getenv("DATABASE_URL", settings.DATABASE_URL)
    _ensure_sqlite_parent(url)
    kwargs: dict = {"future": True}
    if url.startswith("sqlite:"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = int(os.getenv("DB_POOL_SIZE", "5"))
        kwargs["max_overflow"] = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    return create_engine(url, **kwargs)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from harness.store import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
