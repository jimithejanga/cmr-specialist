"""Spec section 06: minimal application interfaces (Pydantic DTOs)."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class CreateCaseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    title: str | None = Field(default=None, max_length=256)
    sender: str | None = Field(default=None, max_length=128)
    source_channel: str = Field(default="api", max_length=64)
    owner: str | None = Field(default=None, max_length=128)
    external_reference: str | None = Field(default=None, max_length=128)


class AddMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    sender: str | None = Field(default=None, max_length=128)


class CreateTaskRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=128)
    instructions: str | None = Field(default=None, max_length=6000)
    approval_required: Literal["never", "sensitive", "always"] = "never"
    idempotency_key: str | None = Field(default=None, max_length=128)


class ApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    approver: str | None = Field(default=None, max_length=128)
    reason: str | None = Field(default=None, max_length=1000)


class PublishVersionRequest(BaseModel):
    pass


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    oldest_queued_job_age_s: int | None = None
    worker_heartbeat: str = "unknown"


# Legacy compat (prototype /v1/chat) — retained as a thin adapter.
class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    conversation_id: str | None = Field(default=None, max_length=128)
    top_k: int = Field(default=4, ge=1, le=10)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6000)
    top_k: int = Field(default=4, ge=1, le=10)


class SourceHit(BaseModel):
    collection: str = "knowledge"
    id: str = ""
    source: str | None = None
    page: int | None = None
    score: float = 0.0


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    intent_type: str | None = None
    confidence: float | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceHit] = Field(default_factory=list)
    latency_seconds: float = 0.0
    generation_seconds: float = 0.0


class QueryResponse(BaseModel):
    answer: str
    intent_type: str | None = None
    confidence: float | None = None
    state: dict[str, Any] = Field(default_factory=dict)
    sources: list[SourceHit] = Field(default_factory=list)
    latency_seconds: float = 0.0
    generation_seconds: float = 0.0


class StatusResponse(BaseModel):
    status: str
    data_directory: str
    sqlite_db: str
