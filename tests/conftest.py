"""Suite isolation: the engine singleton shares one test DB per process,
so every test starts from empty tables. Without this, deterministic
idempotency keys collide across files and tests pass alone but fail together.
"""
import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _clean_db():
    from harness.store.database import SessionLocal, init_db
    from harness.store import models as M  # noqa: F401  (register tables)

    init_db()
    db = SessionLocal()
    try:
        for table in ("tool_audit", "citations", "user_sessions", "users",
                      "approvals", "run_steps", "agent_runs", "case_events",
                      "extracted_fields", "case_inputs", "tasks",
                      "knowledge_chunks", "knowledge_versions",
                      "knowledge_documents", "cases"):
            db.execute(text(f"DELETE FROM {table}"))
        db.commit()
    finally:
        db.close()
    yield
