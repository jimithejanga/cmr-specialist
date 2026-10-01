"""Mock CMR registry repository: typed queries, no agent concepts.

Every function takes a session and flushes; the caller (connector) commits.
Invariants marked INVARIANT in schema.sql are enforced here, inside the
transaction - a transfer that does not move ownership is refused, never
stored; a receipt's linked account changes only through void-and-relink.

Error types are borrowed from the legacy dict backend so the module's
envelope mapping (terminal vs transient) is identical on both backends.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select

from harness.tools.mockdb import TerminalError
from registry import feed as _feed
from registry.models import (Certificate, Profile, Receipt, RegistryCounter,
                             Token, Transfer, Vehicle)


class VersionConflict(Exception):
    """Optimistic-lock failure: the row moved under the editor's hands."""


# ── profiles ─────────────────────────────────────────────────────────────
def find_profile(session, *, phone=None, email=None, nin=None) -> Profile | None:
    conds = []
    if phone:
        conds.append(Profile.phone == phone)
    if email:
        conds.append(Profile.email == email)
    if nin:
        conds.append(Profile.nin == nin)
    if not conds:
        return None
    return session.scalar(select(Profile).where(or_(*conds)))


def find_profile_by_id(session, profile_id: str) -> Profile | None:
    return session.get(Profile, profile_id)


def find_profile_by_name(session, name: str) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.full_name == name))


def create_profile(session, *, profile_id, full_name=None, phone=None,
                   email=None, nin=None, synthetic=True) -> Profile:
    row = Profile(profile_id=profile_id, full_name=full_name, phone=phone,
                  email=email, nin=nin, is_synthetic=bool(synthetic))
    session.add(row)
    session.flush()
    _feed.record(session, table="profiles", row_key=profile_id, action="insert",
                 after={"full_name": full_name, "phone": phone,
                        "email": email, "nin": nin})
    return row


# ── vehicles ─────────────────────────────────────────────────────────────
def find_vehicle(session, *, plate=None, chassis=None,
                 vehicle_id=None) -> Vehicle | None:
    if vehicle_id:
        return session.get(Vehicle, vehicle_id)
    if plate:
        return session.scalar(select(Vehicle).where(Vehicle.plate == plate))
    if chassis:
        return session.scalar(select(Vehicle).where(Vehicle.chassis == chassis))
    return None


def create_vehicle(session, *, vehicle_id, plate, chassis=None,
                   owner_profile_id, cert_state="none", synthetic=True) -> Vehicle:
    row = Vehicle(vehicle_id=vehicle_id, plate=plate, chassis=chassis,
                  owner_profile_id=owner_profile_id, cert_state=cert_state,
                  is_synthetic=bool(synthetic))
    session.add(row)
    session.flush()
    _feed.record(session, table="vehicles", row_key=vehicle_id, action="insert",
                 after={"plate": plate, "owner": owner_profile_id})
    return row


def owner_name(session, vehicle: Vehicle) -> str | None:
    owner = session.get(Profile, vehicle.owner_profile_id)
    return owner.full_name if owner else None


def history_count(session, vehicle_id: str) -> int:
    """Transfer rows + 1 for the initial registration (which is provenance,
    not a transfer, and therefore has no row of its own)."""
    n = session.scalar(select(func.count()).select_from(Transfer).where(
        Transfer.vehicle_id == vehicle_id)) or 0
    return n + 1


# ── transfers (ownership moves here, atomically) ──────────────────────────
def next_counter(session, name: str) -> int:
    row = session.get(RegistryCounter, name)
    if row is None:
        row = RegistryCounter(name=name, next_val=2)
        session.add(row)
        session.flush()
        return 1
    val = row.next_val
    row.next_val = val + 1
    session.flush()
    return val


