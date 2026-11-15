"""Shared plumbing for job-board sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import requests

from ..config import CompanyConfig
from ..http import DEFAULT_TIMEOUT
from ..models import Posting


class SourceError(RuntimeError):
    """A source could not be fetched. The run continues without it."""


class Source(ABC):
    name: str = ""

    def __init__(self, session: requests.Session):
        self.session = session

    @abstractmethod
    def fetch(self, company: CompanyConfig) -> list[Posting]:
        """Return every open posting on this company's board."""

    def fetch_description(self, posting: Posting, company: CompanyConfig) -> str:
        """Fetch the full description for sources that list without one."""
        return posting.description or ""

    # -- helpers ---------------------------------------------------------
    def _get_json(self, url: str, **kwargs):
        try:
            resp = self.session.get(url, timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise SourceError(f"{self.name}: request failed for {url}: {exc}") from exc
        if resp.status_code != 200:
            raise SourceError(f"{self.name}: HTTP {resp.status_code} for {url}")
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"{self.name}: invalid JSON from {url}") from exc

    def _post_json(self, url: str, payload: dict, **kwargs):
        try:
            resp = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException as exc:
            raise SourceError(f"{self.name}: request failed for {url}: {exc}") from exc
        if resp.status_code != 200:
            raise SourceError(f"{self.name}: HTTP {resp.status_code} for {url}")
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceError(f"{self.name}: invalid JSON from {url}") from exc

    @staticmethod
    def uid(company: CompanyConfig, native_id) -> str:
        return f"{company.source}:{company.key}:{native_id}"


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def from_epoch(value, millis: bool = False) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        seconds = float(value) / (1000 if millis else 1)
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None
