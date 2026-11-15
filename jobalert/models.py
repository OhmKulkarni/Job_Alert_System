"""Core data models shared across the pipeline."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Posting(BaseModel):
    """One job posting, normalized from any job-board source."""

    uid: str  # "<source>:<company_key>:<native id>" - stable across runs
    source: str  # greenhouse | lever | ashby | smartrecruiters | workday | eightfold
    company_key: str  # the watchlist key this posting came from
    company: str
    title: str
    locations: list[str] = Field(default_factory=list)
    url: str
    posted_at: Optional[datetime] = None
    description: Optional[str] = None  # plain text; some sources fill it lazily
    detail_ref: Optional[str] = None  # source-specific handle for a lazy detail fetch

    @property
    def location_text(self) -> str:
        return " | ".join(self.locations) if self.locations else "Location not listed"


class Decision(str, Enum):
    SHORTLIST = "shortlist"  # every rule passed: send to the agent
    MAYBE = "maybe"  # a rule could not decide: let the agent judge
    REJECT = "reject"  # a rule ruled it out: never costs an LLM call


class FilterResult(BaseModel):
    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    region: Optional[str] = None
    prescore: float = 0.0  # deterministic priority used to order agent work


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AIForward(str, Enum):
    YES = "yes"
    NO = "no"
    UNCLEAR = "unclear"


class Assessment(BaseModel):
    """What the agent must return for each posting. Validated, never trusted blindly."""

    fit_score: int = Field(ge=0, le=100, description="0-100 fit between the candidate and this role")
    recommended_resume: str = Field(description="Key of the resume variant to send")
    confidence: Confidence
    ai_forward: AIForward = Field(
        description="Does the role encourage building with or using AI tools rather than raw coding?"
    )
    reasons: list[str] = Field(min_length=1, max_length=4, description="Why it fits, one short line each")
    gaps: list[str] = Field(default_factory=list, max_length=3, description="Requirements the candidate may miss")
    evidence: list[str] = Field(
        default_factory=list,
        max_length=4,
        description="Short phrases copied word-for-word from the posting that support the score",
    )


class AssessmentRecord(BaseModel):
    """An assessment plus the guardrail verdicts added after validation."""

    uid: str
    model: str
    assessment: Optional[Assessment] = None
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    steps: int = 0
    tool_calls: list[str] = Field(default_factory=list)
