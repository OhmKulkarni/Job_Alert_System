"""Typed configuration loaded from the YAML files in config/."""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

SourceName = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "eightfold"]


class CompanyConfig(BaseModel):
    """One company on the watchlist and where its job board lives."""

    key: str  # short id used in posting uids, e.g. "doordash"
    name: str
    source: SourceName
    slug: str  # board token / company id / tenant, depending on the source
    # Workday and Eightfold need a little more than a slug:
    host: Optional[str] = None  # e.g. broadcom.wd1.myworkdayjobs.com or paypal.eightfold.ai
    site: Optional[str] = None  # Workday site name, e.g. External_Career
    search_text: Optional[str] = None  # server-side search for big boards (Workday/Eightfold)
    enabled: bool = True

    @model_validator(mode="after")
    def _check_source_fields(self) -> "CompanyConfig":
        if self.source == "workday" and not (self.host and self.site):
            raise ValueError(f"{self.key}: workday companies need 'host' and 'site'")
        if self.source == "eightfold" and not self.host:
            raise ValueError(f"{self.key}: eightfold companies need 'host'")
        return self


class Region(BaseModel):
    name: str
    priority: float = 1.0  # higher = preferred
    places: list[str]  # city/area names matched as whole words


class FilterConfig(BaseModel):
    title_must_match: list[str] = Field(default_factory=lambda: [r"\bintern\b", r"\binternship\b"])
    target_terms: list[str] = Field(default_factory=lambda: ["summer 2027", "2027"])
    reject_season_terms: list[str] = Field(default_factory=list)
    reject_years: list[int] = Field(default_factory=lambda: [2025, 2026, 2028])
    strong_role_terms: list[str] = Field(default_factory=list)
    maybe_role_terms: list[str] = Field(default_factory=list)
    reject_role_terms: list[str] = Field(default_factory=list)
    unknown_role: Literal["maybe", "reject"] = "reject"
    regions: list[Region] = Field(default_factory=list)
    accept_remote_us: bool = True
    degree_level: Literal["bachelors", "masters", "phd"] = "masters"


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    temperature: float = 0.2
    num_ctx: int = 8192
    timeout: int = 180


class AgentConfig(BaseModel):
    max_steps_per_posting: int = 6
    max_llm_calls_per_run: int = 120
    max_postings_per_run: int = 25
    description_page_chars: int = 2500
    review_if_score_between: tuple[int, int] = (55, 70)
    outreach_min_score: int = 75


class EmailConfig(BaseModel):
    send_only_if_new: bool = True
    subject_prefix: str = "Job Alert"


class Settings(BaseModel):
    database: str = "data/jobs.db"
    output_dir: str = "out"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    filters: FilterConfig = Field(default_factory=FilterConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class ResumeVariant(BaseModel):
    key: str
    label: str
    use_for: str  # when this resume is the right one


class Connection(BaseModel):
    company_key: str
    name: str
    relationship: str = "friend"


class Profile(BaseModel):
    """Who the agent is matching jobs for. Keep the real file out of git."""

    name: str
    summary: str
    degree: str
    strengths: list[str]
    preferences: list[str] = Field(default_factory=list)
    resumes: list[ResumeVariant] = Field(min_length=1)
    connections: list[Connection] = Field(default_factory=list)

    def resume_keys(self) -> list[str]:
        return [r.key for r in self.resumes]

    def connection_for(self, company_key: str) -> Optional[Connection]:
        return next((c for c in self.connections if c.company_key == company_key), None)


class AppConfig(BaseModel):
    settings: Settings
    watchlist: list[CompanyConfig]
    profile: Profile


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(config_dir: str | Path = "config") -> AppConfig:
    """Load settings, watchlist and profile. Falls back to profile.example.yaml."""
    config_dir = Path(config_dir)
    settings = Settings.model_validate(_load_yaml(config_dir / "settings.yaml"))
    watchlist_raw = _load_yaml(config_dir / "watchlist.yaml").get("companies", [])
    watchlist = [CompanyConfig.model_validate(c) for c in watchlist_raw]
    keys = [c.key for c in watchlist]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise ValueError(f"Duplicate watchlist keys: {sorted(duplicates)}")

    profile_path = config_dir / "profile.yaml"
    if not profile_path.exists():
        profile_path = config_dir / "profile.example.yaml"
    profile = Profile.model_validate(_load_yaml(profile_path))
    return AppConfig(settings=settings, watchlist=watchlist, profile=profile)
