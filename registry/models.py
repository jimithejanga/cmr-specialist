"""Mock CMR registry models: the six frozen tables + the counters helper.

Mirrors ``schema.sql``. Portable column types (SQLite pilot, Postgres later).
Authorship columns deliberately absent - the change feed records who/when.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import text as _text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class RegistryBase(DeclarativeBase):
    pass


class Profile(RegistryBase):
    __tablename__ = "profiles"

    profile_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    nin: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="person")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Vehicle(RegistryBase):
    __tablename__ = "vehicles"

    vehicle_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    plate: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    chassis: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    owner_profile_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("profiles.profile_id"), nullable=False)
    cert_state: Mapped[str] = mapped_column(String(16), default="none")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Transfer(RegistryBase):
    __tablename__ = "transfers"

    transfer_ref: Mapped[str] = mapped_column(String(16), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("vehicles.vehicle_id"), nullable=False)
    seller_profile_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("profiles.profile_id"), nullable=False)
    buyer_profile_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("profiles.profile_id"), nullable=False)
    doc_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="initiated")
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Receipt(RegistryBase):
    __tablename__ = "receipts"

    rrr: Mapped[str] = mapped_column(String(12), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="unpaid")
    amount_kobo: Mapped[int] = mapped_column(Integer, nullable=False)
    linked_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Certificate(RegistryBase):
    __tablename__ = "certificates"

    cert_no: Mapped[str] = mapped_column(String(32), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("vehicles.vehicle_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active")
    request_age_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


# At most one active certificate per vehicle; history rows (expired/revoked)
# are untouched by this index. Declared after the class (needs the table).
Index("uq_active_cert_per_vehicle", Certificate.vehicle_id, unique=True,
      sqlite_where=_text("status = 'active'"),
      postgresql_where=_text("status = 'active'"))


class Token(RegistryBase):
    __tablename__ = "tokens"

    token_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        String(16), ForeignKey("profiles.profile_id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    template: Mapped[str] = mapped_column(String(64), default="generic")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class RegistryCounter(RegistryBase):
    """Deterministic TRF-/CORR-/tok- numbering (registry-internal machinery)."""

    __tablename__ = "registry_counters"

    name: Mapped[str] = mapped_column(String(16), primary_key=True)
    next_val: Mapped[int] = mapped_column(Integer, default=1)


class RegistryChange(RegistryBase):
    """Append-only change feed. Written in-transaction by repository
    mutations; read by operators. No update/delete path exists on purpose."""

    __tablename__ = "registry_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    table_name: Mapped[str] = mapped_column(String(32), nullable=False)
    row_key: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
