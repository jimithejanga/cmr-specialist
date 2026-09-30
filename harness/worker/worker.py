"""Durable worker: lease pending work, retry failures, resume after restart.

One worker process, controlled concurrency (1-4 jobs). Each action carries
an idempotency key; a restart continues from the last committed step.
"""
from __future__ import annotations

import logging
import time
import uuid

from configs.settings import settings
from harness.agent import service as svc
from harness.store import repository as R
from harness.store.database import SessionLocal, init_db

log = logging.getLogger("cmr.worker")


def run_once(*, worker_id: str | None = None) -> dict | None:
    init_db()
    worker_id = worker_id or f"worker-{uuid.uuid4().hex[:6]}"
    db = SessionLocal()
    try:
        task = R.lease_pending_task(db, worker_id=worker_id,
                                    timeout_s=settings.WORKER_JOB_TIMEOUT_S)
        if task is None:
            return None
        log.info("leased task %s (%s) attempt %s", task.id, task.task_type, task.attempts)
        try:
            result = svc.execute_task(db, task, worker_id=worker_id)
            return result
        except Exception as exc:  # bounded retry -> dead-letter
            log.exception("task %s failed: %s", task.id, exc)
            if (task.attempts or 0) >= (task.max_attempts or 3):
                R.set_task_status(db, task, "dead_letter", error_ref=str(exc)[:500])
                return {"task_id": task.id, "status": "dead_letter"}
            R.set_task_status(db, task, "queued", error_ref=str(exc)[:500])
            return {"task_id": task.id, "status": "requeued"}
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log.info("CMR worker starting (poll %.1fs)", settings.WORKER_POLL_INTERVAL_S)
    while True:
        try:
            result = run_once()
            if result is None:
                time.sleep(settings.WORKER_POLL_INTERVAL_S)
        except KeyboardInterrupt:
            log.info("worker shutdown requested")
            break
        except Exception:
            log.exception("worker loop error")
            time.sleep(settings.WORKER_POLL_INTERVAL_S)


if __name__ == "__main__":
    from configs.settings import assert_pilot_secrets

    assert_pilot_secrets()
    main()
