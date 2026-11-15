import pytest

from jobalert.filters import RuleFilter
from jobalert.models import Decision, Posting


def posting(title, locations=("San Francisco, CA",), description="", company_key="doordash"):
    return Posting(uid=f"t:{title}", source="greenhouse", company_key=company_key, company="Co",
                   title=title, locations=list(locations), url="https://x", description=description)


@pytest.fixture
def rules(config):
    return RuleFilter(config.settings.filters, config.profile)


@pytest.mark.parametrize("title", [
    "Internal Audit Senior Manager",
    "International Payroll Analyst",
    "Senior Manager, Internal Comms",
])
def test_internal_and_international_are_not_internships(rules, title):
    assert rules.evaluate(posting(title)).decision == Decision.REJECT


def test_target_ml_internship_is_shortlisted(rules):
    r = rules.evaluate(posting("Machine Learning Intern (Masters) - Summer 2027"))
    assert r.decision == Decision.SHORTLIST
    assert r.region == "Bay Area"


@pytest.mark.parametrize("title,why", [
    ("Machine Learning Intern (Winter 2027)", "wrong season"),
    ("Software Engineer Intern, Mobile (Summer 2027)", "off-target role"),
    ("Data Science Intern - Summer 2026", "wrong season"),
    ("Data Science Intern 2026", "wrong year"),
    ("[2027] Data Scientist - PhD Intern", "PhD-only"),
    ("Drone Operations, Intern - Labs (Summer 2027)", "off-target role"),
    ("Machine Learning Intern/Co-op (Winter 2027)", "wrong season"),
])
def test_rule_rejections_explain_themselves(rules, title, why):
    r = rules.evaluate(posting(title))
    assert r.decision == Decision.REJECT
    assert why in r.reasons[0]


def test_bs_ms_phd_title_is_open_to_masters(rules):
    r = rules.evaluate(posting("2027 Summer Intern, BS/MS/PhD, Machine Learning", ["Mountain View, CA, USA"]))
    assert r.decision == Decision.SHORTLIST


def test_outside_regions_rejected_but_remote_us_accepted(rules):
    assert rules.evaluate(posting("ML Intern 2027", ["London, UK"])).decision == Decision.REJECT
    assert rules.evaluate(posting("ML Intern 2027", ["Remote (US)"])).decision == Decision.SHORTLIST


def test_orange_county_outranks_bay_area(rules):
    oc = rules.evaluate(posting("AI Intern Summer 2027", ["Costa Mesa, California, United States"]))
    bay = rules.evaluate(posting("AI Intern Summer 2027", ["San Jose, CA"]))
    assert oc.region == "Orange County"
    assert oc.prescore > bay.prescore


def test_unclear_cases_go_to_the_agent_not_the_bin(rules):
    # adjacent role, no season stated: let the agent judge
    r = rules.evaluate(posting("Software Engineer Intern", ["San Francisco, CA"]))
    assert r.decision == Decision.MAYBE
    assert "season not stated" in r.reasons


def test_season_from_description(rules):
    r = rules.evaluate(posting("Data Science Intern", description="Join us for summer 2027 in SF."))
    assert r.decision == Decision.SHORTLIST


def test_connection_bonus(rules):
    with_friend = rules.evaluate(posting("Data Scientist Intern - Summer 2027", company_key="paypal"))
    without = rules.evaluate(posting("Data Scientist Intern - Summer 2027"))
    assert with_friend.prescore > without.prescore
    assert "you have a contact here" in with_friend.reasons
