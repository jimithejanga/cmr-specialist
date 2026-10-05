"""Agent service: the two primary workflows (spec 05).

Knowledge question: store input -> classify -> retrieve active chunks ->
generate -> validate citations -> store + answer.
Automation task: store task -> extract fields -> missing? -> plan+approve ->
worker executes -> validate + close.
Follow-up: attach input, re-extract, propose revisions, resume waiting tasks.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.agent import extractor as E
from harness.agent import guard, intent as intent_mod
from harness.agent import planner as planner_mod
from harness.agent import policy as policy_mod
from harness.agent import retriever as retriever_mod
from harness.agent import validator as validator_mod
from harness.agent.schemas import Intent
from harness.store import models as M
from harness.store import repository as R
from harness.tools import registry as tools

FALLBACK_NO_EVIDENCE = ("I couldn't find supporting evidence in the published knowledge base "
                        "for this question. Please rephrase or provide more detail (e.g. plate "
                        "number, receipt reference), and a specialist will follow up.")

PROMPT_VERSION = "v2-lean"


def _json_safe(o: Any) -> Any:
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "__dict__"):
        return str(o)
    return str(o)


def _formulation_args(fields: dict, results: dict, task) -> dict:
    """Map case fields + prior step data → formulation arguments.

    Missing inputs are left absent so the module's schema validation fails
    loudly with a field-level reason (recorded on the step, never a crash).
    """
    f = fields or {}
    args: dict[str, Any] = {
        "rrr": f.get("remita_rrr") or f.get("rrr"),
        "plate": f.get("plate_number") or f.get("plate"),
        "chassis": f.get("chassis_number") or f.get("chassis"),
        "nin": f.get("nin"),
        "phone": f.get("phone"),
        "email": f.get("email"),
        "account": f.get("account_identifier") or f.get("account"),
        "tin": f.get("tin"),
    }
    # chain prior formulation outputs (vehicle_id, profile_id, doc refs)
    for prev in results.values():
        data = (prev or {}).get("data") or {}
        for k in ("vehicle_id", "profile_id", "buyer_profile_id", "doc_ref",
                  "request_ref", "state", "reason", "field", "old_value",
                  "new_value", "request_age_days", "medium"):
            if data.get(k) and not args.get(k):
                args[k] = data[k]
    # Phase-4: the searched buyer IS the transfer buyer.
    if not args.get("buyer_profile_id") and args.get("profile_id"):
        args["buyer_profile_id"] = args["profile_id"]
    if task is not None and getattr(task, "instructions", None) and not args.get("reason"):
        args["reason"] = (task.instructions or "")[:300]
    # Phase-4: transfers need a document reference; default to the case/task
    # so the step is explicit and audited rather than missing. Still overridable.
    if task is not None and not args.get("doc_ref"):
        args["doc_ref"] = f"case:{task.case_id}/task:{task.id}"
    return {k: v for k, v in args.items() if v is not None}


def _compose_answer(query: str, hits) -> str:
    if not hits:
        return FALLBACK_NO_EVIDENCE
    spans = "\n".join(f"- {h.text[:280]}" for h in hits[:3])
    return (f"Based on the published CMR procedures:\n{spans}\n\n"
            f"Question: {query[:300]}")


_DRAFT_PROMPT = (
    "You answer citizen questions for the Nigeria Police CMR support desk using ONLY the "
    "procedure excerpts below. Write a short plain-language answer (max 150 words), then "
    "stop. Never invent steps, fees, timelines, or outcomes not stated in the excerpts. "
    "Never claim any payment, account, or certificate changed."
)


def _draft_answer(query: str, hits) -> str:
    """Model drafts from cited spans; deterministic composition is the fallback."""
    from harness.agent import llm as llm_mod

    spans = "\n".join(f"[Excerpt {i + 1}] {h.text[:600]}" for i, h in enumerate(hits[:3]))
    draft = llm_mod.propose_text(
        _DRAFT_PROMPT,
        f"Question: {query[:500]}\n\nProcedure excerpts:\n{spans}",
        max_new_tokens=800)
    return draft.strip() if draft and draft.strip() else _compose_answer(query, hits)


def answer_knowledge(db: Session, *, case_id: str, input_id: str, query: str) -> dict[str, Any]:
    started = time.perf_counter()
    classification = intent_mod.classify(query)
    run = R.create_run(db, case_id=case_id, task_id=None, intent=classification.intent.value,
                       prompt_version=PROMPT_VERSION)
    R.add_step(db, run_id=run.id, task_id=None, sequence=0, action="classify",
               arguments={"query": query[:500]}, result={"intent": classification.intent.value})
    hits = retriever_mod.retrieve(db, query)
    R.add_step(db, run_id=run.id, task_id=None, sequence=1, action="knowledge_lookup",
               tool="knowledge_lookup", arguments={"query": query[:500]},
               result={"matches": len(hits)})
    tool_res = tools.run_tool("knowledge_lookup", {"query": query, "citations": hits})
    answer = _draft_answer(query, hits)
    validation = validator_mod.validate_knowledge_answer(answer, hits)
    if not validation.valid:
        answer = FALLBACK_NO_EVIDENCE
    R.add_citations(db, run_id=run.id, task_id=None,
                    hits=[{"version_id": h.version_id, "chunk_id": h.chunk_id,
                           "text": h.text, "score": h.score} for h in hits])
    R.add_step(db, run_id=run.id, task_id=None, sequence=2, action="draft_answer",
               tool="draft_answer",
               arguments={"citation_count": len(hits)},
               result={"answer": answer[:2000], "fallback": not validation.valid})
    latency_ms = int((time.perf_counter() - started) * 1000)
    run.status = "completed"
    run.latency_ms = latency_ms
    db.commit()
    return {
        "run_id": run.id,
        "intent": classification.intent.value,
        "intent_confidence": classification.confidence,
        "answer": answer,
        "fallback": not validation.valid,
        "citations": [{"version_id": h.version_id, "chunk_id": h.chunk_id,
                       "document_id": h.document_id, "page": h.page,
                       "score": h.score, "span": h.text[:300]} for h in hits],
        "validation": {"valid": validation.valid, "reason": validation.reason},
        "latency_ms": latency_ms,
    }


def queue_task(db: Session, *, case_id: str, task_type: str,
               instructions: str | None = None, approval_required: str = "never",
               idempotency_key: str | None = None) -> M.Task:
    """Create a task with its plan stored immediately.

    The model proposes the step order (harness enforces), so even tasks that
    end up waiting_for_input carry their intended path for operators to see.
    Idempotent on idempotency_key: replays return the existing task untouched.
    """
    existing_key = idempotency_key or R._idem_key(case_id, task_type, instructions)
    existing = db.scalar(select(M.Task).where(M.Task.idempotency_key == existing_key))
    if existing:
        return existing
    task = R.create_task(db, case_id=case_id, task_type=task_type,
                         instructions=instructions, approval_required=approval_required,
                         idempotency_key=idempotency_key)
    state = R.get_case_state(db, case_id) or {}
    fields = {k: (v.get("normalized_value") if isinstance(v, dict) else v)
              for k, v in (state.get("fields") or {}).items()}
    plan = planner_mod.propose_plan(task_type, task.id, fields,
                                    needs_approval=(task.approval_required != "never"))
    task.plan_json = json.dumps({
        "task_type": plan.task_type, "proposed_by": plan.proposed_by,
        "steps": [{"sequence": s.sequence, "action": s.action, "tool": s.tool,
                   "arguments": s.arguments, "requires_approval": s.requires_approval,
                   "optional": s.optional,
                   "idempotency_key": s.idempotency_key} for s in plan.steps]})
    # Phase-4: family plans are preliminary until execution (fields arrive
    # via follow-ups), so their approval is requested at execution on the
    # final plan - requesting now would bind the wrong hash and loop.
    if plan.steps and any(s.requires_approval for s in plan.steps) \
            and task_type not in planner_mod.FAMILY_ROUTE:
        R.request_approval(db, task_id=task.id,
                           requested_action=f"execute {plan.proposed_by}-proposed plan",
                           action_hash=policy_mod.plan_hash(plan))
    db.flush()
    return task


def process_new_input(db: Session, *, case_id: str, raw_text: str,
                      sender: str | None = None) -> dict[str, Any]:
    """Store-first: input is persisted before any model call (spec 05)."""
    g = guard.check_text(raw_text)
    if not g.allowed:
        raise ValueError(g.reason)
    inp = R.add_message(db, case_id=case_id, raw_text=raw_text, sender=sender)
    classification = intent_mod.classify(raw_text)
    run = R.create_run(db, case_id=case_id, task_id=None, intent=classification.intent.value,
                       prompt_version=PROMPT_VERSION)
    extracted = E.extract(raw_text)
    R.store_extracted_fields(
        db, case_id=case_id, source_input_id=inp.id, extraction_run_id=run.id,
        fields=[{"name": e.name, "data_type": e.data_type, "raw_value": e.raw_value,
                 "normalized_value": e.normalized_value, "confidence": e.confidence,
                 "validation": e.validation} for e in extracted],
        accepted_by="model")
    if classification.intent == Intent.KNOWLEDGE_QUERY:
        result = answer_knowledge(db, case_id=case_id, input_id=inp.id, query=raw_text)
        result.update({"input_id": inp.id, "intent": classification.intent.value,
                       "warnings": g.warnings})
        return result
    if classification.intent == Intent.AUTOMATION_TASK:
        task_type = _infer_task_type(raw_text)
        state = R.get_case_state(db, case_id) or {}
        fields = {k: (v.get("normalized_value") if isinstance(v, dict) else v)
                  for k, v in (state.get("fields") or {}).items()}
        ok, missing = E.validate_for_task(task_type, fields)
        task = queue_task(db, case_id=case_id, task_type=task_type, instructions=raw_text)
        _stored = json.loads(task.plan_json) if task.plan_json else {}
        _by = _stored.get("proposed_by", "none")
        _planflag = {"plan_proposed_by": _by, "plan_fallback": _by != "model"}
        if not ok:
            prompts = {m: E.missing_prompt(task_type, m) for m in missing}
            R.set_task_status(db, task, "waiting_for_input",
                              waiting_reason=json.dumps({"missing": missing, "prompts": prompts}))
            return {"input_id": inp.id, "intent": classification.intent.value,
                    "task_id": task.id, "task_type": task_type,
                    "status": "waiting_for_input", "missing": missing, "prompts": prompts,
                    "warnings": g.warnings, **_planflag}
        return {"input_id": inp.id, "intent": classification.intent.value,
                "task_id": task.id, "task_type": task_type, "status": "queued",
                "warnings": g.warnings, **_planflag}
    if classification.intent == Intent.UNSUPPORTED:
        return {"input_id": inp.id, "intent": classification.intent.value,
                "answer": "This request is outside what the CMR Specialist can do. "
                          "It cannot perform sensitive, irreversible or external actions "
                          "outside the tool policy.",
                "fallback": True, "warnings": g.warnings}
    # CASE_UPDATE / NEEDS_CLARIFICATION
    resume = _resume_waiting_tasks(db, case_id)
    msg = ("Noted and attached to the case." if classification.intent == Intent.CASE_UPDATE
           else "Could you clarify what you need? For example: ask a procedure question, "
                "or describe a task (payment reconciliation, change of ownership).")
    return {"input_id": inp.id, "intent": classification.intent.value, "answer": msg,
            "fallback": classification.intent == Intent.NEEDS_CLARIFICATION,
            "resumed": resume, "warnings": g.warnings}


def _infer_task_type(text: str) -> str:
    lowered = (text or "").lower()
    if any(k in lowered for k in ["rrr", "remita", "payment", "paid", "unpaid", "receipt"]):
        return "payment_reconciliation"
    if "ownership" in lowered or ("buyer" in lowered and "seller" in lowered):
        return "change_of_ownership"
    return "general_support"


def _resume_waiting_tasks(db: Session, case_id: str) -> list[dict]:
    from sqlalchemy import select
    state = R.get_case_state(db, case_id) or {}
    fields = {k: (v.get("normalized_value") if isinstance(v, dict) else v)
              for k, v in (state.get("fields") or {}).items()}
    waiting = db.scalars(select(M.Task).where(
        M.Task.case_id == case_id, M.Task.status == "waiting_for_input")).all()
    resumed = []
    for t in waiting:
        ok, missing = E.validate_for_task(t.task_type, fields)
        if ok:
            R.set_task_status(db, t, "queued", waiting_reason=None)
            resumed.append({"task_id": t.id, "status": "queued"})
    return resumed


def execute_task(db: Session, task: M.Task, *, worker_id: str = "worker") -> dict[str, Any]:
    """Synchronous task execution used by the worker loop (and tests).

    Stores plan before execution; each step stores args/result/status.
    Idempotent: steps with the same idempotency key are not re-executed.
    """
    from sqlalchemy import select

    R.set_task_status(db, task, "running", leased_by=worker_id)
    state = R.get_case_state(db, task.case_id) or {}
    fields = {k: (v.get("normalized_value") if isinstance(v, dict) else v)
              for k, v in (state.get("fields") or {}).items()}
    ok, missing = E.validate_for_task(task.task_type, fields)
    run = R.create_run(db, case_id=task.case_id, task_id=task.id,
                       intent=Intent.AUTOMATION_TASK.value, prompt_version=PROMPT_VERSION)
    if not ok:
        prompts = {m: E.missing_prompt(task.task_type, m) for m in missing}
        R.set_task_status(db, task, "waiting_for_input",
                          waiting_reason=json.dumps({"missing": missing, "prompts": prompts}))
        R.add_step(db, run_id=run.id, task_id=task.id, sequence=0, action="validate_fields",
                   tool="validate_fields", arguments={"missing": missing},
                   result={"valid": False}, status="ok")
        return {"task_id": task.id, "status": "waiting_for_input", "missing": missing}

    stored = json.loads(task.plan_json) if task.plan_json else None
    # Phase-4: family plans are viability-pruned against live fields, so they
    # are re-proposed at execution (fields may have arrived via follow-ups).
    # Approval binds at execution on the final plan - never on a preliminary one.
    if task.task_type in planner_mod.FAMILY_ROUTE:
        plan = planner_mod.propose_plan(task.task_type, task.id, fields,
                                        needs_approval=(task.approval_required != "never"))
        # Honest-write rule: a family whose WRITEs all pruned away must ASK
        # for the blocking facts - never silently complete as read-only.
        from harness.tools import formulations as _F
        family = planner_mod.FAMILY_ROUTE[task.task_type]
        blocked = _F.blocking_inputs(family, fields)
        if blocked:
            prompts = {b: _F.prompt_for_input(b) for b in blocked}
            R.set_task_status(db, task, "waiting_for_input",
                              waiting_reason=json.dumps({"missing": blocked,
                                                         "prompts": prompts}))
            R.add_step(db, run_id=run.id, task_id=task.id, sequence=0,
                       action="await_write_inputs", tool="validate_fields",
                       arguments={"missing": blocked},
                       result={"valid": False}, status="ok")
            return {"task_id": task.id, "status": "waiting_for_input",
                    "missing": blocked, "prompts": prompts}
    elif stored and stored.get("steps"):
        from harness.agent.schemas import Plan as _Plan, PlanStep as _PlanStep
        plan = _Plan(task_type=stored.get("task_type", task.task_type),
                     proposed_by=stored.get("proposed_by", "template"),
                     steps=[_PlanStep(**s) for s in stored["steps"]])
    else:
        plan = planner_mod.propose_plan(task.task_type, task.id, fields,
                                        needs_approval=(task.approval_required != "never"))
    effective_requirement = task.approval_required
    current_hash = policy_mod.plan_hash(plan)
    approval_satisfied = False
    # A bound, matching approval satisfies the gate whether or not this task
    # demanded one: the human approved this exact act, so it may run.
    approved = db.scalar(select(M.Approval).where(
        M.Approval.task_id == task.id, M.Approval.decision == "approved")
        .order_by(M.Approval.decided_at.desc()))
    # Phase-2 binding: only a matching approval unlocks, and only the
    # exact act it was requested for. A replanned task re-gates.
    if approved is not None and approved.action_hash == current_hash:
        # One matching human approval unlocks this exact plan; no loop.
        effective_requirement = "never"
        approval_satisfied = True
        for s in plan.steps:
            s.requires_approval = False
    decision = policy_mod.check(plan, approval_required=effective_requirement,
                                approval_satisfied=approval_satisfied)
    task.plan_json = json.dumps({"task_type": plan.task_type,
                                 "proposed_by": plan.proposed_by,
                                 "steps": [s.model_dump() for s in plan.steps]})
    db.commit()
    R.add_step(db, run_id=run.id, task_id=task.id, sequence=0, action="plan",
               arguments={"steps": len(plan.steps)}, result={"policy": decision.reason})
    if not decision.allowed:
        R.set_task_status(db, task, "failed", error_ref=decision.reason)
        return {"task_id": task.id, "status": "failed", "error": decision.reason}
    if decision.needs_approval:
        R.request_approval(db, task_id=task.id, requested_action="execute sensitive plan",
                           action_hash=current_hash)
        R.set_task_status(db, task, "waiting_approval",
                          waiting_reason=json.dumps({"reason": decision.reason}))
        return {"task_id": task.id, "status": "waiting_approval", "reason": decision.reason}

    results: dict[str, Any] = {}
    for step in plan.steps:
        # idempotency: skip if this key already produced a step
        seen = db.scalar(select(M.RunStep).where(
            M.RunStep.task_id == task.id, M.RunStep.idempotency_key == step.idempotency_key))
        if seen and seen.result_json:
            results[step.tool] = json.loads(seen.result_json)
            continue
        args = dict(step.arguments)
        # Formulation steps (CHECK.* / WRITE.*) route via the thin client to
        # the tool module — the only path to the database (PDF v3 §8).
        from harness.tools import formulations as _F
        if step.tool in _F.CATALOG:
            from harness.tools import client as _client
            _fargs = _formulation_args(fields, results, task)
            _env = _client.call_formulation(
                db, formulation_id=step.tool, arguments=_fargs,
                run_id=run.id, task_id=task.id, case_id=task.case_id)
            from harness.tools.registry import ToolResult as _TR
            res = _TR(ok=_env.get("status") == "ok", output=_env,
                      attempts=1, latency_ms=0,
                      error=None if _env.get("status") == "ok" else _env.get("error_ref"))
        elif step.tool == "knowledge_lookup":
            hits = retriever_mod.retrieve(db, task.instructions or "")
            args["citations"] = [h.model_dump() for h in hits]
            res = tools.run_tool(step.tool, {"query": task.instructions or "", "citations": hits},
                                 idempotency_key=step.idempotency_key)
            R.add_citations(db, run_id=run.id, task_id=task.id,
                            hits=[{"version_id": h.version_id, "chunk_id": h.chunk_id,
                                   "text": h.text, "score": h.score} for h in hits])
        elif step.tool == "validate_fields":
            res = tools.run_tool(step.tool, {"fields": fields, "task_type": task.task_type},
                                 idempotency_key=step.idempotency_key)
        elif step.tool == "payment_status_check":
            res = tools.run_tool(step.tool, {"fields": fields}, idempotency_key=step.idempotency_key)
        elif step.tool == "draft_solution":
            summary = (f"{task.task_type} completed with {len(results)} prior step(s). "
                       + str((results.get("payment_status_check") or {}).get("finding", "")))
            snapshot = json.loads(json.dumps(results, default=_json_safe))
            res = tools.run_tool(step.tool, {"summary": summary, "findings": snapshot},
                                 idempotency_key=step.idempotency_key)
        else:
            res = tools.run_tool(step.tool, args, idempotency_key=step.idempotency_key)
        R.add_step(db, run_id=run.id, task_id=task.id, sequence=step.sequence + 1,
                   action=step.action, tool=step.tool, arguments=args,
                   result=res.output, status="ok" if res.ok else "failed",
                   retry_count=max(res.attempts - 1, 0), idempotency_key=step.idempotency_key)
        results[step.tool] = res.output
        # Phase-2 rule: status mirrors reality. A failed REQUIRED step fails
        # the task immediately with the step named - never drafted over.
        # (Transient retry policy is Phase-3 work; terminal truth comes first.)
        if not res.ok and not step.optional:
            err = f"required step failed: {step.tool} ({res.error or 'see step result'})"
            R.set_task_status(db, task, "failed", error_ref=err)
            return {"task_id": task.id, "status": "failed", "error": err}
    summary = (results.get("draft_solution") or {}).get("summary") or f"{task.task_type} executed."
    final = {"summary": summary, "status": "completed", "steps": len(plan.steps),
             "run_id": run.id, "tool_results": results}
    validation = validator_mod.validate_task_result(final)
    if not validation.valid:
        R.set_task_status(db, task, "failed", error_ref=validation.reason)
        return {"task_id": task.id, "status": "failed", "error": validation.reason}
    R.set_task_status(db, task, "completed", result_json=json.dumps(final, default=str))
    return {"task_id": task.id, "status": "completed", "result": final}