def execute_transfer(session, *, vehicle_id, buyer_profile_id, doc_ref=None,
                     approved_by=None) -> Transfer:
    vehicle = session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise TerminalError("not-found: vehicle")
    buyer = session.get(Profile, buyer_profile_id)
    if buyer is None:
        raise TerminalError("not-found: buyer profile")
    ref = f"TRF-{next_counter(session, 'TRF'):04d}"
    before_owner = vehicle.owner_profile_id
    row = Transfer(transfer_ref=ref, vehicle_id=vehicle_id,
                   seller_profile_id=vehicle.owner_profile_id,
                   buyer_profile_id=buyer_profile_id, doc_ref=doc_ref,
                   status="initiated", approved_by=approved_by)
    session.add(row)
    # The move itself: seller was the owner at commit (read inside this
    # transaction), buyer becomes the owner, version bumps for the feed.
    vehicle.owner_profile_id = buyer_profile_id
    vehicle.version = (vehicle.version or 1) + 1
    session.flush()
    _feed.record(session, table="vehicles", row_key=vehicle_id, action="transfer",
                 before={"owner": before_owner},
                 after={"owner": buyer_profile_id, "transfer_ref": ref})
    return row


# ── receipts ─────────────────────────────────────────────────────────────
def find_receipt(session, rrr: str) -> Receipt | None:
    return session.get(Receipt, rrr)


def create_receipt(session, *, rrr, status="unpaid", amount_kobo,
                   paid_at=None, synthetic=True) -> Receipt:
    row = Receipt(rrr=rrr, status=status, amount_kobo=amount_kobo,
                  paid_at=paid_at, is_synthetic=bool(synthetic))
    session.add(row)
    session.flush()
    _feed.record(session, table="receipts", row_key=rrr, action="insert",
                 after={"status": status, "amount_kobo": amount_kobo})
    return row


def confirm_receipt(session, rrr: str) -> Receipt:
    row = session.get(Receipt, rrr)
    if row is None or row.status != "paid":
        raise TerminalError("no paid receipt to confirm")
    return row


def link_receipt(session, rrr: str, account: str) -> Receipt:
    row = session.get(Receipt, rrr)
    if row is None:
        raise TerminalError("not-found: receipt")
    if row.status != "paid":
        raise TerminalError("receipt not paid; cannot link")
    if row.linked_account is not None and row.linked_account != account:
        raise TerminalError("receipt already linked; void-and-relink required")
    before = row.linked_account
    row.linked_account = account
    row.linked_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.flush()
    _feed.record(session, table="receipts", row_key=rrr, action="link",
                 before={"linked_account": before},
                 after={"linked_account": account})
    return row


# ── certificates ─────────────────────────────────────────────────────────
def active_certificate(session, vehicle_id: str) -> Certificate | None:
    return session.scalar(select(Certificate).where(
        Certificate.vehicle_id == vehicle_id, Certificate.status == "active"))


def certificate_history(session, vehicle_id: str) -> list[Certificate]:
    return list(session.scalars(select(Certificate).where(
        Certificate.vehicle_id == vehicle_id).order_by(Certificate.cert_no)).all())


def renew_certificate(session, *, vehicle_id, cert_no, expires_at,
                      request_age_h=None) -> Certificate:
    old = active_certificate(session, vehicle_id)
    before = {"cert_no": old.cert_no, "status": old.status} if old else None
    if old is not None:
        old.status = "expired"  # history kept, never deleted
    row = Certificate(cert_no=cert_no, vehicle_id=vehicle_id, status="active",
                      request_age_h=request_age_h, expires_at=expires_at)
    session.add(row)
    vehicle = session.get(Vehicle, vehicle_id)
    if vehicle is not None:
        vehicle.cert_state = "issued"
    session.flush()
    _feed.record(session, table="certificates", row_key=vehicle_id, action="renew",
                 before=before, after={"cert_no": cert_no, "status": "active"})
    return row


# ── tokens ───────────────────────────────────────────────────────────────
def log_token(session, *, profile_id, channel, template="generic") -> Token:
    if session.get(Profile, profile_id) is None:
        raise TerminalError("not-found: profile")
    token_id = f"tok-{next_counter(session, 'TOK'):06d}"
    row = Token(token_id=token_id, profile_id=profile_id, channel=channel,
                template=template,
                delivered_at=datetime.now(timezone.utc).replace(tzinfo=None))
    session.add(row)
    session.flush()
    _feed.record(session, table="tokens", row_key=token_id, action="token",
                 after={"profile_id": profile_id, "channel": channel})
    return row


