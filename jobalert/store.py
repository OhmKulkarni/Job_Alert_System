"""SQLite memory: what was seen, when, what the agent thought, what you did."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .models import AssessmentRecord, FilterResult, Posting

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    uid TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    company_key TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    locations TEXT NOT NULL,
    url TEXT NOT NULL,
    posted_at TEXT,
    description TEXT,
    detail_ref TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',          -- open | closed
    closed_at TEXT,
    filter_decision TEXT,
    filter_reasons TEXT,
    region TEXT,
    prescore REAL DEFAULT 0,
    user_status TEXT NOT NULL DEFAULT 'new',      -- new | applied | ignored | saved
    notified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_postings_company ON postings(company_key, status);

CREATE TABLE IF NOT EXISTS assessments (
    uid TEXT PRIMARY KEY REFERENCES postings(uid),
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    fit_score INTEGER,
    recommended_resume TEXT,
    confidence TEXT,
    ai_forward TEXT,
    reasons TEXT,
    gaps TEXT,
    evidence TEXT,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons TEXT,
    steps INTEGER,
    tool_calls TEXT
);

CREATE TABLE IF NOT EXISTS outreach (
    uid TEXT PRIMARY KEY REFERENCES postings(uid),
    contact TEXT NOT NULL,
    draft TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stats TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # -- postings ----------------------------------------------------------
    def sync(self, postings: Iterable[Posting], fetched_companies: Iterable[str]) -> dict[str, list[str]]:
        """Upsert this run's postings and close the ones that disappeared.

        Only companies whose board was fetched successfully can close postings,
        so a source outage never looks like every job closing at once.
        """
        now = _now()
        new, reopened, seen = [], [], set()
        with self.conn:
            for p in postings:
                seen.add(p.uid)
                row = self.conn.execute("SELECT status FROM postings WHERE uid=?", (p.uid,)).fetchone()
                if row is None:
                    self.conn.execute(
                        """INSERT INTO postings (uid, source, company_key, company, title, locations, url,
                               posted_at, description, detail_ref, first_seen, last_seen)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            p.uid, p.source, p.company_key, p.company, p.title, json.dumps(p.locations),
                            p.url, p.posted_at.isoformat() if p.posted_at else None, p.description,
                            p.detail_ref, now, now,
                        ),
                    )
                    new.append(p.uid)
                else:
                    if row["status"] == "closed":
                        reopened.append(p.uid)
                    self.conn.execute(
                        """UPDATE postings SET title=?, locations=?, url=?, last_seen=?, status='open',
                               closed_at=NULL, description=COALESCE(?, description) WHERE uid=?""",
                        (p.title, json.dumps(p.locations), p.url, now, p.description, p.uid),
                    )
            closed = []
            for key in fetched_companies:
                rows = self.conn.execute(
                    "SELECT uid FROM postings WHERE company_key=? AND status='open'", (key,)
                ).fetchall()
                for r in rows:
                    if r["uid"] not in seen:
                        closed.append(r["uid"])
                        self.conn.execute(
                            "UPDATE postings SET status='closed', closed_at=? WHERE uid=?", (now, r["uid"])
                        )
        return {"new": new, "reopened": reopened, "closed": closed}

    def get(self, uid: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM postings WHERE uid=?", (uid,)).fetchone()

    def to_posting(self, row: sqlite3.Row) -> Posting:
        return Posting(
            uid=row["uid"], source=row["source"], company_key=row["company_key"], company=row["company"],
            title=row["title"], locations=json.loads(row["locations"]), url=row["url"],
            posted_at=row["posted_at"], description=row["description"], detail_ref=row["detail_ref"],
        )

    def set_description(self, uid: str, description: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE postings SET description=? WHERE uid=?", (description, uid))

    def save_filter(self, uid: str, result: FilterResult) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE postings SET filter_decision=?, filter_reasons=?, region=?, prescore=? WHERE uid=?",
                (result.decision.value, json.dumps(result.reasons), result.region, result.prescore, uid),
            )

    def unfiltered_open(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM postings WHERE status='open' AND filter_decision IS NULL"
        ).fetchall()

    def awaiting_assessment(self) -> list[sqlite3.Row]:
        """Open postings that passed the rules and have no assessment yet, best first."""
        return self.conn.execute(
            """SELECT p.* FROM postings p LEFT JOIN assessments a ON a.uid = p.uid
               WHERE p.status='open' AND p.filter_decision IN ('shortlist','maybe')
                 AND p.user_status IN ('new','saved') AND a.uid IS NULL
               ORDER BY p.filter_decision='shortlist' DESC, p.prescore DESC, p.first_seen ASC"""
        ).fetchall()

    def company_history(self, company_key: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT p.title, p.status, p.user_status, a.fit_score FROM postings p
               LEFT JOIN assessments a ON a.uid = p.uid
               WHERE p.company_key=? AND p.filter_decision IN ('shortlist','maybe')
               ORDER BY p.first_seen DESC LIMIT 15""",
            (company_key,),
        ).fetchall()

    def set_user_status(self, uid: str, status: str) -> bool:
        if status not in {"new", "applied", "ignored", "saved"}:
            raise ValueError(f"unknown status {status!r}")
        with self.conn:
            cur = self.conn.execute("UPDATE postings SET user_status=? WHERE uid=?", (status, uid))
        return cur.rowcount == 1

    # -- assessments & outreach ------------------------------------------
    def save_assessment(self, rec: AssessmentRecord) -> None:
        a = rec.assessment
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO assessments (uid, created_at, model, fit_score, recommended_resume,
                       confidence, ai_forward, reasons, gaps, evidence, needs_review, review_reasons, steps,
                       tool_calls)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rec.uid, _now(), rec.model,
                    a.fit_score if a else None, a.recommended_resume if a else None,
                    a.confidence.value if a else None, a.ai_forward.value if a else None,
                    json.dumps(a.reasons if a else []), json.dumps(a.gaps if a else []),
                    json.dumps(a.evidence if a else []), int(rec.needs_review),
                    json.dumps(rec.review_reasons), rec.steps, json.dumps(rec.tool_calls),
                ),
            )

    def save_outreach(self, uid: str, contact: str, draft: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO outreach (uid, contact, draft, created_at) VALUES (?,?,?,?)",
                (uid, contact, draft, _now()),
            )

    # -- digest -------------------------------------------------------------
    def digest_rows(self) -> list[sqlite3.Row]:
        """Assessed, open, not-yet-notified postings with their assessment and outreach."""
        return self.conn.execute(
            """SELECT p.*, a.fit_score, a.recommended_resume, a.confidence, a.ai_forward, a.reasons,
                      a.gaps, a.evidence, a.needs_review, a.review_reasons, o.contact, o.draft
               FROM postings p JOIN assessments a ON a.uid = p.uid
               LEFT JOIN outreach o ON o.uid = p.uid
               WHERE p.status='open' AND p.notified_at IS NULL AND p.user_status IN ('new','saved')
               ORDER BY a.needs_review ASC, a.fit_score DESC"""
        ).fetchall()

    def pending_rows(self, since: Optional[str] = None) -> list[sqlite3.Row]:
        """Passed the rules, not assessed yet (budget or Ollama down), first seen since `since`.

        These are listed but never marked notified, so they still show up as
        full matches once the agent gets to them.
        """
        return [r for r in self.awaiting_assessment() if r["first_seen"] >= (since or "")]

    def closed_since(self, since_iso: Optional[str]) -> list[sqlite3.Row]:
        """Closed postings you had shown interest in (assessed, saved or applied)."""
        return self.conn.execute(
            """SELECT p.* FROM postings p LEFT JOIN assessments a ON a.uid=p.uid
               WHERE p.status='closed' AND p.closed_at >= COALESCE(?, '')
                 AND (a.uid IS NOT NULL OR p.user_status IN ('saved','applied'))
               ORDER BY p.closed_at DESC""",
            (since_iso,),
        ).fetchall()

    def mark_notified(self, uids: Iterable[str]) -> None:
        now = _now()
        with self.conn:
            self.conn.executemany("UPDATE postings SET notified_at=? WHERE uid=?", [(now, u) for u in uids])

    # -- runs -------------------------------------------------------------
    def start_run(self) -> int:
        with self.conn:
            cur = self.conn.execute("INSERT INTO runs (started_at) VALUES (?)", (_now(),))
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, stats: dict) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET finished_at=?, stats=? WHERE id=?", (_now(), json.dumps(stats), run_id)
            )

    def last_finished_run_start(self) -> Optional[str]:
        row = self.conn.execute(
            "SELECT started_at FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["started_at"] if row else None
