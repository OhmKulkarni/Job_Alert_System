"""The agent's tools. Every argument is validated before anything runs."""
from __future__ import annotations

import json
import re
from typing import Callable

from pydantic import BaseModel, Field, ValidationError

from ..config import Profile
from ..models import Assessment, Posting
from ..store import Store


class ToolError(Exception):
    """Returned to the model as text so it can correct itself."""


class ReadPostingArgs(BaseModel):
    page: int = Field(default=1, ge=1, description="Page number, starting at 1")


class SearchPostingArgs(BaseModel):
    terms: list[str] = Field(min_length=1, max_length=6, description="Words or phrases to look for")


class NoArgs(BaseModel):
    pass


def paginate(text: str, page_chars: int) -> list[str]:
    """Split on paragraph boundaries into pages of roughly page_chars."""
    if not text:
        return [""]
    pages, current = [], ""
    for para in text.split("\n"):
        if current and len(current) + len(para) + 1 > page_chars:
            pages.append(current)
            current = ""
        while len(para) > page_chars:  # a single giant paragraph
            pages.append(para[:page_chars])
            para = para[page_chars:]
        current = f"{current}\n{para}" if current else para
    if current:
        pages.append(current)
    return pages or [""]


def inline_refs(schema: dict) -> dict:
    """Replace $ref pointers with their definitions. Small models handle flat schemas better."""
    defs = schema.get("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(dict(defs[node["$ref"].rsplit("/", 1)[-1]]))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if p.strip(" -•\t")]


class Toolbox:
    """Tools bound to one posting. `submit_assessment` ends the episode."""

    def __init__(self, posting: Posting, profile: Profile, store: Store | None, page_chars: int):
        self.posting = posting
        self.profile = profile
        self.store = store
        self.pages = paginate(posting.description or "", page_chars)
        self.submitted: Assessment | None = None
        self._handlers: dict[str, tuple[type[BaseModel], Callable]] = {
            "read_posting": (ReadPostingArgs, self.read_posting),
            "search_posting": (SearchPostingArgs, self.search_posting),
            "get_profile": (NoArgs, self.get_profile),
            "company_history": (NoArgs, self.company_history),
            "submit_assessment": (Assessment, self.submit_assessment),
        }

    # -- schemas -------------------------------------------------------------
    def check_assessment(self, assessment: Assessment) -> Assessment:
        keys = self.profile.resume_keys()
        if assessment.recommended_resume not in keys:
            raise ToolError(f"recommended_resume must be one of {keys}, got '{assessment.recommended_resume}'")
        return assessment

    def assessment_schema(self) -> dict:
        schema = inline_refs(Assessment.model_json_schema())
        schema["properties"]["recommended_resume"]["enum"] = self.profile.resume_keys()
        return schema

    def specs(self) -> list[dict]:
        """Tool definitions in the function-calling format Ollama expects."""

        def spec(name: str, description: str, params: dict) -> dict:
            return {"type": "function", "function": {"name": name, "description": description, "parameters": params}}

        def params(model: type[BaseModel]) -> dict:
            schema = model.model_json_schema()
            return {"type": "object", "properties": schema.get("properties", {}), "required": schema.get("required", [])}

        return [
            spec("read_posting", f"Read one page of the job description ({len(self.pages)} pages).", params(ReadPostingArgs)),
            spec("search_posting", "Find sentences in the job description that mention any of the terms.", params(SearchPostingArgs)),
            spec("get_profile", "Get the candidate's background, preferences and resume versions.", params(NoArgs)),
            spec("company_history", "See other relevant roles already seen at this company.", params(NoArgs)),
            spec("submit_assessment", "Submit the final assessment. Call exactly once.", {
                "type": "object",
                "properties": self.assessment_schema()["properties"],
                "required": self.assessment_schema().get("required", []),
            }),
        ]

    # -- dispatch ----------------------------------------------------------
    def call(self, name: str, arguments: dict) -> str:
        if name not in self._handlers:
            raise ToolError(f"Unknown tool '{name}'. Available: {', '.join(self._handlers)}")
        if "__unparseable__" in arguments:
            raise ToolError(f"Arguments for {name} were not valid JSON.")
        model, handler = self._handlers[name]
        try:
            args = model.model_validate(arguments)
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors())
            raise ToolError(f"Invalid arguments for {name}: {problems}") from exc
        return handler(args)

    # -- tools ---------------------------------------------------------------
    def read_posting(self, args: ReadPostingArgs) -> str:
        if args.page > len(self.pages):
            raise ToolError(f"There are only {len(self.pages)} page(s).")
        return f"Page {args.page} of {len(self.pages)}:\n{self.pages[args.page - 1]}"

    def search_posting(self, args: SearchPostingArgs) -> str:
        terms = [t.lower() for t in args.terms if t.strip()]
        hits = [s for s in _sentences(self.posting.description or "") if any(t in s.lower() for t in terms)]
        if not hits:
            return f"No sentences mention: {', '.join(args.terms)}"
        return "\n".join(f"- {s}" for s in hits[:8])

    def get_profile(self, args: NoArgs) -> str:
        p = self.profile
        return json.dumps(
            {
                "summary": p.summary,
                "degree": p.degree,
                "strengths": p.strengths,
                "preferences": p.preferences,
                "resumes": [{"key": r.key, "label": r.label, "use_for": r.use_for} for r in p.resumes],
            },
            indent=1,
        )

    def company_history(self, args: NoArgs) -> str:
        if self.store is None:
            return "No history available."
        rows = [r for r in self.store.company_history(self.posting.company_key) if r["title"] != self.posting.title]
        if not rows:
            return f"No other relevant roles seen at {self.posting.company} yet."
        lines = [
            f"- {r['title']} ({r['status']}, you: {r['user_status']}, fit: {r['fit_score'] if r['fit_score'] is not None else 'n/a'})"
            for r in rows
        ]
        return "Other roles at this company:\n" + "\n".join(lines)

    def submit_assessment(self, args: Assessment) -> str:
        self.submitted = self.check_assessment(args)
        return "Assessment recorded."
