"""End to end: fake job boards + fake model through the real pipeline."""
import copy
import json

import pytest

from jobalert.llm import ChatResponse
from jobalert.config import AppConfig, CompanyConfig, Connection
from jobalert.pipeline import RunOptions, run
from jobalert.store import Store

from .conftest import GREENHOUSE_JOBS, FakeModel, FakeResponse, FakeSession, assessment_args, call


@pytest.fixture
def app(config, tmp_path) -> AppConfig:
    cfg = config.model_copy(deep=True)
    cfg.settings.output_dir = str(tmp_path / "out")
    cfg.watchlist = [
        CompanyConfig(key="doordash", name="DoorDash", source="greenhouse", slug="doordashusa"),
        CompanyConfig(key="zoox", name="Zoox", source="lever", slug="zoox"),
    ]
    cfg.profile.connections = [Connection(company_key="doordash", name="Sam")]
    return cfg


def boards(jobs=GREENHOUSE_JOBS):
    return FakeSession({
        "boards-api.greenhouse.io": FakeResponse(jobs),
        "api.lever.co": FakeResponse({}, status=503),
    })


def test_full_run_then_rerun_then_close(app, monkeypatch):
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    store = Store(":memory:")

    model = FakeModel([
        call("get_profile"),
        call("submit_assessment", **assessment_args()),
        ChatResponse(content=json.dumps({"message": "Hey Sam, saw an ML intern role at DoorDash. Quick call?"})),
    ])
    result = run(app, store, RunOptions(dry_run=True), session=boards(), model=model)

    assert result.stats["fetched"] == 3 and result.stats["new"] == 3
    # 1 shortlisted ML role; audit job + drone operations rejected by rules, never reached the model
    assert result.stats["filtered"] == {"shortlist": 1, "maybe": 0, "reject": 2}
    assert result.stats["assessed"] == 1
    assert len(model.calls) == 3

    html = result.digest_path.read_text()
    assert "Machine Learning Intern (Masters) - Summer 2027" in html
    assert "Fit 86/100" in html
    assert "Data Science / ML resume" in html
    assert "Draft note to Sam" in html
    assert "Could not reach zoox" in html  # failing board is reported, not fatal
    assert "Drone Operations" not in html

    # Second run: nothing new, the model is not called again
    model2 = FakeModel([])
    result2 = run(app, store, RunOptions(dry_run=True), session=boards(), model=model2)
    assert result2.stats["new"] == 0 and result2.stats["assessed"] == 0
    assert model2.calls == []

    # Third run: the ML posting disappears from the board -> reported as closed
    jobs = copy.deepcopy(GREENHOUSE_JOBS)
    jobs["jobs"] = jobs["jobs"][1:]
    result3 = run(app, store, RunOptions(dry_run=True), session=boards(jobs), model=FakeModel([]))
    assert result3.stats["closed"] == 1
    assert "Closed since last run" in result3.digest_path.read_text()


def test_titles_from_the_web_are_escaped(app):
    jobs = copy.deepcopy(GREENHOUSE_JOBS)
    jobs["jobs"][0]["title"] = "ML Intern Summer 2027 <script>alert(1)</script>"
    result = run(app, Store(":memory:"), RunOptions(dry_run=True, use_llm=False), session=boards(jobs))
    html = result.digest_path.read_text()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_without_llm_survivors_are_listed_as_pending(app):
    result = run(app, Store(":memory:"), RunOptions(dry_run=True, use_llm=False), session=boards())
    html = result.digest_path.read_text()
    assert "Passed the filters, not assessed yet (1)" in html
    assert "AI assessment skipped (--no-llm)." in html


def test_ollama_down_degrades_gracefully(app, monkeypatch):
    from jobalert import pipeline

    class DownClient:
        model = "x"

        def __init__(self, cfg):
            pass

        def health(self):
            return False, "Ollama is not reachable at http://localhost:11434 (ConnectionError)"

    monkeypatch.setattr(pipeline, "OllamaClient", DownClient)
    result = run(app, Store(":memory:"), RunOptions(dry_run=True), session=boards())
    assert result.stats["assessed"] == 0
    assert "Ollama is not reachable" in result.digest_path.read_text()
