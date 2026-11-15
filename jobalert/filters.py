"""Deterministic first pass. Cheap, explainable rules decide most postings.

Every rule returns pass, reject, or "can't tell". Only postings that survive
the rules reach the LLM agent, and "can't tell" is passed along as context.
"""
from __future__ import annotations

import re

from .config import FilterConfig, Profile
from .models import Decision, FilterResult, Posting
from .text import normalize

_YEAR = re.compile(r"\b(20\d\d)\b")


def _has_any(text: str, terms: list[str]) -> list[str]:
    """Return the terms that appear in `text` as whole words/phrases."""
    hits = []
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text):
            hits.append(term)
    return hits


class RuleFilter:
    def __init__(self, cfg: FilterConfig, profile: Profile | None = None):
        self.cfg = cfg
        self.title_patterns = [re.compile(p, re.IGNORECASE) for p in cfg.title_must_match]
        self.connected = {c.company_key for c in profile.connections} if profile else set()

    # Each check returns (verdict, reason) where verdict is True / False / None (unsure).
    def check_internship(self, title: str):
        if any(p.search(title) for p in self.title_patterns):
            return True, "internship title"
        return False, "not an internship title"

    def check_season(self, title: str, description: str):
        t = normalize(title)
        bad = _has_any(t, self.cfg.reject_season_terms)
        if bad:
            return False, f"wrong season: '{bad[0]}'"
        years = {int(y) for y in _YEAR.findall(t)}
        if years & set(self.cfg.reject_years) and not years - set(self.cfg.reject_years):
            return False, f"wrong year in title: {sorted(years)[0]}"
        if _has_any(t, self.cfg.target_terms):
            return True, "target season in title"
        d = normalize(description)
        if _has_any(d, self.cfg.reject_season_terms) and not _has_any(d, self.cfg.target_terms):
            return False, "description names a different season"
        if _has_any(d, self.cfg.target_terms):
            return True, "target season in description"
        return None, "season not stated"

    def check_degree(self, title: str):
        t = normalize(title)
        level = self.cfg.degree_level
        phd = bool(re.search(r"\bph\.?d\b", t))
        masters = bool(re.search(r"\b(ms|m\.s\.|master'?s?|masters)\b", t))
        undergrad = bool(re.search(r"\b(undergrad(uate)?|bachelor'?s?|bs only|high school)\b", t))
        mba_only = bool(re.search(r"\bmba\b", t)) and not masters
        if phd and not masters and level != "phd":
            return False, "PhD-only title"
        if undergrad and not masters and level != "bachelors":
            return False, "undergraduate-only title"
        if mba_only:
            return False, "MBA-only title"
        if masters:
            return True, "master's students named in title"
        return None, "degree level not stated"

    def check_role(self, title: str):
        t = normalize(title)
        bad = _has_any(t, self.cfg.reject_role_terms)
        good = _has_any(t, self.cfg.strong_role_terms)
        if good and bad:
            return None, f"mixed role signals: '{good[0]}' but '{bad[0]}'"
        if good:
            return True, f"target role: '{good[0]}'"
        if bad:
            return False, f"off-target role: '{bad[0]}'"
        maybe = _has_any(t, self.cfg.maybe_role_terms)
        if maybe:
            return None, f"adjacent role: '{maybe[0]}'"
        if self.cfg.unknown_role == "maybe":
            return None, "role family unclear"
        return False, "role not in target families"

    def check_location(self, locations: list[str]):
        best = None
        for loc in locations:
            text = normalize(loc)
            for region in self.cfg.regions:
                if _has_any(text, region.places) and (best is None or region.priority > best.priority):
                    best = region
        if best:
            return True, best
        if self.cfg.accept_remote_us and any(
            "remote" in normalize(loc) and re.search(r"\b(us|usa|united states|u\.s\.)\b", normalize(loc))
            for loc in locations
        ):
            return True, None
        if not locations:
            return None, None
        return False, None

    def evaluate(self, posting: Posting) -> FilterResult:
        reasons: list[str] = []
        unsure = False
        score = 0.0

        ok, why = self.check_internship(posting.title)
        if not ok:
            return FilterResult(decision=Decision.REJECT, reasons=[why])

        ok, why = self.check_role(posting.title)
        if ok is False:
            return FilterResult(decision=Decision.REJECT, reasons=[why])
        reasons.append(why)
        unsure |= ok is None
        score += 3 if ok else 1

        ok, region = self.check_location(posting.locations)
        if ok is False:
            return FilterResult(
                decision=Decision.REJECT, reasons=[f"outside target regions: {posting.location_text}"]
            )
        if ok is None:
            reasons.append("location not listed")
            unsure = True
        elif region:
            reasons.append(f"in {region.name}")
            score += region.priority
        else:
            reasons.append("remote (US)")
            score += 0.5

        ok, why = self.check_season(posting.title, posting.description or "")
        if ok is False:
            return FilterResult(decision=Decision.REJECT, reasons=[why])
        reasons.append(why)
        unsure |= ok is None
        score += 1 if ok else 0

        ok, why = self.check_degree(posting.title)
        if ok is False:
            return FilterResult(decision=Decision.REJECT, reasons=[why])
        reasons.append(why)
        score += 1 if ok else 0

        if posting.company_key in self.connected:
            reasons.append("you have a contact here")
            score += 1.5

        return FilterResult(
            decision=Decision.MAYBE if unsure else Decision.SHORTLIST,
            reasons=reasons,
            region=region.name if region else None,
            prescore=round(score, 2),
        )
