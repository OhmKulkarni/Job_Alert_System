"""The agent loop: investigate with tools, submit, then pass deterministic guardrails.

Guardrails, in order:
1. Step limit per posting and a shared call budget per run.
2. Tool arguments are schema-validated; mistakes go back to the model as errors.
3. If the model never submits, one schema-constrained "finalize" call is made.
4. Evidence quotes must appear in the posting text, or they are dropped.
5. Low confidence, borderline or near-zero scores, or ungrounded evidence -> flagged for human review.
"""
from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from ..config import AgentConfig, Profile
from ..llm import BudgetExceeded, ChatModel, LLMError
from ..models import Assessment, AssessmentRecord, Confidence, FilterResult, Posting
from ..store import Store
from . import prompts
from .tools import Toolbox, ToolError

log = logging.getLogger("jobalert.agent")


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def ground_evidence(evidence: list[str], description: str) -> tuple[list[str], list[str]]:
    """Split evidence into (found in posting, not found). Ignores case and punctuation."""
    haystack = _squash(description)
    found, missing = [], []
    for quote in evidence:
        needle = _squash(quote)
        (found if needle and needle in haystack else missing).append(quote)
    return found, missing


class JobAgent:
    def __init__(self, model: ChatModel, profile: Profile, cfg: AgentConfig, store: Store | None = None):
        self.model = model
        self.profile = profile
        self.cfg = cfg
        self.store = store

    def assess(self, posting: Posting, filter_result: FilterResult | None = None) -> AssessmentRecord:
        """Run one agent episode. Raises BudgetExceeded if the run's budget is gone."""
        box = Toolbox(posting, self.profile, self.store, self.cfg.description_page_chars)
        tools = box.specs()
        excerpt = (posting.description or "(no description available)")[:600]
        messages = [
            {"role": "system", "content": prompts.SYSTEM},
            {
                "role": "user",
                "content": prompts.TASK.format(
                    company=posting.company,
                    title=posting.title,
                    locations=posting.location_text,
                    url=posting.url,
                    filter_notes="; ".join(filter_result.reasons) if filter_result else "none",
                    pages=len(box.pages),
                    excerpt=excerpt,
                ),
            },
        ]
        record = AssessmentRecord(uid=posting.uid, model=self.model.model)

        for step in range(1, self.cfg.max_steps_per_posting + 1):
            record.steps = step
            try:
                response = self.model.chat(messages, tools=tools)
            except LLMError as exc:
                record.needs_review = True
                record.review_reasons.append(f"model error: {exc}")
                return record

            if not response.tool_calls:
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": prompts.NUDGE})
                continue

            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": [
                        {"function": {"name": c.name, "arguments": c.arguments}} for c in response.tool_calls
                    ],
                }
            )
            for call in response.tool_calls:
                record.tool_calls.append(call.name)
                try:
                    result = box.call(call.name, call.arguments)
                except ToolError as exc:
                    result = f"ERROR: {exc}"
                    log.debug("Tool error on %s: %s", posting.uid, exc)
                messages.append({"role": "tool", "content": result, "tool_name": call.name})
            if box.submitted:
                break

        if box.submitted is None:
            box.submitted = self._finalize(box, messages, record)
        if box.submitted is None:
            record.needs_review = True
            record.review_reasons.append("agent could not produce a valid assessment")
            return record

        return self._apply_guardrails(box.submitted, posting, record)

    def _finalize(self, box: Toolbox, messages: list[dict], record: AssessmentRecord) -> Assessment | None:
        """One schema-constrained call when the agent ran out of steps without submitting."""
        record.tool_calls.append("finalize")
        ask = prompts.FINALIZE.format(resume_keys=", ".join(self.profile.resume_keys()))
        try:
            response = self.model.chat(messages + [{"role": "user", "content": ask}], schema=box.assessment_schema())
        except LLMError as exc:
            record.review_reasons.append(f"model error on finalize: {exc}")
            return None
        try:
            return box.check_assessment(Assessment.model_validate(json.loads(response.content)))
        except (json.JSONDecodeError, ValidationError, ToolError) as exc:
            record.review_reasons.append(f"finalize output invalid: {str(exc).splitlines()[0]}")
            return None

    def _apply_guardrails(self, a: Assessment, posting: Posting, record: AssessmentRecord) -> AssessmentRecord:
        found, missing = ground_evidence(a.evidence, posting.description or "")
        if missing:
            record.review_reasons.append(f"{len(missing)} evidence quote(s) not found in the posting")
        a = a.model_copy(update={"evidence": found})
        if not found:
            record.review_reasons.append("no grounded evidence")
        if a.confidence == Confidence.LOW:
            record.review_reasons.append("agent confidence is low")
        if a.fit_score <= 10:
            # Small models sometimes answer on a 0-10 scale; a score this low needs a human look.
            record.review_reasons.append(f"very low score ({a.fit_score}); check it was on the 0-100 scale")
        lo, hi = self.cfg.review_if_score_between
        if lo <= a.fit_score <= hi:
            record.review_reasons.append(f"borderline score ({a.fit_score})")
        record.assessment = a
        record.needs_review = bool(record.review_reasons)
        return record


def draft_outreach(model: ChatModel, posting: Posting, assessment: Assessment, contact: str, profile: Profile) -> str | None:
    """Draft (never send) an informal note to a friend at the company."""
    schema = {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}
    messages = [
        {"role": "system", "content": prompts.OUTREACH_SYSTEM},
        {
            "role": "user",
            "content": prompts.OUTREACH_TASK.format(
                contact=contact,
                company=posting.company,
                title=posting.title,
                url=posting.url,
                reasons="; ".join(assessment.reasons),
                first_name=profile.name.split()[0],
            ),
        },
    ]
    try:
        response = model.chat(messages, schema=schema)
        message = json.loads(response.content).get("message", "").strip()
    except (LLMError, json.JSONDecodeError, AttributeError):
        return None
    if not message:
        return None
    # Guardrail: the only link allowed is the job link itself.
    message = re.sub(r"https?://\S+", lambda m: m.group(0) if m.group(0).rstrip(".,)") == posting.url else "", message)
    return message[:900]


__all__ = ["JobAgent", "draft_outreach", "ground_evidence", "BudgetExceeded"]
