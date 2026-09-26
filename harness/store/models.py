"""Durable case memory + execution records (spec section 04).

Latest usable state + full history:
Case -> CaseInput -> ExtractedField (versioned) -> Task -> AgentRun -> RunStep
Knowledge: Document -> Version -> Chunk; Citation explains evidence.
Approval: human control point. CaseEvent: append-only history.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from harness.store.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}" if prefix else uuid.uuid4().hex


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    source_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class CaseInput(Base):
    """Preserves exactly what entered the system (message / follow-up)."""

    __tablename__ = "case_inputs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    sender: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attachment_refs: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExtractedField(Base):
    """Versioned — corrections create a NEW row with version+1, never overwrite."""

    __tablename__ = "extracted_fields"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), index=True)
    source_input_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    data_type: Mapped[str] = mapped_column(String(32), default="string")
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation: Mapped[str] = mapped_column(String(32), default="pending")  # pending|valid|invalid
    version: Mapped[int] = mapped_column(Integer, default=1)
    accepted_by: Mapped[str | None] = mapped_column(String(64), nullable=True)  # model|human|system
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Task(Base):
    """Durable unit of automation; doubles as the job-queue row (DB-backed queue)."""

    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(128), index=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    # queued|leased|running|waiting_for_input|waiting_approval|failed|completed|dead_letter
    approval_required: Mapped[str] = mapped_column(String(16), default="never")  # never|sensitive|always
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    waiting_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    leased_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("cases.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=True, index=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")  # completed|failed
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RunStep(Base):
    __tablename__ = "run_steps"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("agent_runs.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tasks.id"), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(128))
    tool: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arguments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ok")  # ok|retry|failed|skipped|awaiting_approval
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    title: Mapped[str] = mapped_column(String(256))
    source_filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeVersion(Base):
    __tablename__ = "knowledge_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_documents.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    # processing|ready|active|archived
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    version_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_versions.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locator: Mapped[str | None] = mapped_column(String(256), nullable=True)


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("agent_runs.id"), nullable=True, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_version_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_id: Mapped[str] = mapped_column(String(64), index=True)
    quoted_span: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.id"), index=True)
    requested_action: Mapped[str] = mapped_column(String(256))
    requester: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), default="pending")  # pending|approved|rejected
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseEvent(Base):
    __tablename__ = "case_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    event_type: Mapped[str] = mapped_column(String(64))
    previous_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ToolAudit(Base):
    """Module-owned audit log (PDF v3 §7). Append-only: no update/delete API
    exists by design. Ground truth for what happened to the data."""

    __tablename__ = "tool_audit"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uid)
    formulation_id: Mapped[str] = mapped_column(String(64), index=True)
    verb: Mapped[str] = mapped_column(String(16))  # CHECK | WRITE
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    arguments_masked: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
