"""Mock CMR registry seed: the deterministic world, translated to tables.

Same people, cars, and receipts as the legacy dict seed - now with keys
instead of labels: ownership is a profile FK, the NIN lives on the profile
row (UNIQUE does the work string-matching used to do), and the seed receipt
starts UNLINKED (NULL) so the link WRITE has something honest to do.
"""
from __future__ import annotations

from datetime import datetime

from registry import repository as repo
from registry.models import RegistryCounter


def seed_all(session) -> None:
    repo.create_profile(session, profile_id="prof-001", full_name="Ada Obi",
                        phone="08012345678", email="ada@example.com",
                        nin="12345678901", synthetic=False)
    repo.create_vehicle(session, vehicle_id="veh-001", plate="ABC123XY",
                        chassis="CHS987654321", owner_profile_id="prof-001",
                        cert_state="issued", synthetic=False)
    repo.create_receipt(session, rrr="123456789012", status="paid",
                        amount_kobo=500000,  # NGN 5,000 in integer kobo
                        paid_at=datetime(2026, 9, 10), synthetic=False)
    session.add(_cert())
    for name in ("TRF", "CORR", "TOK"):
        session.merge(RegistryCounter(name=name, next_val=1))
    session.flush()


def _cert():
    from registry.models import Certificate

    return Certificate(cert_no="CMR-0001", vehicle_id="veh-001", status="active",
                       request_age_h=30, expires_at=datetime(2027, 1, 1),
                       is_synthetic=False)
