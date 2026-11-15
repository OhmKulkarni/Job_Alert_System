"""Adapters for each job-board API. Each one maps a raw posting to `Posting`.

All endpoints are the public, unauthenticated APIs the boards themselves use.
"""
from __future__ import annotations

from urllib.parse import quote

from ..config import CompanyConfig
from ..models import Posting
from ..text import html_to_text
from .base import Source, SourceError, from_epoch, parse_iso


class GreenhouseSource(Source):
    name = "greenhouse"
    URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        data = self._get_json(self.URL.format(slug=quote(company.slug)))
        return [self.parse(job, company) for job in data.get("jobs", [])]

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        location = (job.get("location") or {}).get("name") or ""
        locations = [part.strip() for part in location.replace(";", "|").replace("•", "|").split("|") if part.strip()]
        return Posting(
            uid=self.uid(company, job["id"]),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("title") or "").strip(),
            locations=locations,
            url=job.get("absolute_url") or "",
            posted_at=parse_iso(job.get("first_published") or job.get("updated_at")),
            description=html_to_text(job.get("content")),
        )


class LeverSource(Source):
    name = "lever"
    URL = "https://api.lever.co/v0/postings/{slug}?mode=json"

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        data = self._get_json(self.URL.format(slug=quote(company.slug)))
        if not isinstance(data, list):
            raise SourceError(f"lever: unexpected response for {company.slug}")
        return [self.parse(job, company) for job in data]

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        cats = job.get("categories") or {}
        locations = cats.get("allLocations") or ([cats["location"]] if cats.get("location") else [])
        parts = [job.get("descriptionPlain") or ""]
        for block in job.get("lists") or []:
            parts.append(f"{block.get('text', '')}\n{html_to_text(block.get('content'))}")
        parts.append(job.get("additionalPlain") or "")
        return Posting(
            uid=self.uid(company, job["id"]),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("text") or "").strip(),
            locations=[loc.strip() for loc in locations if loc],
            url=job.get("hostedUrl") or "",
            posted_at=from_epoch(job.get("createdAt"), millis=True),
            description="\n\n".join(p.strip() for p in parts if p and p.strip()),
        )


class AshbySource(Source):
    name = "ashby"
    URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        data = self._get_json(self.URL.format(slug=quote(company.slug)))
        return [self.parse(job, company) for job in data.get("jobs", []) if job.get("isListed", True)]

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        locations = [job.get("location") or ""]
        locations += [s.get("location", "") for s in job.get("secondaryLocations") or []]
        return Posting(
            uid=self.uid(company, job["id"]),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("title") or "").strip(),
            locations=[loc.strip() for loc in locations if loc and loc.strip()],
            url=job.get("jobUrl") or "",
            posted_at=parse_iso(job.get("publishedAt")),
            description=(job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml"))).strip(),
        )


class SmartRecruitersSource(Source):
    name = "smartrecruiters"
    URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
    PAGE_CAP = 20  # 2,000 postings is far more than any watchlist company needs

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        postings: list[Posting] = []
        offset = 0
        for _ in range(self.PAGE_CAP):
            data = self._get_json(self.URL.format(slug=quote(company.slug), offset=offset))
            content = data.get("content", [])
            postings += [self.parse(job, company) for job in content]
            offset += len(content)
            if not content or offset >= data.get("totalFound", 0):
                break
        return postings

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        loc = job.get("location") or {}
        location = loc.get("fullLocation") or ", ".join(
            x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x
        )
        if loc.get("remote"):
            location = f"{location} (Remote)" if location else "Remote"
        return Posting(
            uid=self.uid(company, job["id"]),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("name") or "").strip(),
            locations=[location] if location else [],
            url=f"https://jobs.smartrecruiters.com/{company.slug}/{job['id']}",
            posted_at=parse_iso(job.get("releasedDate")),
            description=None,  # fetched lazily: the list endpoint has no description
            detail_ref=job.get("ref"),
        )

    def fetch_description(self, posting: Posting, company: CompanyConfig) -> str:
        if posting.description:
            return posting.description
        if not posting.detail_ref:
            return ""
        detail = self._get_json(posting.detail_ref)
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        order = ("jobDescription", "qualifications", "additionalInformation")
        return "\n\n".join(
            html_to_text((sections.get(k) or {}).get("text")) for k in order if sections.get(k)
        ).strip()


