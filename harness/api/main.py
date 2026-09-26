"""FastAPI web process (spec 03/07): accept requests, return answers, expose status.

One codebase, two process types: `harness.api.main` (web) and
`harness.worker.worker` (worker). PostgreSQL is the system of record;
SQLite is the local fallback. See configs.settings.DATABASE_URL.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
import uvicorn

from configs.settings import settings
from harness.api import auth as auth_mod
from harness.agent import guard as guard_mod
from harness.agent import service as svc
from harness.api import schemas as S
from harness.store import models as M
from harness.store import repository as R
from harness.store.database import SessionLocal, init_db

log = logging.getLogger("cmr.web")
WORKER_HEARTBEAT: dict[str, Any] = {"last_seen": None}

app = FastAPI(title="CMR Specialist Agent API", version="2.0.0",
              description="Lean case-centered automation agent (spec v2.0).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Authorization"])

from harness.api.admin import router as admin_router  # noqa: E402

app.include_router(admin_router)

ADMIN_DIR = Path(__file__).resolve().parent.parent.parent / "admin"

FRONTEND_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "index.html"


# ── middleware: request IDs + PII-masked structured logs ─────────────────────

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = rid
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request failed", extra={"request_id": rid, "path": request.url.path})
        raise
    response.headers["X-Request-ID"] = rid
    log.info("%s %s -> %s (%.0fms)", request.method, request.url.path,
             getattr(response, "status_code", "?"),
             (time.perf_counter() - started) * 1000,
             extra={"request_id": rid} if False else None)
    return response


def verify_api_key(provided: Optional[str]) -> None:
    if settings.HARNESS_API_KEY and provided:
        if not hmac.compare_digest(provided, settings.HARNESS_API_KEY):
            raise HTTPException(status_code=401, detail="Invalid API Key")


def get_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _task_payload(task: M.Task) -> dict[str, Any]:
    plan = json.loads(task.plan_json) if task.plan_json else None
    proposed_by = (plan or {}).get("proposed_by", "none")
    return {
        "id": task.id, "case_id": task.case_id, "task_type": task.task_type,
        "instructions": task.instructions, "status": task.status,
        "approval_required": task.approval_required,
        "idempotency_key": task.idempotency_key,
        "plan": plan,
        "plan_proposed_by": proposed_by,
        "plan_fallback": proposed_by != "model",
        "result": json.loads(task.result_json) if task.result_json else None,
        "error_ref": task.error_ref,
        "waiting_reason": json.loads(task.waiting_reason) if task.waiting_reason else None,
        "attempts": task.attempts, "max_attempts": task.max_attempts,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# ── shed locks: login system ───────────────────────────────────────────────

@app.post("/auth/users", tags=["Auth"])
def register_user(req: S.CreateUserRequest,
                  authorization: Optional[str] = Header(default=None),
                  x_api_key: Optional[str] = Header(default=None),
                  db: Session = Depends(get_db)):
    """Create a staff login. Open only for the FIRST user (bootstrap);
    afterwards the caller must already be authenticated."""
    if db.scalar(select(M.User)) is None:
        pass  # bootstrap: no users yet, allow creation
    else:
        actor = auth_mod.resolve_actor(db, authorization=authorization, x_api_key=x_api_key)
        if actor is None:
            raise HTTPException(status_code=401, detail="login required")
        if req.is_admin and actor != "api-key":
            caller = db.scalar(select(M.User).where(M.User.username == actor))
            if not caller or not getattr(caller, "is_admin", 0):
                raise HTTPException(status_code=403, detail="admin required to grant admin")
    try:
        user = auth_mod.create_user(db, username=req.username, password=req.password,
                                    display_name=req.display_name,
                                    make_admin=req.is_admin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"id": user.id, "username": user.username, "display_name": user.display_name,
            "is_admin": bool(getattr(user, "is_admin", 0))}


@app.post("/auth/login", tags=["Auth"])
def login(req: S.LoginRequest, db: Session = Depends(get_db)):
    user = auth_mod.authenticate(db, username=req.username, password=req.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid username or password")
    sess = auth_mod.issue_session(db, user)
    return {"token": sess.token, "username": user.username,
            "display_name": user.display_name,
            "expires_at": sess.expires_at.isoformat()}


@app.post("/auth/logout", tags=["Auth"])
def logout(authorization: Optional[str] = Header(default=None),
           db: Session = Depends(get_db)):
    if authorization and authorization.lower().startswith("bearer "):
        auth_mod.revoke_session(db, authorization[7:].strip())
    return {"ok": True}


@app.get("/auth/me", tags=["Auth"])
def me(authorization: Optional[str] = Header(default=None),
       x_api_key: Optional[str] = Header(default=None),
       db: Session = Depends(get_db)):
    actor = auth_mod.resolve_actor(db, authorization=authorization, x_api_key=x_api_key)
    if not actor:
        raise HTTPException(status_code=401, detail="login required")
    is_admin = False
    if actor != "api-key":
        u = db.scalar(select(M.User).where(M.User.username == actor))
        is_admin = bool(u and getattr(u, "is_admin", 0))
    return {"actor": actor, "is_admin": is_admin}


# ── root / health ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def root():
    if FRONTEND_PATH.exists():
        return FileResponse(FRONTEND_PATH)
    return HTMLResponse("<h2>CMR Specialist Agent API v2.0</h2><p>Visit <a href='/docs'>/docs</a>.</p>")


@app.get("/admin", response_class=HTMLResponse, tags=["Admin"])
def admin_index():
    idx = ADMIN_DIR / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return HTMLResponse("<h2>Admin site not installed</h2>")


@app.get("/admin/{page}", tags=["Admin"])
def admin_page(page: str):
    allowed = {"index.html", "mockdb.html", "harness.html", "worker.html", "knowledge.html",
               "shared.js", "shared.css"}
    if page not in allowed:
        raise HTTPException(status_code=404, detail="no such admin page")
    return FileResponse(ADMIN_DIR / page)


@app.get("/health", tags=["Health"])
def health(db: Session = Depends(get_db)):
    try:
        db.scalar(select(func.count()).select_from(M.Case))
        db_ok = "connected"
    except Exception as exc:
        db_ok = f"error: {exc}"
    oldest = db.scalar(select(func.min(M.Task.created_at)).where(M.Task.status == "queued"))
    age = int((datetime.now(timezone.utc) - oldest).total_seconds()) if oldest else None
    if oldest is not None and getattr(oldest, "tzinfo", None) is None:
        age = int((datetime.now(timezone.utc) - oldest.replace(tzinfo=timezone.utc)).total_seconds())
    return {"status": "ok" if db_ok == "connected" else "degraded",
            "version": settings.APP_VERSION, "database": db_ok,
            "oldest_queued_job_age_s": age,
            "worker_heartbeat": WORKER_HEARTBEAT.get("last_seen") or "unknown"}


@app.post("/worker/heartbeat", tags=["Health"])
def heartbeat(payload: dict[str, Any]):
    WORKER_HEARTBEAT["last_seen"] = datetime.now(timezone.utc).isoformat()
    return {"ok": True}


# ── spec interfaces ──────────────────────────────────────────────────────────

@app.post("/cases", tags=["Cases"])
def create_case(req: S.CreateCaseRequest, x_api_key: Optional[str] = Header(default=None),
                db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    g = guard_mod.check_text(req.text)
    if not g.allowed:
        raise HTTPException(status_code=400, detail=g.reason)
    case = R.create_case_shell(db, title=req.title or (req.text[:80] if req.text else None),
                               source_channel=req.source_channel, owner=req.owner,
                               external_reference=req.external_reference)
    try:
        outcome = svc.process_new_input(db, case_id=case.id, raw_text=req.text, sender=req.sender)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    inp_id = outcome.get("input_id")
    return {"case_id": case.id, "input_id": inp_id, **outcome}


@app.post("/cases/{case_id}/messages", tags=["Cases"])
def add_message(case_id: str, req: S.AddMessageRequest,
                x_api_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    if not db.get(M.Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    try:
        outcome = svc.process_new_input(db, case_id=case_id, raw_text=req.text, sender=req.sender)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"case_id": case_id, **outcome}


@app.post("/cases/{case_id}/tasks", tags=["Tasks"])
def create_task(case_id: str, req: S.CreateTaskRequest,
                x_api_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    if not db.get(M.Case, case_id):
        raise HTTPException(status_code=404, detail="case not found")
    task = svc.queue_task(db, case_id=case_id, task_type=req.task_type,
                          instructions=req.instructions, approval_required=req.approval_required,
                          idempotency_key=req.idempotency_key)
    return _task_payload(task)


@app.get("/cases/{case_id}", tags=["Cases"])
def get_case(case_id: str, x_api_key: Optional[str] = Header(default=None),
             db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    state = R.get_case_state(db, case_id)
    if not state:
        raise HTTPException(status_code=404, detail="case not found")
    # attach outputs
    tasks = db.scalars(select(M.Task).where(M.Task.case_id == case_id)).all()
    state["outputs"] = [{"task_id": t.id, "status": t.status,
                         "result": json.loads(t.result_json) if t.result_json else None,
                         "error_ref": t.error_ref} for t in tasks]
    return state


@app.get("/tasks/{task_id}", tags=["Tasks"])
def get_task(task_id: str, x_api_key: Optional[str] = Header(default=None),
             db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    task = db.get(M.Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    payload = _task_payload(task)
    steps = db.scalars(select(M.RunStep).where(M.RunStep.task_id == task_id)
                       .order_by(M.RunStep.sequence.asc())).all()
    payload["steps"] = [{"sequence": s.sequence, "action": s.action, "tool": s.tool,
                         "status": s.status, "retry_count": s.retry_count,
                         "result": json.loads(s.result_json) if s.result_json else None} for s in steps]
    approvals = db.scalars(select(M.Approval).where(M.Approval.task_id == task_id)
                           .order_by(M.Approval.created_at.desc())).all()
    payload["approvals"] = [{"id": a.id, "requested_action": a.requested_action,
                             "decision": a.decision, "approver": a.approver,
                             "reason": a.reason} for a in approvals]
    return payload


@app.post("/tasks/{task_id}/approvals", tags=["Tasks"])
def decide_approval(task_id: str, req: S.ApprovalRequest,
                    x_api_key: Optional[str] = Header(default=None),
                    authorization: Optional[str] = Header(default=None),
                    db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    actor = auth_mod.resolve_actor(db, authorization=authorization, x_api_key=x_api_key)
    task = db.get(M.Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    ap = db.scalar(select(M.Approval).where(M.Approval.task_id == task_id,
                                            M.Approval.decision == "pending")
                   .order_by(M.Approval.created_at.desc()))
    if not ap:
        # create one so the decision is auditable even if worker didn't request
        ap = R.request_approval(db, task_id=task_id, requested_action="manual approval",
                                requester="api")
    ap.decision = req.decision
    ap.approver = actor or req.approver
    ap.reason = req.reason
    ap.decided_at = datetime.now(timezone.utc)
    if req.decision == "approved":
        R.set_task_status(db, task, "queued", waiting_reason=None)
    else:
        R.set_task_status(db, task, "failed", error_ref=f"rejected: {req.reason or 'no reason'}")
    db.commit()
    return {"approval_id": ap.id, "task_id": task_id, "decision": ap.decision,
            "task_status": task.status}


# ── knowledge ────────────────────────────────────────────────────────────────

def _chunk_text(text: str, size: int = 260, overlap: int = 45) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    out = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + size]).strip()
        if chunk:
            out.append(chunk)
        if start + size >= len(words):
            break
    return out


@app.post("/knowledge/documents", tags=["Knowledge"])
async def upload_document(file: UploadFile = File(...),
                          title: str | None = None,
                          x_api_key: Optional[str] = Header(default=None),
                          db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    data = await file.read()
    g = guard_mod.check_attachment(file.filename or "doc.txt", len(data))
    if not g.allowed:
        raise HTTPException(status_code=400, detail=g.reason)
    text = ""
    name = (file.filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(data))
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                t = (page.extract_text() or "").strip()
                if t:
                    pages.append((i, t))
            text = "\n\n".join(f"[page {i}]\n{t}" for i, t in pages)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF parse failed: {exc}")
    else:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            raise HTTPException(status_code=400, detail="unreadable text file")
    if not text.strip():
        raise HTTPException(status_code=400, detail="no extractable text")
    doc = M.KnowledgeDocument(title=title or file.filename, source_filename=file.filename,
                              content_type=file.content_type, size_bytes=len(data),
                              sha256=hashlib.sha256(data).hexdigest())
    db.add(doc)
    db.flush()
    existing = db.scalar(select(func.max(M.KnowledgeVersion.version_no))
                         .where(M.KnowledgeVersion.document_id == doc.id)) or 0
    ver = M.KnowledgeVersion(document_id=doc.id, version_no=(existing + 1), status="ready")
    db.add(ver)
    db.flush()
    chunks = _chunk_text(text)
    for i, ch in enumerate(chunks):
        db.add(M.KnowledgeChunk(version_id=ver.id, document_id=doc.id, ordinal=i,
                                text=ch, locator=f"chunk {i + 1}/{len(chunks)}"))
    ver.chunk_count = len(chunks)
    db.commit()
    return {"document_id": doc.id, "version_id": ver.id, "chunks": len(chunks), "status": ver.status}


@app.post("/knowledge/versions/{version_id}/publish", tags=["Knowledge"])
def publish_version(version_id: str, x_api_key: Optional[str] = Header(default=None),
                    db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    ver = db.get(M.KnowledgeVersion, version_id)
    if not ver:
        raise HTTPException(status_code=404, detail="version not found")
    if ver.status != "ready" and ver.status != "active":
        raise HTTPException(status_code=400, detail=f"version is {ver.status}")
    # one active version per document: archive siblings
    siblings = db.scalars(select(M.KnowledgeVersion).where(
        M.KnowledgeVersion.document_id == ver.document_id,
        M.KnowledgeVersion.id != ver.id, M.KnowledgeVersion.status == "active")).all()
    for s in siblings:
        s.status = "archived"
    ver.status = "active"
    db.commit()
    return {"version_id": ver.id, "status": "active"}


@app.get("/knowledge/documents", tags=["Knowledge"])
def list_documents(x_api_key: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    docs = db.scalars(select(M.KnowledgeDocument).order_by(M.KnowledgeDocument.created_at.desc()).limit(100)).all()
    out = []
    for d in docs:
        vers = db.scalars(select(M.KnowledgeVersion).where(
            M.KnowledgeVersion.document_id == d.id).order_by(M.KnowledgeVersion.version_no.desc())).all()
        out.append({"document_id": d.id, "title": d.title, "source_filename": d.source_filename,
                    "versions": [{"version_id": v.id, "version_no": v.version_no,
                                  "status": v.status, "chunks": v.chunk_count} for v in vers]})
    return {"documents": out}


# ── legacy /v1 adapter (prototype compat) ────────────────────────────────────

@app.get("/v1/health", response_model=S.HealthResponse, tags=["Legacy"])
def legacy_health():
    return S.HealthResponse(status="healthy", version=settings.APP_VERSION,
                            embedding_model=getattr(settings, "EMBEDDING_MODEL_NAME", "none"),
                            inference_provider=settings.INFERENCE_PROVIDER)


@app.get("/v1/status", response_model=S.StatusResponse, tags=["Legacy"])
def legacy_status():
    return S.StatusResponse(status="ok", data_directory=str(settings.DATA_DIR),
                            sqlite_db=str(settings.SQLITE_DB_PATH))


def _legacy_answer(question: str, top_k: int, db: Session) -> dict:
    case = R.create_case_shell(db, title=question[:80], source_channel="legacy-chat")
    outcome = svc.process_new_input(db, case_id=case.id, raw_text=question, sender="legacy")
    hits = outcome.get("citations", [])
    return {
        "conversation_id": case.id, "answer": outcome.get("answer", ""),
        "intent_type": outcome.get("intent"), "confidence": outcome.get("intent_confidence", 0.0),
        "state": R.get_case_state(db, case.id).get("fields", {}),
        "sources": [{"collection": "knowledge", "id": h.get("chunk_id", ""),
                     "source": h.get("document_id"), "page": h.get("page"),
                     "score": h.get("score", 0.0)} for h in hits],
    }


@app.post("/v1/chat", response_model=S.ChatResponse, tags=["Legacy"])
def legacy_chat(req: S.ChatRequest, x_api_key: Optional[str] = Header(default=None),
                db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    import time as _t
    t0 = _t.perf_counter()
    try:
        if req.conversation_id and db.get(M.Case, req.conversation_id):
            outcome = svc.process_new_input(db, case_id=req.conversation_id,
                                            raw_text=req.question, sender="legacy")
            cid = req.conversation_id
        else:
            r = _legacy_answer(req.question, req.top_k, db)
            cid = r["conversation_id"]
            return S.ChatResponse(conversation_id=cid, answer=r["answer"],
                                  intent_type=r["intent_type"], confidence=r["confidence"],
                                  state=r["state"], sources=r["sources"],
                                  latency_seconds=round(_t.perf_counter() - t0, 3),
                                  generation_seconds=0.0)
        state = R.get_case_state(db, cid).get("fields", {})
        return S.ChatResponse(conversation_id=cid, answer=outcome.get("answer", ""),
                              intent_type=outcome.get("intent"), confidence=outcome.get("intent_confidence"),
                              state=state, sources=[], latency_seconds=round(_t.perf_counter() - t0, 3),
                              generation_seconds=0.0)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat orchestration failed: {exc}") from exc


@app.post("/v1/query", response_model=S.QueryResponse, tags=["Legacy"])
def legacy_query(req: S.QueryRequest, x_api_key: Optional[str] = Header(default=None),
                 db: Session = Depends(get_db)):
    verify_api_key(x_api_key)
    import time as _t
    t0 = _t.perf_counter()
    try:
        r = _legacy_answer(req.question, req.top_k, db)
        return S.QueryResponse(answer=r["answer"], intent_type=r["intent_type"],
                               confidence=r["confidence"], state=r["state"], sources=r["sources"],
                               latency_seconds=round(_t.perf_counter() - t0, 3), generation_seconds=0.0)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query orchestration failed: {exc}") from exc


if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
