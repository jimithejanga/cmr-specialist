"""Registry change feed: append-only memory of what happened.

Every mutation committed through ``repository.py`` writes one feed row in
the SAME transaction - a change without a feed entry is impossible by
construction. There is deliberately no update/delete path: if the feed says
it happened, it happened; if it doesn't, it didn't.

Who acted is carried on a context variable (thread-safe under the worker's
concurrency): the module sets ``agent:<formulation_id>`` around every fire,
admin routes set the operator's username, resets record ``system:reset``.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

_actor: ContextVar[str] = ContextVar("registry_actor", default="agent")


@contextmanager
def acting(name: str):
    """Run the enclosed block with feed actor ``name``."""
    token = _actor.set(name)
    try:
        yield
    finally:
        _actor.reset(token)


def current_actor() -> str:
    return _actor.get()


def record(session, *, table: str, row_key: str, action: str,
           before=None, after=None) -> None:
    """Append one feed row. Call BEFORE commit, inside the mutation's
    transaction - the caller commits both or neither."""
    from registry.models import RegistryChange

    session.add(RegistryChange(
        actor=current_actor(), action=action,
        table_name=table, row_key=str(row_key),
        before_json=json.dumps(before, default=str) if before is not None else None,
        after_json=json.dumps(after, default=str) if after is not None else None,
        at=datetime.now(timezone.utc).replace(tzinfo=None)))
    session.flush()


def list_changes(session, *, table: str | None = None,
                 actor: str | None = None, row_key: str | None = None,
                 limit: int = 100) -> list:
    """Newest-first feed query - the future service/console read exactly this."""
    from sqlalchemy import desc, select

    from registry.models import RegistryChange

    q = select(RegistryChange).order_by(desc(RegistryChange.id))
    if table:
        q = q.where(RegistryChange.table_name == table)
    if actor:
        q = q.where(RegistryChange.actor == actor)
    if row_key:
        q = q.where(RegistryChange.row_key == str(row_key))
    return list(session.scalars(q.limit(limit)).all())
