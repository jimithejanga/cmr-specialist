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
# Phase-4 routing: task type -> formulation family executed end to end.
FAMILY_ROUTE: dict[str, str] = {
    "payment_reconciliation": "payment_issue",
    "change_of_ownership": "change_of_ownership",
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
    # Phase-4 routing: these families execute through CHECK/WRITE plans so
    # user journeys exercise the same sealed boundary a real connector uses.
    family = FAMILY_ROUTE.get(task_type)
    if family:
        candidates = F.viable_family_plan(family, fields)
        is_family = True
    else:
        is_family = False
    if is_family and not candidates:
        # Nothing resolvable: fall back to the internal-tool template so the
        # task still validates, waits, and explains instead of empty-planning.
        plan = build_plan(task_type, task_id, fields, needs_approval)
        plan.proposed_by = "template"
        return plan

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
        if is_family:
            plan = build_family_plan(family, task_id, fields)
        else:
            plan = build_plan(task_type, task_id, fields, needs_approval)
        plan.proposed_by = "template"
        return plan

    tools = ordered[: settings.MAX_PLAN_STEPS]
    steps = []
    for i, tool in enumerate(tools):
        key = hashlib.sha256(f"{task_id}|{i}|{tool}".encode()).hexdigest()[:12]
        if is_family:
            form = F.CATALOG[tool]
            steps.append(PlanStep(
                sequence=i, action=f"{tool} (step {i + 1}/{len(tools)})", tool=tool,
                optional=False,
                arguments={"fields": fields},
                requires_approval=(form.verb == "WRITE"),
                idempotency_key=f"{task_id}-s{i}-{key}",
            ))
            continue
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
    """Plan steps naming CHECK/WRITE formulations (PDF v3 §8), viability-pruned."""
    from harness.tools import formulations as F

    tools = F.viable_family_plan(family, fields)
    if len(tools) > settings.MAX_PLAN_STEPS:
        tools = tools[: settings.MAX_PLAN_STEPS]
    steps = []
    for i, tool in enumerate(tools):
        key = hashlib.sha256(f"{task_id}|{i}|{tool}".encode()).hexdigest()[:12]
        form = F.CATALOG[tool]
        steps.append(PlanStep(
            sequence=i, action=f"{tool} (step {i + 1}/{len(tools)})", tool=tool,
            optional=False,
            arguments={"fields": fields},
            requires_approval=form.verb == "WRITE",
            idempotency_key=f"{task_id}-s{i}-{key}",
        ))
    return Plan(task_type=family, steps=steps)
