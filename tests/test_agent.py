import json

import pytest

from jobalert.agent import JobAgent, draft_outreach, ground_evidence
from jobalert.config import AgentConfig
from jobalert.llm import BudgetedModel, BudgetExceeded, CallBudget, ChatResponse
from jobalert.models import Assessment, Posting
from jobalert.text import html_to_text

from .conftest import ML_DESCRIPTION, FakeModel, assessment_args, call


@pytest.fixture
def posting():
    return Posting(
        uid="greenhouse:doordash:111", source="greenhouse", company_key="doordash", company="DoorDash",
        title="Machine Learning Intern (Masters) - Summer 2027", locations=["San Francisco, CA"],
        url="https://job-boards.greenhouse.io/doordashusa/jobs/111", description=html_to_text(ML_DESCRIPTION),
    )


@pytest.fixture
def agent_cfg():
    return AgentConfig(max_steps_per_posting=4, review_if_score_between=(55, 70))


def test_agent_investigates_then_submits(config, posting, agent_cfg):
    model = FakeModel([
        call("get_profile"),
        call("search_posting", terms=["master", "degree"]),
        call("submit_assessment", **assessment_args()),
    ])
    rec = JobAgent(model, config.profile, agent_cfg).assess(posting)
    assert rec.tool_calls == ["get_profile", "search_posting", "submit_assessment"]
    assert rec.assessment.fit_score == 86
    assert rec.needs_review is False
    # search results were fed back to the model as a tool message
    tool_msgs = [m for m in model.calls[2]["messages"] if m["role"] == "tool"]
    assert "Master's degree" in tool_msgs[-1]["content"]


def test_bad_arguments_are_returned_as_errors_and_the_agent_recovers(config, posting, agent_cfg):
    model = FakeModel([
        call("read_posting", page=0),  # invalid: pages start at 1
        call("submit_assessment", **assessment_args(recommended_resume="marketing")),  # not a resume key
        call("submit_assessment", **assessment_args()),
    ])
    rec = JobAgent(model, config.profile, agent_cfg).assess(posting)
    errors = [m["content"] for m in model.calls[2]["messages"] if m["role"] == "tool"]
    assert errors[0].startswith("ERROR: Invalid arguments for read_posting")
    assert "recommended_resume must be one of" in errors[1]
    assert rec.assessment.recommended_resume == "data_science"


def test_unknown_tool(config, posting, agent_cfg):
    model = FakeModel([call("browse_web", url="x"), call("submit_assessment", **assessment_args())])
    JobAgent(model, config.profile, agent_cfg).assess(posting)
    tool_msgs = [m for m in model.calls[1]["messages"] if m["role"] == "tool"]
    assert "Unknown tool 'browse_web'" in tool_msgs[0]["content"]


def test_finalize_with_schema_when_agent_never_submits(config, posting, agent_cfg):
    chatter = [ChatResponse(content="Let me think...")] * agent_cfg.max_steps_per_posting
    final = ChatResponse(content=json.dumps(assessment_args(fit_score=80)))
    model = FakeModel(chatter + [final])
    rec = JobAgent(model, config.profile, agent_cfg).assess(posting)
    assert model.calls[-1]["schema"]["properties"]["recommended_resume"]["enum"] == config.profile.resume_keys()
    assert "$ref" not in json.dumps(model.calls[-1]["schema"])
    assert rec.tool_calls[-1] == "finalize"
    assert rec.assessment.fit_score == 80


def test_invalid_finalize_flags_for_review(config, posting, agent_cfg):
    chatter = [ChatResponse(content="hmm")] * agent_cfg.max_steps_per_posting
    model = FakeModel(chatter + [ChatResponse(content="{not json")])
    rec = JobAgent(model, config.profile, agent_cfg).assess(posting)
    assert rec.assessment is None
    assert rec.needs_review
    assert "agent could not produce a valid assessment" in rec.review_reasons


def test_invented_evidence_is_dropped_and_flagged(config, posting, agent_cfg):
    args = assessment_args(evidence=["currently pursuing a Master's degree", "10+ years of Kubernetes"])
    rec = JobAgent(FakeModel([call("submit_assessment", **args)]), config.profile, agent_cfg).assess(posting)
    assert rec.assessment.evidence == ["currently pursuing a Master's degree"]
    assert rec.needs_review
    assert "1 evidence quote(s) not found in the posting" in rec.review_reasons


@pytest.mark.parametrize("override,reason", [
    ({"confidence": "low"}, "agent confidence is low"),
    ({"fit_score": 62}, "borderline score (62)"),
    ({"fit_score": 8}, "very low score (8); check it was on the 0-100 scale"),
])
def test_review_triggers(config, posting, agent_cfg, override, reason):
    rec = JobAgent(FakeModel([call("submit_assessment", **assessment_args(**override))]),
                   config.profile, agent_cfg).assess(posting)
    assert rec.needs_review and reason in rec.review_reasons


def test_budget_is_enforced_across_postings(config, posting, agent_cfg):
    model = BudgetedModel(FakeModel([call("get_profile")] * 10), CallBudget(3))
    with pytest.raises(BudgetExceeded):
        JobAgent(model, config.profile, agent_cfg).assess(posting)
    assert model.budget.used == 3


def test_ground_evidence_ignores_case_and_punctuation():
    found, missing = ground_evidence(["PYTHON and PyTorch!", "Rust"], "Experience with Python and PyTorch.")
    assert found == ["PYTHON and PyTorch!"] and missing == ["Rust"]


def test_outreach_only_keeps_the_job_link(config, posting):
    text = f"Hey Sam! Saw this ML intern role: {posting.url} - also see http://evil.example/x. Free for a call?"
    model = FakeModel([ChatResponse(content=json.dumps({"message": text}))])
    draft = draft_outreach(model, posting, Assessment(**assessment_args()), "Sam", config.profile)
    assert posting.url in draft
    assert "evil.example" not in draft
    assert model.calls[0]["schema"]["required"] == ["message"]
