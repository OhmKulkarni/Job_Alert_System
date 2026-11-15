from jobalert.sources import fetch_all
from jobalert.sources.boards import (
    AshbySource,
    EightfoldSource,
    GreenhouseSource,
    LeverSource,
    SmartRecruitersSource,
    WorkdaySource,
)
from jobalert.text import html_to_text

from .conftest import (
    ASHBY_JOBS,
    EIGHTFOLD_DETAIL,
    EIGHTFOLD_SEARCH,
    GREENHOUSE_JOBS,
    LEVER_JOBS,
    SMARTRECRUITERS_DETAIL,
    FakeResponse,
    FakeSession,
    company,
    smartrecruiters_page,
    workday_page,
)


def test_html_to_text_handles_double_escaped_html():
    raw = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    assert html_to_text(raw).split("\n") == ["Hello & welcome", "", "- Python"]


def test_greenhouse_parses_locations_and_description():
    s = FakeSession({"boards-api.greenhouse.io": FakeResponse(GREENHOUSE_JOBS)})
    postings = GreenhouseSource(s).fetch(company())
    ml = postings[0]
    assert ml.uid == "greenhouse:doordash:111"
    assert ml.locations == ["San Francisco, CA", "Sunnyvale, CA", "New York City, NY"]
    assert "currently pursuing a Master's degree" in ml.description
    assert "<" not in ml.description
    assert ml.posted_at.year == 2026


def test_lever_merges_lists_into_description():
    s = FakeSession({"api.lever.co": FakeResponse(LEVER_JOBS)})
    [p] = LeverSource(s).fetch(company("zoox", "lever", "zoox"))
    assert p.title == "AI Workflows Intern [Summer 2027]"
    assert p.locations == ["Foster City, CA"]
    assert "Pursuing an MS degree" in p.description


def test_ashby_skips_unlisted_and_keeps_secondary_locations():
    s = FakeSession({"api.ashbyhq.com": FakeResponse(ASHBY_JOBS)})
    postings = AshbySource(s).fetch(company("sierra", "ashby", "sierra"))
    assert len(postings) == 1
    assert postings[0].locations == ["San Francisco, CA", "Remote (US)"]


def test_smartrecruiters_paginates_and_fetches_description_lazily():
    s = FakeSession({
        "postings?limit": smartrecruiters_page,
        "/postings/74400": FakeResponse(SMARTRECRUITERS_DETAIL),
    })
    src = SmartRecruitersSource(s)
    co = company("linkedin", "smartrecruiters", "LinkedIn3")
    postings = src.fetch(co)
    assert len(postings) == 130
    assert postings[0].description is None
    text = src.fetch_description(postings[0], co)
    assert "Work on ML for the feed." in text and "MS student" in text


def test_workday_paginates_with_post():
    s = FakeSession({"/wday/cxs/broadcom/External_Career/jobs": lambda payload: workday_page(payload)})
    co = company("broadcom", "workday", "broadcom", host="broadcom.wd1.myworkdayjobs.com",
                 site="External_Career", search_text="intern")
    postings = WorkdaySource(s).fetch(co)
    assert len(postings) == 25
    assert postings[0].uid == "workday:broadcom:R00000"
    assert postings[0].url == "https://broadcom.wd1.myworkdayjobs.com/External_Career/job/USA-San-Jose/Intern_R00000"
    assert s.calls[0][2]["searchText"] == "intern"


def test_eightfold_search_and_detail():
    s = FakeSession({
        "/api/pcsx/search": FakeResponse(EIGHTFOLD_SEARCH),
        "/api/pcsx/position_details": FakeResponse(EIGHTFOLD_DETAIL),
    })
    co = company("paypal", "eightfold", "paypal.com", host="paypal.eightfold.ai", search_text="intern")
    src = EightfoldSource(s)
    postings = src.fetch(co)
    assert [p.title for p in postings][0] == "Data Scientist Intern - Summer 2027"
    assert postings[0].url == "https://paypal.eightfold.ai/careers/job/274922982821"
    assert "PayPal data science intern." in src.fetch_description(postings[0], co)


def test_fetch_all_isolates_a_failing_board():
    s = FakeSession({
        "boards-api.greenhouse.io/v1/boards/doordashusa": FakeResponse(GREENHOUSE_JOBS),
        "boards-api.greenhouse.io/v1/boards/broken": FakeResponse({}, status=503),
        "api.lever.co": FakeResponse(ValueError("not json")),
    })
    report = fetch_all(
        [company(), company("broken", slug="broken"), company("zoox", "lever", "zoox")], s, workers=1
    )
    assert report.ok == {"doordash": 3}
    assert set(report.failed) == {"broken", "zoox"}
    assert len(report.postings) == 3
