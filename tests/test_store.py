from jobalert.models import Posting
from jobalert.store import Store


def p(uid, company_key="doordash"):
    return Posting(uid=uid, source="greenhouse", company_key=company_key, company="Co", title=uid,
                   locations=["SF"], url=f"https://x/{uid}")


def test_new_closed_and_reopened():
    s = Store(":memory:")
    first = s.sync([p("a"), p("b")], ["doordash"])
    assert sorted(first["new"]) == ["a", "b"]

    second = s.sync([p("a")], ["doordash"])
    assert second == {"new": [], "reopened": [], "closed": ["b"]}
    assert s.get("b")["status"] == "closed"

    third = s.sync([p("a"), p("b")], ["doordash"])
    assert third["reopened"] == ["b"]
    assert s.get("b")["status"] == "open"


def test_failed_source_never_closes_postings():
    s = Store(":memory:")
    s.sync([p("a"), p("z", "zoox")], ["doordash", "zoox"])
    # zoox's board failed this run, so it is not in the fetched list
    changes = s.sync([p("a")], ["doordash"])
    assert changes["closed"] == []
    assert s.get("z")["status"] == "open"


def test_user_status():
    s = Store(":memory:")
    s.sync([p("a")], ["doordash"])
    assert s.set_user_status("a", "applied")
    assert s.get("a")["user_status"] == "applied"
    assert not s.set_user_status("missing", "applied")
