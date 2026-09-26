"""Model-proposes-plan: ordering from the model, enforcement by the harness."""
from harness.agent import planner


def test_model_proposal_reorders_but_cannot_invent(monkeypatch):
    monkeypatch.setattr(
        "harness.agent.llm.propose_json",
        lambda **kw: {"tools": ["draft_solution", "rm_rf_everything",
                                "validate_fields", "knowledge_lookup",
                                "payment_status_check", "draft_solution"]},
    )
    plan = planner.propose_plan("payment_reconciliation", "t1", {})
    assert plan.proposed_by == "model"
    assert "rm_rf_everything" not in plan.tool_names()
    assert set(plan.tool_names()) <= {"validate_fields", "knowledge_lookup",
                                      "payment_status_check", "draft_solution"}
    assert len(plan.steps) <= 12


def test_silent_model_falls_back_to_template(monkeypatch):
    monkeypatch.setattr("harness.agent.llm.propose_json", lambda **kw: None)
    plan = planner.propose_plan("change_of_ownership", "t2", {})
    assert plan.proposed_by == "template"
    assert plan.tool_names() == ["validate_fields", "knowledge_lookup", "draft_solution"]


def test_garbage_proposal_falls_back_to_template(monkeypatch):
    monkeypatch.setattr("harness.agent.llm.propose_json",
                        lambda **kw: {"tools": ["nuke", "pillage"]})
    plan = planner.propose_plan("general_support", "t3", {})
    assert plan.proposed_by == "template"
