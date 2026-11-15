"""Fetch postings from every watchlist company, isolating failures per company."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests

from ..config import CompanyConfig
from ..models import Posting
from .base import Source, SourceError
from .boards import SOURCES

log = logging.getLogger("jobalert.sources")

__all__ = ["FetchReport", "Source", "SourceError", "SOURCES", "fetch_all", "source_for"]


@dataclass
class FetchReport:
    postings: list[Posting] = field(default_factory=list)
    ok: dict[str, int] = field(default_factory=dict)  # company key -> postings fetched
    failed: dict[str, str] = field(default_factory=dict)  # company key -> error


def source_for(company: CompanyConfig, session: requests.Session) -> Source:
    return SOURCES[company.source](session)


def fetch_all(companies: list[CompanyConfig], session: requests.Session, workers: int = 6) -> FetchReport:
    report = FetchReport()
    enabled = [c for c in companies if c.enabled]

    def run(company: CompanyConfig):
        try:
            return company, source_for(company, session).fetch(company), None
        except SourceError as exc:
            return company, [], str(exc)
        except Exception as exc:  # a parser bug in one source must not sink the run
            return company, [], f"{company.source}: unexpected {type(exc).__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for company, postings, error in pool.map(run, enabled):
            if error:
                log.warning("Source failed for %s: %s", company.key, error)
                report.failed[company.key] = error
            else:
                log.info("Fetched %d postings from %s (%s)", len(postings), company.name, company.source)
                report.ok[company.key] = len(postings)
                report.postings.extend(postings)

    # The same posting can appear twice inside one board's response; keep the first.
    seen: set[str] = set()
    unique = []
    for p in report.postings:
        if p.uid not in seen:
            seen.add(p.uid)
            unique.append(p)
    report.postings = unique
    return report
