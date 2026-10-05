"""Mock CMR registry engine/session factory.

Separate database, separate credentials, separate file from the agent's own
store: ``REGISTRY_DATABASE_URL`` (default ``var/registry.db``). The pilot
runs SQLite; the VM runs Postgres by setting one env var - the agent's code
does not move, only this URL does.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from registry.models import RegistryBase


def _default_url() -> str:
    from configs.settings import settings

    return str(getattr(settings, "REGISTRY_DATABASE_URL", "")) or (
        f"sqlite:///{Path(settings.BASE_DIR) / 'var' / 'registry.db'}")


def _ensure_sqlite_parent(url: str) -> None:
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1).split("?")[0]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)


def build_registry_engine(database_url: str | None = None):
    url = database_url or os.getenv("REGISTRY_DATABASE_URL") or _default_url()
    _ensure_sqlite_parent(url)
    kwargs: dict = {"future": True}
    if url.startswith("sqlite:"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
    return create_engine(url, **kwargs)


engine = build_registry_engine()
RegistrySession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_registry_db(seed_if_empty: bool = True) -> None:
    """Create tables + active-certificates view. Seeds ONLY when empty, so a
    restart never wipes live rows - reseeding is an explicit reset, not a boot
    side effect."""
    from registry import models as _models  # noqa: F401 (register tables)

    RegistryBase.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIEW IF NOT EXISTS active_certificates AS "
            "SELECT * FROM certificates WHERE status = 'active'"))
    if seed_if_empty:
        from sqlalchemy import func, select

        with RegistrySession() as session:
            empty = session.scalar(select(func.count()).select_from(_models.Profile)) == 0
            if empty:
                from registry import seed as _seed

                _seed.seed_all(session)
                session.commit()
