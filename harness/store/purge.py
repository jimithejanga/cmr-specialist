"""Shed retention CLI: python -m harness.store.purge [--days 90]."""
from __future__ import annotations

import argparse

from harness.store import repository as R
from harness.store.database import SessionLocal, init_db


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()
    init_db()
    db = SessionLocal()
    try:
        removed = R.purge_cases_older_than(db, days=args.days)
    finally:
        db.close()
    print(f"purged {removed} case(s) older than {args.days} days")


if __name__ == "__main__":
    main()
