"""One run: fetch -> remember -> filter -> agent -> digest -> notify."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .agent import JobAgent, draft_outreach
from .config import AppConfig
from .digest import DigestData, render_html, render_text, subject
from .filters import RuleFilter
from .llm import BudgetedModel, BudgetExceeded, CallBudget, ChatModel, OllamaClient
from .models import Decision, FilterResult
from .notify import email_configured, send_email
from .sources import SourceError, fetch_all, source_for
from .store import Store

log = logging.getLogger("jobalert.pipeline")


@dataclass
class RunOptions:
    dry_run: bool = False  # write the digest to out/ instead of emailing; don't mark as notified
    use_llm: bool = True
    only_company: Optional[str] = None
    max_postings: Optional[int] = None


@dataclass
class RunResult:
    stats: dict = field(default_factory=dict)
    digest_path: Optional[Path] = None
    sent: bool = False


def run(
    config: AppConfig,
    store: Store,
    options: RunOptions,
    session: Optional[requests.Session] = None,
    model: Optional[ChatModel] = None,
) -> RunResult:
    from .http import make_session

    session = session or make_session()
    settings = config.settings
    companies = [c for c in config.watchlist if not options.only_company or c.key == options.only_company]
    by_key = {c.key: c for c in companies}
    last_run = store.last_finished_run_start()
    run_id = store.start_run()
    stats: dict = {}
    notes: list[str] = []

    # 1. Fetch every board. A failing board is reported, never fatal.
    report = fetch_all(companies, session)
    changes = store.sync(report.postings, report.ok.keys())
    stats.update(
        fetched=len(report.postings),
        new=len(changes["new"]),
        closed=len(changes["closed"]),
        failed_sources=len(report.failed),
    )

    # 2. Deterministic rules on everything not yet judged.
    rules = RuleFilter(settings.filters, config.profile)
    counts = {d.value: 0 for d in Decision}
    for row in store.unfiltered_open():
        result = rules.evaluate(store.to_posting(row))
        store.save_filter(row["uid"], result)
        counts[result.decision.value] += 1
    stats["filtered"] = counts

    # 3. Agent pass over survivors, best first, within budget.
    assessed = 0
    if options.use_llm:
        if model is None:
            client = OllamaClient(settings.ollama)
            healthy, why = client.health()
            if not healthy:
                notes.append(f"AI assessment skipped: {why}")
                log.warning(why)
                client = None
            model = client
        if model is not None:
            assessed = _assess(config, store, by_key, session, model, options, notes)
    else:
        notes.append("AI assessment skipped (--no-llm).")
    stats["assessed"] = assessed

    # 4. Digest.
    rows = store.digest_rows()
    data = DigestData(
        matches=[r for r in rows if not r["needs_review"]],
        review=[r for r in rows if r["needs_review"]],
        pending=store.pending_rows(since=last_run),
        closed=store.closed_since(last_run),
        failed_sources=report.failed,
        notes=notes,
    )
    html_body = render_html(data, config.profile)
    text_body = render_text(data, config.profile)
    subj = subject(data, settings.email.subject_prefix)

    out_dir = Path(settings.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest_path = out_dir / "digest.html"
    digest_path.write_text(html_body, encoding="utf-8")
    result = RunResult(stats=stats, digest_path=digest_path)

    nothing_new = not (data.matches or data.review or data.closed or data.pending)
    if options.dry_run:
        log.info("Dry run: digest written to %s", digest_path)
    elif nothing_new and settings.email.send_only_if_new:
        log.info("Nothing new; no email sent")
    else:
        ok, missing = email_configured()
        if not ok:
            log.warning("Email not configured (missing %s); digest saved to %s", ", ".join(missing), digest_path)
        else:
            send_email(subj, html_body, text_body)
            result.sent = True
            store.mark_notified([r["uid"] for r in rows])

    stats["sent"] = result.sent
    store.finish_run(run_id, stats)
    return result


def _assess(config, store, by_key, session, model, options, notes) -> int:
    settings = config.settings
    budget = CallBudget(settings.agent.max_llm_calls_per_run)
    budgeted = BudgetedModel(model, budget)
    agent = JobAgent(budgeted, config.profile, settings.agent, store)
    limit = options.max_postings or settings.agent.max_postings_per_run
    queue = [r for r in store.awaiting_assessment() if r["company_key"] in by_key][:limit]
    done = 0
    for row in queue:
        posting = store.to_posting(row)
        company = by_key[posting.company_key]
        if not posting.description:
            try:
                posting.description = source_for(company, session).fetch_description(posting, company)
                store.set_description(posting.uid, posting.description)
            except SourceError as exc:
                log.warning("Could not fetch description for %s: %s", posting.uid, exc)
        filter_result = FilterResult(
            decision=Decision(row["filter_decision"]),
            reasons=json.loads(row["filter_reasons"] or "[]"),
        )
        try:
            record = agent.assess(posting, filter_result)
            store.save_assessment(record)
            done += 1
            log.info(
                "Assessed %s: %s (review=%s)",
                posting.title,
                record.assessment.fit_score if record.assessment else "n/a",
                record.needs_review,
            )
            contact = config.profile.connection_for(posting.company_key)
            a = record.assessment
            if contact and a and not record.needs_review and a.fit_score >= settings.agent.outreach_min_score:
                draft = draft_outreach(budgeted, posting, a, contact.name, config.profile)
                if draft:
                    store.save_outreach(posting.uid, contact.name, draft)
        except BudgetExceeded:
            notes.append(
                f"Agent budget of {budget.limit} model calls reached; the rest will be assessed next run."
            )
            break
    return done