class WorkdaySource(Source):
    name = "workday"
    PAGE = 20  # Workday's maximum page size
    PAGE_CAP = 15

    def _base(self, company: CompanyConfig) -> str:
        tenant = company.host.split(".")[0]
        return f"https://{company.host}/wday/cxs/{tenant}/{company.site}"

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        postings: list[Posting] = []
        offset = 0
        for _ in range(self.PAGE_CAP):
            payload = {
                "appliedFacets": {},
                "limit": self.PAGE,
                "offset": offset,
                "searchText": company.search_text or "",
            }
            data = self._post_json(f"{self._base(company)}/jobs", payload)
            batch = data.get("jobPostings", [])
            postings += [self.parse(job, company) for job in batch if job.get("externalPath")]
            offset += len(batch)
            if not batch or offset >= data.get("total", 0):
                break
        return postings

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        path = job["externalPath"]
        native_id = (job.get("bulletFields") or [path.rsplit("_", 1)[-1]])[0]
        return Posting(
            uid=self.uid(company, native_id),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("title") or "").strip(),
            locations=[job["locationsText"]] if job.get("locationsText") else [],
            url=f"https://{company.host}/{company.site}{path}",
            posted_at=None,  # Workday lists only relative dates ("Posted Yesterday")
            description=None,
            detail_ref=path,
        )

    def fetch_description(self, posting: Posting, company: CompanyConfig) -> str:
        if posting.description:
            return posting.description
        detail = self._get_json(f"{self._base(company)}{posting.detail_ref}")
        info = detail.get("jobPostingInfo") or {}
        return html_to_text(info.get("jobDescription"))


class EightfoldSource(Source):
    """Eightfold career sites (used by PayPal). Uses the site's own search API."""

    name = "eightfold"
    PAGE = 10
    PAGE_CAP = 10

    def fetch(self, company: CompanyConfig) -> list[Posting]:
        postings: list[Posting] = []
        start = 0
        query = quote(company.search_text or "")
        for _ in range(self.PAGE_CAP):
            url = (
                f"https://{company.host}/api/pcsx/search?domain={quote(company.slug)}"
                f"&query={query}&start={start}"
            )
            data = self._get_json(url).get("data") or {}
            batch = data.get("positions") or []
            postings += [self.parse(job, company) for job in batch]
            start += len(batch)
            if not batch or start >= data.get("count", 0):
                break
        return postings

    def parse(self, job: dict, company: CompanyConfig) -> Posting:
        return Posting(
            uid=self.uid(company, job["id"]),
            source=self.name,
            company_key=company.key,
            company=company.name,
            title=(job.get("name") or "").strip(),
            locations=job.get("locations") or job.get("standardizedLocations") or [],
            url=f"https://{company.host}{job.get('positionUrl') or '/careers/job/' + str(job['id'])}",
            posted_at=from_epoch(job.get("postedTs")),
            description=None,
            detail_ref=str(job["id"]),
        )

    def fetch_description(self, posting: Posting, company: CompanyConfig) -> str:
        if posting.description:
            return posting.description
        url = (
            f"https://{company.host}/api/pcsx/position_details?position_id={posting.detail_ref}"
            f"&domain={quote(company.slug)}&hl=en"
        )
        data = self._get_json(url).get("data") or {}
        return html_to_text(data.get("jobDescription"))


SOURCES: dict[str, type[Source]] = {
    cls.name: cls
    for cls in (
        GreenhouseSource,
        LeverSource,
        AshbySource,
        SmartRecruitersSource,
        WorkdaySource,
        EightfoldSource,
    )
}
