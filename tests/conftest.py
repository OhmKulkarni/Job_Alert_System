"""Shared fakes. Sample payloads mirror the real APIs' shapes (trimmed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobalert.config import AppConfig, CompanyConfig, Settings, load_config
from jobalert.llm import ChatResponse, ToolCall

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    """Routes GET/POST by URL substring to canned payloads."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple[str, str, dict | None]] = []
        self.headers = {}

    def _match(self, url, arg):
        for key, value in self.routes.items():
            if key in url:
                return value(arg) if callable(value) else value
        return FakeResponse({}, status=404)

    def get(self, url, timeout=None, **kwargs):
        self.calls.append(("GET", url, None))
        return self._match(url, url)  # callables receive the URL

    def post(self, url, json=None, timeout=None, **kwargs):
        self.calls.append(("POST", url, json))
        return self._match(url, json)  # callables receive the JSON payload


class FakeModel:
    """Plays back scripted ChatResponses and records what it was sent."""

    model = "fake-model"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, tools=None, schema=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools, "schema": schema})
        if not self.script:
            return ChatResponse(content="I am done.")
        nxt = self.script.pop(0)
        return nxt(messages) if callable(nxt) else nxt


def call(name, **arguments) -> ChatResponse:
    return ChatResponse(tool_calls=[ToolCall(name=name, arguments=arguments)])


def assessment_args(**overrides):
    args = {
        "fit_score": 86,
        "recommended_resume": "data_science",
        "confidence": "high",
        "ai_forward": "yes",
        "reasons": ["ML internship for master's students", "Python and PyTorch match"],
        "gaps": [],
        "evidence": ["currently pursuing a Master's degree"],
    }
    args.update(overrides)
    return args


@pytest.fixture
def config() -> AppConfig:
    return load_config(ROOT / "config")


@pytest.fixture
def settings(config) -> Settings:
    return config.settings


def company(key="doordash", source="greenhouse", slug="doordashusa", **kw) -> CompanyConfig:
    return CompanyConfig(key=key, name=kw.pop("name", key.title()), source=source, slug=slug, **kw)


ML_DESCRIPTION = (
    "<p>About the team</p><p>We build ML models for logistics.</p>"
    "<ul><li>You are currently pursuing a Master&#39;s degree in Computer Science or Data Science</li>"
    "<li>Experience with Python and PyTorch</li><li>You use LLM tools to speed up experimentation</li></ul>"
    "<p>This is a Summer 2027 internship.</p>"
)

GREENHOUSE_JOBS = {
    "jobs": [
        {
            "id": 111,
            "title": "Machine Learning Intern (Masters) - Summer 2027",
            "absolute_url": "https://job-boards.greenhouse.io/doordashusa/jobs/111",
            "location": {"name": "San Francisco, CA;  Sunnyvale, CA ; New York City, NY"},
            "first_published": "2026-10-22T09:31:00-04:00",
            "updated_at": "2026-11-04T16:15:15-05:00",
            # Greenhouse double-escapes its HTML
            "content": ML_DESCRIPTION.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"),
        },
        {
            "id": 222,
            "title": "Internal Audit Senior Manager",
            "absolute_url": "https://job-boards.greenhouse.io/doordashusa/jobs/222",
            "location": {"name": "Menlo Park, CA"},
            "content": "",
        },
        {
            "id": 333,
            "title": "Drone Operations, Intern - Labs (Summer 2027)",
            "absolute_url": "https://job-boards.greenhouse.io/doordashusa/jobs/333",
            "location": {"name": "San Francisco, CA"},
            "content": "",
        },
    ]
}

LEVER_JOBS = [
    {
        "id": "6ed76ce8",
        "text": "AI Workflows Intern [Summer 2027]",
        "hostedUrl": "https://jobs.lever.co/zoox/6ed76ce8",
        "createdAt": 1786469891368,
        "categories": {"commitment": "Intern", "location": "Foster City, CA", "allLocations": ["Foster City, CA"]},
        "descriptionPlain": "Help teams adopt AI workflows.",
        "lists": [{"text": "Qualifications", "content": "<li>Pursuing an MS degree</li>"}],
        "additionalPlain": "",
    }
]

ASHBY_JOBS = {
    "jobs": [
        {
            "id": "34413f8d",
            "title": "Software Engineer Intern, Agent (Summer 2027)",
            "location": "San Francisco, CA",
            "secondaryLocations": [{"location": "Remote (US)"}],
            "isListed": True,
            "publishedAt": "2026-04-07T17:12:35.753+00:00",
            "jobUrl": "https://jobs.ashbyhq.com/sierra/34413f8d",
            "descriptionPlain": "Build customer-facing AI agents.",
        },
        {"id": "hidden", "title": "Unlisted", "location": "SF", "isListed": False, "jobUrl": "x"},
    ]
}


def smartrecruiters_page(url):
    offset = int(url.rsplit("offset=", 1)[-1])
    content = [
        {
            "id": f"7440{offset + i}",
            "name": "Data Science Intern" if offset + i == 0 else f"Engineering Manager {offset + i}",
            "location": {"city": "Sunnyvale", "region": "CA", "country": "us", "remote": False,
                         "fullLocation": "Sunnyvale, CA, United States"},
            "releasedDate": "2026-11-13T22:59:57.899Z",
            "ref": f"https://api.smartrecruiters.com/v1/companies/LinkedIn3/postings/7440{offset + i}",
        }
        for i in range(100 if offset == 0 else 30)
    ]
    return FakeResponse({"offset": offset, "limit": 100, "totalFound": 130, "content": content})


SMARTRECRUITERS_DETAIL = {
    "jobAd": {
        "sections": {
            "jobDescription": {"text": "<p>Work on <b>ML</b> for the feed.</p>"},
            "qualifications": {"text": "<ul><li>MS student</li></ul>"},
        }
    }
}


def workday_page(payload):
    offset = payload["offset"]
    batch = [
        {
            "title": f"Intern {offset + i}",
            "externalPath": f"/job/USA-San-Jose/Intern_R{offset + i:05d}",
            "locationsText": "USA-San Jose",
            "postedOn": "Posted Yesterday",
            "bulletFields": [f"R{offset + i:05d}"],
        }
        for i in range(20 if offset < 20 else 5)
    ]
    return FakeResponse({"total": 25, "jobPostings": batch})


EIGHTFOLD_SEARCH = {
    "status": 200,
    "data": {
        "count": 2,
        "positions": [
            {
                "id": 274922982821,
                "name": "Data Scientist Intern - Summer 2027",
                "locations": ["San Jose, California, United States of America"],
                "postedTs": 1793836800,
                "positionUrl": "/careers/job/274922982821",
            },
            {
                "id": 274922982812,
                "name": "Cybersecurity Intern - Summer 2027",
                "locations": ["San Jose, California, United States of America"],
                "postedTs": 1793836800,
                "positionUrl": "/careers/job/274922982812",
            },
        ],
    },
}

EIGHTFOLD_DETAIL = {"data": {"jobDescription": "<p>The Company</p><p>PayPal data science intern.</p>"}}


def dump(obj) -> str:
    return json.dumps(obj, default=str)