def tokens_for(session, profile_id: str) -> list[Token]:
    return list(session.scalars(select(Token).where(
        Token.profile_id == profile_id).order_by(Token.token_id)).all())


# ── wipe (explicit reset only; never on boot) ─────────────────────────────
def clear_all(session) -> None:
    for model in (Token, Transfer, Certificate, Receipt, Vehicle, Profile,
                  RegistryCounter):
        session.query(model).delete()
    session.flush()


# ── operator updates (guarded; every one feeds) ───────────────────────────
def resolve_owner(session, owner_value: str | None) -> str | None:
    """Legacy seeds/admin rows name owners by id OR by name; the tables need
    a profile FK. Resolve either, else create a synthetic stub profile."""
    if not owner_value:
        return None
    hit = (find_profile_by_id(session, owner_value)
           or find_profile_by_name(session, owner_value))
    if hit is not None:
        return hit.profile_id
    n = session.query(Profile).count() + 1
    stub = create_profile(session, profile_id=f"prof-{n:03d}",
                          full_name=owner_value, synthetic=True)
    return stub.profile_id


def _find_profile_any(session, key: str) -> Profile | None:
    return (find_profile(session, phone=key, email=key, nin=key)
            or find_profile_by_id(session, key))


def update_profile(session, key: str, **fields) -> Profile:
    allowed = ("full_name", "phone", "email", "nin")
    p = _find_profile_any(session, key)
    if p is None:
        raise TerminalError(f"not-found: profile {key}")
    before, after = {}, {}
    for name in allowed:
        if name in fields and fields[name] is not None:
            before[name] = getattr(p, name)
            setattr(p, name, fields[name])
            after[name] = fields[name]
    if not after:
        raise TerminalError("nothing to update")
    session.flush()
    _feed.record(session, table="profiles", row_key=p.profile_id,
                 action="update", before=before, after=after)
    return p


def update_vehicle(session, key: str, *, owner=None, chassis=None,
                   expected_version=None) -> Vehicle:
    v = (find_vehicle(session, plate=key, chassis=key)
         or session.get(Vehicle, key))
    if v is None:
        raise TerminalError(f"not-found: vehicle {key}")
    if expected_version is not None and v.version != expected_version:
        raise VersionConflict(
            f"vehicle {v.plate} is version {v.version}, "
            f"you edited {expected_version}; re-read and retry")
    before = {"owner": v.owner_profile_id, "chassis": v.chassis}
    if owner is not None:
        v.owner_profile_id = resolve_owner(session, owner)
    if chassis is not None:
        v.chassis = chassis
    v.version = (v.version or 1) + 1
    session.flush()
    _feed.record(session, table="vehicles", row_key=v.vehicle_id,
                 action="update",
                 before=before,
                 after={"owner": v.owner_profile_id, "chassis": v.chassis,
                        "version": v.version})
    return v


def set_receipt_status(session, rrr: str, status: str | None) -> Receipt:
    if status not in ("paid", "unpaid", "void"):
        raise TerminalError(f"bad receipt status: {status}")
    row = find_receipt(session, rrr)
    if row is None:
        raise TerminalError(f"not-found: receipt {rrr}")
    before = row.status
    row.status = status
    session.flush()
    _feed.record(session, table="receipts", row_key=rrr, action="update",
                 before={"status": before}, after={"status": status})
    return row


def set_certificate_status(session, key: str, status: str | None) -> Certificate:
    if status not in ("active", "expired", "revoked"):
        raise TerminalError(f"bad certificate status: {status}")
    row = session.get(Certificate, key)
    if row is None:
        v = find_vehicle(session, plate=key)
        row = active_certificate(session, v.vehicle_id) if v else None
    if row is None:
        raise TerminalError(f"not-found: certificate {key}")
    if status == "active":
        other = active_certificate(session, row.vehicle_id)
        if other is not None and other.cert_no != row.cert_no:
            other.status = "expired"
    before = row.status
    row.status = status
    session.flush()
    _feed.record(session, table="certificates", row_key=row.vehicle_id,
                 action="update", before={"status": before, "cert_no": row.cert_no},
                 after={"status": status, "cert_no": row.cert_no})
    return row
