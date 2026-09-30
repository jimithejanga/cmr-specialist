"""Planner: bounded steps referencing ONLY registered tools + explicit case fields."""
from __future__ import annotations

import hashlib

from configs.settings import settings
from harness.agent.schemas import Plan, PlanStep

KNOWLEDGE_FLOW = ["knowledge_lookup", "draft_answer"]
TASK_FLOWS: dict[str, list[str]] = {
    "payment_reconciliation": ["validate_fields", "knowledge_lookup", "payment_status_check", "draft_solution"],
    "change_of_ownership": ["validate_fields", "knowledge_lookup", "draft_solution"],
    "general_support": ["knowledge_lookup", "draft_solution"],
}


def build_plan(task_type: str, task_id: str, fields: dict, needs_approval: bool = False) -> Plan:
    tools = TASK_FLOWS.get(task_type, TASK_FLOWS["general_support"])
    if len(tools) > settings.MAX_PLAN_STEPS:
        tools = tools[: settings.MAX_PLAN_STEPS]
    steps = []
    for i, tool in enumerate(tools):
        key = hashlib.sha256(f"{task_id}|{i}|{tool}".encode()).hexdigest()[:12]
        steps.append(PlanStep(
            sequence=i, action=f"{tool} (step {i + 1}/{len(tools)})", tool=tool,
            optional=(tool == "knowledge_lookup"),
            arguments={"task_type": task_type, "fields": fields},
            requires_approval=bool(needs_approval and tool in {"payment_status_check"}),
            idempotency_key=f"{task_id}-s{i}-{key}",
        ))
    return Plan(task_type=task_type, steps=steps)


def propose_plan(task_type: str, task_id: str, fields: dict,
                 needs_approval: bool = False) -> Plan:
    """Model proposes the step order; harness enforces allowlist + budget.

    The model may only order/subset the candidate tools for this task type —
    never invent tools. Unknown names are dropped; an empty or silent proposal
    falls back to the template plan. WRITE-bearing steps always require
    approval regardless of what the model says.
    """
    candidates = TASK_FLOWS.get(task_type, TASK_FLOWS["general_support"])
    from harness.tools import formulations as F
    write_tools = {fid for fid, form in F.CATALOG.items() if form.verb == "WRITE"}

    ordered: list[str] | None = None
    try:
        from harness.agent import llm as LLM
        proposal = LLM.propose_json(
            system=("You order an execution plan. Reply ONLY JSON: "
                    "{\"tools\": [\"tool\", ...]} using only names from the allowed list. "
                    "Put verification steps before writes. Omit unneeded steps."),
            user_text=(f"task_type={task_type} fields={sorted(fields)} "
                       f"allowed={candidates}"),
            max_new_tokens=300,
        ) or {}
        names = proposal.get("tools")
        if isinstance(names, list):
            ordered = [t for t in names if t in candidates]
    except Exception as exc:
        print(f"[planner] proposal failed, using template: {exc}", flush=True)
        ordered = None
    if not ordered:
        plan = build_plan(task_type, task_id, fields, needs_approval)
        plan.proposed_by = "template"
        return plan

    tools = ordered[: settings.MAX_PLAN_STEPS]
    steps = []
    for i, tool in enumerate(tools):
        key = hashlib.sha256(f"{task_id}|{i}|{tool}".encode()).hexdigest()[:12]
        steps.append(PlanStep(
            sequence=i, action=f"{tool} (step {i + 1}/{len(tools)})", tool=tool,
            optional=(tool == "knowledge_lookup"),
            arguments={"task_type": task_type, "fields": fields},
            requires_approval=bool(
                (needs_approval and tool in {"payment_status_check"})
                or tool in write_tools),
            idempotency_key=f"{task_id}-s{i}-{key}",
        ))
    plan = Plan(task_type=task_type, steps=steps, proposed_by="model")
    return plan


def build_knowledge_plan(query_id: str) -> Plan:
    steps = []
    for i, tool in enumerate(KNOWLEDGE_FLOW):
        key = hashlib.sha256(f"{query_id}|{i}|{tool}".encode()).hexdigest()[:12]
        steps.append(PlanStep(sequence=i, action=f"{tool}", tool=tool,
                               optional=(tool == "knowledge_lookup"),
                              arguments={}, requires_approval=False,
                              idempotency_key=f"{query_id}-k{i}-{key}"))
    return Plan(task_type="knowledge_query", steps=steps)


def build_family_plan(family: str, task_id: str, fields: dict) -> Plan:
    """Plan steps naming CHECK/WRITE formulations (PDF v3 §8)."""
    from harness.tools import formulations as F

    tools = F.FAMILY_PLANS.get(family, [])
    if len(tools) > settings.MAX_PLAN_STEPS:
        tools = tools[: settings.MAX_PLAN_STEPS]
    steps = []
    for i, tool in enumerate(tools):
        key = hashlib.sha256(f"{task_id}|{i}|{tool}".encode()).hexdigest()[:12]
        form = F.CATALOG[tool]
        steps.append(PlanStep(
            sequence=i, action=f"{tool} (step {i + 1}/{len(tools)})", tool=tool,
            optional=(tool == "knowledge_lookup"),
            arguments={"fields": fields},
            requires_approval=form.verb == "WRITE",
            idempotency_key=f"{task_id}-s{i}-{key}",
        ))
    return Plan(task_type=family, steps=steps)
