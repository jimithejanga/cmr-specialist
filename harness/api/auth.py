"""Shed locks: password hashing, session stamps, and the current-user dependency.

No new dependencies: PBKDF2-HMAC-SHA256 from hashlib, tokens from secrets.
Legacy X-API-Key machine callers keep working; browsers log in as people.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from configs.settings import settings
from harness.store import models as M

SESSION_TTL_HOURS = 12
_PBKDF2_ROUNDS = 210_000


def _utcnow():
    return datetime.now(timezone.utc)


def hash_password(cleartext: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", cleartext.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(cleartext: str, stored: str) -> bool:
    try:
        _, rounds, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", cleartext.encode(),
                                 bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def create_user(db: Session, *, username: str, password: str,
                display_name: str | None = None, make_admin: bool = False) -> M.User:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    existing = db.scalar(select(M.User).where(M.User.username == username))
    if existing:
        raise ValueError("username already exists")
    first = db.scalar(select(M.User)) is None
    user = M.User(username=username, display_name=display_name or username,
                  password_hash=hash_password(password),
                  is_admin=1 if (first or make_admin) else 0)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, *, username: str, password: str) -> M.User | None:
    user = db.scalar(select(M.User).where(M.User.username == username))
    if not user or not user.active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def issue_session(db: Session, user: M.User) -> M.UserSession:
    token = secrets.token_urlsafe(32)
    sess = M.UserSession(token=token, user_id=user.id,
                         expires_at=_utcnow() + timedelta(hours=SESSION_TTL_HOURS))
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def revoke_session(db: Session, token: str) -> None:
    sess = db.get(M.UserSession, token)
    if sess:
        db.delete(sess)
        db.commit()


def user_from_token(db: Session, token: str) -> M.User | None:
    sess = db.get(M.UserSession, token)
    if not sess:
        return None
    exp = sess.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _utcnow():
        db.delete(sess)
        db.commit()
        return None
    user = db.get(M.User, sess.user_id)
    if not user or not user.active:
        return None
    return user


def session_user(db: Session, authorization: Optional[str]) -> M.User | None:
    """The logged-in human, if any. Machine API keys are NOT session users."""
    if authorization and authorization.lower().startswith("bearer "):
        return user_from_token(db, authorization[7:].strip())
    return None


def resolve_actor(db: Session, *, authorization: Optional[str],
                  x_api_key: Optional[str]) -> str | None:
    """Who is calling? Session user preferred, legacy API key as machine actor."""
    if authorization and authorization.lower().startswith("bearer "):
        user = user_from_token(db, authorization[7:].strip())
        if user:
            return user.username
    if settings.HARNESS_API_KEY and x_api_key:
        if hmac.compare_digest(x_api_key, settings.HARNESS_API_KEY):
            return "api-key"
    return None


def require_admin(db: Session, *, authorization: Optional[str],
                  x_api_key: Optional[str]) -> M.User:
    """Admin gate for the observability site. Raises 401/403."""
    from fastapi import HTTPException

    actor = resolve_actor(db, authorization=authorization, x_api_key=x_api_key)
    if not actor:
        raise HTTPException(status_code=401, detail="login required")
    if actor == "api-key":
        raise HTTPException(status_code=403, detail="admin login required")
    user = db.scalar(select(M.User).where(M.User.username == actor))
    if not user or not user.active or not getattr(user, "is_admin", 0):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def ensure_schema(engine) -> None:
    """Tolerant migration for pre-admin databases: add users.is_admin if absent."""
    from sqlalchemy import inspect, text

    try:
        cols = [c["name"] for c in inspect(engine).get_columns("users")]
    except Exception:
        return
    if "is_admin" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"))
        # first user owns the site: promote when nobody is admin yet
        from harness.store.database import SessionLocal as _SL
        db = _SL()
        try:
            if db.scalar(select(M.User).where(M.User.is_admin == 1)) is None:
                first = db.scalars(select(M.User).order_by(M.User.created_at)).first()
                if first:
                    first.is_admin = 1
                    db.commit()
        finally:
            db.close()
