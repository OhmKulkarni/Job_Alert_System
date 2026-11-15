"""Render the digest email. Every value from the web is HTML-escaped."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from html import escape

from .config import Profile


@dataclass
class DigestData:
    matches: list[sqlite3.Row] = field(default_factory=list)  # assessed, no review needed
    review: list[sqlite3.Row] = field(default_factory=list)  # assessed, flagged by guardrails
    pending: list[sqlite3.Row] = field(default_factory=list)  # passed rules, not assessed yet
    closed: list[sqlite3.Row] = field(default_factory=list)
    failed_sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.matches or self.review or self.pending or self.closed)


def _list(raw) -> list[str]:
    try:
        return json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []


def _resume_label(profile: Profile, key: str | None) -> str:
    for r in profile.resumes:
        if r.key == key:
            return r.label
    return key or "n/a"


def _color(score) -> str:
    if score is None:
        return "#6B7280"
    return "#047857" if score >= 75 else "#B45309" if score >= 55 else "#6B7280"


def _card(row: sqlite3.Row, profile: Profile, show_review: bool) -> str:
    score = row["fit_score"]
    locations = ", ".join(_list(row["locations"])) or "Location not listed"
    reasons = "".join(f"<li>{escape(r)}</li>" for r in _list(row["reasons"]))
    gaps = "".join(f"<li>{escape(g)}</li>" for g in _list(row["gaps"]))
    evidence = "".join(f"<li><em>&ldquo;{escape(e)}&rdquo;</em></li>" for e in _list(row["evidence"]))
    ai = {"yes": "AI-forward", "no": "Not AI-focused", "unclear": "AI use unclear"}.get(row["ai_forward"] or "", "")
    review = ""
    if show_review:
        review = "".join(f"<li>{escape(r)}</li>" for r in _list(row["review_reasons"]))
        review = f'<p style="margin:8px 0 0;color:#B45309;font-size:13px"><b>Check:</b></p><ul style="margin:4px 0;color:#B45309;font-size:13px">{review}</ul>'
    outreach = ""
    if row["draft"]:
        outreach = (
            f'<div style="margin-top:10px;padding:10px;background:#F3F4F6;border-radius:6px;font-size:13px">'
            f"<b>Draft note to {escape(row['contact'] or '')}</b> (not sent)<br>"
            f'<span style="white-space:pre-wrap">{escape(row["draft"])}</span></div>'
        )
    return f"""
<div style="border:1px solid #E5E7EB;border-left:4px solid {_color(score)};border-radius:8px;padding:14px 16px;margin:0 0 14px">
  <div style="font-size:16px;font-weight:600;color:#111827">{escape(row['title'])}</div>
  <div style="font-size:13px;color:#4B5563;margin:2px 0 8px">{escape(row['company'])} &middot; {escape(locations)}</div>
  <div style="font-size:13px;color:#111827">
    <b style="color:{_color(score)}">Fit {score if score is not None else '?'}/100</b>
    &middot; Send: <b>{escape(_resume_label(profile, row['recommended_resume']))}</b>
    &middot; {escape(ai)} &middot; confidence {escape(row['confidence'] or 'n/a')}
  </div>
  {f'<ul style="margin:8px 0 0;font-size:13px;color:#374151">{reasons}</ul>' if reasons else ''}
  {f'<p style="margin:6px 0 0;font-size:13px;color:#374151"><b>Gaps:</b></p><ul style="margin:2px 0;font-size:13px;color:#374151">{gaps}</ul>' if gaps else ''}
  {f'<ul style="margin:6px 0 0;font-size:12px;color:#6B7280">{evidence}</ul>' if evidence else ''}
  {review}
  {outreach}
  <p style="margin:10px 0 0"><a href="{escape(row['url'], quote=True)}" style="color:#1D4ED8;font-size:13px">Open posting &rarr;</a>
  <span style="color:#9CA3AF;font-size:11px"> &middot; id {escape(row['uid'])}</span></p>
</div>"""


def _simple(row: sqlite3.Row) -> str:
    locations = ", ".join(_list(row["locations"])) or "Location not listed"
    return (
        f'<li style="margin:0 0 6px;font-size:13px"><a href="{escape(row["url"], quote=True)}" style="color:#1D4ED8">'
        f"{escape(row['title'])}</a> &middot; {escape(row['company'])} &middot; {escape(locations)}</li>"
    )


def _section(title: str, body: str) -> str:
    return f'<h2 style="font-size:17px;color:#111827;margin:24px 0 10px">{escape(title)}</h2>{body}'


def render_html(data: DigestData, profile: Profile) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    parts = [
        f'<p style="font-size:14px;color:#374151">Hi {escape(profile.name.split()[0])}, here is what changed since the last run.</p>'
    ]
    if data.matches:
        parts.append(_section(f"Matches ({len(data.matches)})", "".join(_card(r, profile, False) for r in data.matches)))
    if data.review:
        parts.append(_section(f"Worth a second look ({len(data.review)})", "".join(_card(r, profile, True) for r in data.review)))
    if data.pending:
        parts.append(_section(
            f"Passed the filters, not assessed yet ({len(data.pending)})",
            "<ul style='padding-left:18px'>" + "".join(_simple(r) for r in data.pending) + "</ul>",
        ))
    if data.closed:
        parts.append(_section(
            f"Closed since last run ({len(data.closed)})",
            "<ul style='padding-left:18px'>" + "".join(_simple(r) for r in data.closed) + "</ul>",
        ))
    footer = list(data.notes)
    footer += [f"Could not reach {k}: {v}" for k, v in data.failed_sources.items()]
    if footer:
        parts.append(
            '<p style="font-size:12px;color:#6B7280;margin-top:24px">'
            + "<br>".join(escape(n) for n in footer)
            + "</p>"
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Alert {escape(today)}</title></head>
<body style="margin:0;background:#F9FAFB;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;background:#FFFFFF">
<h1 style="font-size:20px;color:#111827;margin:0">Job Alert &middot; {escape(today)}</h1>
{''.join(parts)}
</div></body></html>"""


def render_text(data: DigestData, profile: Profile) -> str:
    lines = [f"Job Alert - {datetime.now():%B %d, %Y}", ""]

    def block(title, rows, detail):
        if not rows:
            return
        lines.append(f"== {title} ({len(rows)}) ==")
        for r in rows:
            if detail:
                lines.append(
                    f"* [{r['fit_score']}/100] {r['title']} - {r['company']} | send: "
                    f"{_resume_label(profile, r['recommended_resume'])}"
                )
                for reason in _list(r["reasons"]):
                    lines.append(f"    - {reason}")
            else:
                lines.append(f"* {r['title']} - {r['company']}")
            lines.append(f"    {r['url']}")
        lines.append("")

    block("Matches", data.matches, True)
    block("Worth a second look", data.review, True)
    block("Passed the filters, not assessed yet", data.pending, False)
    block("Closed since last run", data.closed, False)
    lines += data.notes
    lines += [f"Could not reach {k}: {v}" for k, v in data.failed_sources.items()]
    return "\n".join(lines).strip() + "\n"


def subject(data: DigestData, prefix: str) -> str:
    bits = []
    if data.matches:
        bits.append(f"{len(data.matches)} match{'es' if len(data.matches) != 1 else ''}")
    if data.review:
        bits.append(f"{len(data.review)} to review")
    if data.closed:
        bits.append(f"{len(data.closed)} closed")
    if not bits and data.pending:
        bits.append(f"{len(data.pending)} new")
    return f"{prefix}: {', '.join(bits) or 'no changes'} ({datetime.now():%b %d})"
