"""Policy gate: role, approval class, sensitivity, step count, timeout, allowed tool.

Phase-2 rule: approval mirrors the exact act. plan_hash binds an approval to
the precise plan (tool order + arguments) it was requested for; a changed
plan needs a fresh approval, and only a matching approval unlocks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from configs.settings import settings
from harness.agent.schemas import Plan
from harness.tools import formulations as F
from harness.tools.registry import REGISTRY

SENSITIVE_TOOLS = {"payment_status_check"}


@dataclass
class PolicyDecision:
    allowed: bool
    needs_approval: bool = False
    reason: str = ""


def check(plan: Plan, *, approval_required: str = "never") -> PolicyDecision:
    if len(plan.steps) > settings.MAX_PLAN_STEPS:
        return PolicyDecision(allowed=False, reason=f"plan exceeds {settings.MAX_PLAN_STEPS} steps")
    for s in plan.steps:
        # Rule 1 — CHECK formulations pass freely (allowlisted + schema-valid).
        if s.tool in F.CATALOG and F.CATALOG[s.tool].verb == "CHECK":
            continue
        # Rule 2 — WRITE formulations need approval + key + evidence (enforced
        # again inside the module at fire time; the gate pauses the task here).
        if s.tool in F.CATALOG and F.CATALOG[s.tool].verb == "WRITE":
            return PolicyDecision(allowed=True, needs_approval=True,
                                  reason=f"write formulation {s.tool} requires approval")
        if s.tool not in REGISTRY:
            return PolicyDecision(allowed=False, reason=f"tool not allowlisted: {s.tool}")
        spec = REGISTRY[s.tool]
        if spec.permission == "sensitive" or s.tool in SENSITIVE_TOOLS:
            if approval_required == "always":
                return PolicyDecision(allowed=True, needs_approval=True,
                                      reason=f"tool {s.tool} requires approval")
            if approval_required == "sensitive":
                return PolicyDecision(allowed=True, needs_approval=True,
                                      reason=f"sensitive tool {s.tool} requires approval")
    if any(s.requires_approval for s in plan.steps):
        return PolicyDecision(allowed=True, needs_approval=True, reason="planner flagged approval")
    return PolicyDecision(allowed=True, reason="policy passed")


def plan_hash(plan: Plan) -> str:
    """Canonical fingerprint of the exact act: tool order + full arguments.

    Idempotency keys are included (they bind task + order); volatile
    nothing is excluded. Any replan - reorder, re-argument, re-target -
    yields a different hash and voids prior approvals.
    """
    canon = [{"tool": s.tool, "arguments": s.arguments,
              "requires_approval": s.requires_approval,
              "idempotency_key": s.idempotency_key} for s in plan.steps]
    return hashlib.sha256(json.dumps(canon, sort_keys=True, default=str).encode()).hexdigest()[:16]
