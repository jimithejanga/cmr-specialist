"""Model-proposes-plan: ordering from the model, enforcement by the harness.

Phase-4 routing: payment/ownership families plan in CHECK/WRITE formulations;
general_support keeps the internal-tool flows.
"""
from harness.agent import planner
from harness.tools import formulations as F


def test_model_proposal_reorders_but_cannot_invent(monkeypatch):
    monkeypatch.setattr(
        "harness.agent.llm.propose_json",
        lambda **kw: {"tools": ["draft_solution", "rm_rf_everything",
                                "validate_fields", "knowledge_lookup",
                                "payment_status_check", "draft_solution"]},
    )
    plan = planner.propose_plan("general_support", "t1", {})
    assert plan.proposed_by == "model"
    assert "rm_rf_everything" not in plan.tool_names()
    assert set(plan.tool_names()) <= {"knowledge_lookup", "draft_solution"}
    assert len(plan.steps) <= 12


def test_family_proposal_stays_in_catalog(monkeypatch):
    monkeypatch.setattr(
        "harness.agent.llm.propose_json",
        lambda **kw: {"tools": ["WRITE.transfer.initiate", "rm_rf_everything",
                                "CHECK.vehicle.lookup"]},
    )
    fields = {"plate_number": "ABC123XY", "buyer_name": "Ada",
              "seller_name": "Musa", "phone": "08012345678"}
    plan = planner.propose_plan("change_of_ownership", "t9", fields)
    assert plan.proposed_by == "model"
    assert "rm_rf_everything" not in plan.tool_names()
    assert set(plan.tool_names()) <= set(F.FAMILY_PLANS["change_of_ownership"])
    writes = [s for s in plan.steps if s.tool.startswith("WRITE.")]
    assert writes and all(s.requires_approval for s in writes)


def test_silent_model_falls_back_to_template(monkeypatch):
    monkeypatch.setattr("harness.agent.llm.propose_json", lambda **kw: None)
    plan = planner.propose_plan("general_support", "t2", {})
    assert plan.proposed_by == "template"
    assert plan.tool_names() == ["knowledge_lookup", "draft_solution"]


def test_silent_family_falls_back_to_formulations(monkeypatch):
    monkeypatch.setattr("harness.agent.llm.propose_json", lambda **kw: None)
    fields = {"plate_number": "ABC123XY", "buyer_name": "Ada",
              "seller_name": "Musa", "phone": "08012345678"}
    plan = planner.propose_plan("change_of_ownership", "t2b", fields)
    assert plan.proposed_by == "template"
    assert plan.tool_names() == F.viable_family_plan("change_of_ownership", fields)
    assert plan.tool_names()[0] == "CHECK.vehicle.lookup"


def test_garbage_proposal_falls_back_to_template(monkeypatch):
    monkeypatch.setattr("harness.agent.llm.propose_json",
                        lambda **kw: {"tools": ["nuke", "pillage"]})
    plan = planner.propose_plan("general_support", "t3", {})
    assert plan.proposed_by == "template"
