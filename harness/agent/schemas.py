"""Typed schemas: the harness controls the model (spec section 06).

The LLM may PROPOSE; Pydantic + policy code ENFORCE.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class Intent(str, Enum):
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"
    AUTOMATION_TASK = "AUTOMATION_TASK"
    CASE_UPDATE = "CASE_UPDATE"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class ExtractedValue(BaseModel):
    name: str
    data_type: Literal["string", "number", "date", "boolean"] = "string"
    raw_value: str | None = None
    normalized_value: Any = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    validation: Literal["pending", "valid", "invalid"] = "pending"


class PlanStep(BaseModel):
    sequence: int = Field(ge=0)
    action: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    # Phase-2 rule: every step is required unless explicitly optional.
    # A failed required step fails the task; optional steps degrade.
    optional: bool = False
    idempotency_key: str


class Plan(BaseModel):
    task_type: str
    steps: list[PlanStep] = Field(max_length=12)
    proposed_by: str = "template"  # template | model

    def tool_names(self) -> list[str]:
        return [s.tool for s in self.steps]


class CitationHit(BaseModel):
    version_id: str
    chunk_id: str
    document_id: str = ""
    text: str
    page: int | None = None
    locator: str | None = None
    score: float


class GroundedAnswer(BaseModel):
    answer: str
    citations: list[CitationHit] = Field(default_factory=list)
    fallback: bool = False
