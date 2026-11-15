"""Command line: python -m jobalert <command>."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from dotenv import load_dotenv

from .config import load_config
from .http import make_session
from .llm import OllamaClient
from .pipeline import RunOptions, run
from .sources import SourceError, source_for
from .store import Store


def _cmd_run(args, config) -> int:
    store = Store(config.settings.database)
    try:
        result = run(
            config,
            store,
            RunOptions(
                dry_run=args.dry_run,
                use_llm=not args.no_llm,
                only_company=args.company,
                max_postings=args.limit,
            ),
        )
    finally:
        store.close()
    print(json.dumps(result.stats, indent=2))
    print(f"Digest: {result.digest_path}" + (" (emailed)" if result.sent else ""))
    return 0


def _cmd_check(args, config) -> int:
    """Verify every watchlist board responds, and Ollama is ready."""
    session = make_session()
    failures = 0
    for company in config.watchlist:
        if not company.enabled:
            continue
        try:
            postings = source_for(company, session).fetch(company)
            print(f"  ok    {company.key:<18} {company.source:<16} {len(postings)} postings")
        except SourceError as exc:
            failures += 1
            print(f"  FAIL  {company.key:<18} {company.source:<16} {exc}")
    healthy, why = OllamaClient(config.settings.ollama).health()
    print(f"\nOllama ({config.settings.ollama.model}): {'ok' if healthy else why}")
    return 1 if failures else 0


def _cmd_list(args, config) -> int:
    store = Store(config.settings.database)
    rows = store.conn.execute(
        """SELECT p.uid, p.company, p.title, p.user_status, a.fit_score, a.recommended_resume, a.needs_review
           FROM postings p JOIN assessments a ON a.uid = p.uid
           WHERE p.status='open' ORDER BY a.fit_score DESC LIMIT ?""",
        (args.top,),
    ).fetchall()
    for r in rows:
        flag = " (review)" if r["needs_review"] else ""
        print(f"{r['fit_score'] if r['fit_score'] is not None else '--':>3}  {r['company']:<14} {r['title'][:60]:<60} "
              f"[{r['recommended_resume']}] {r['user_status']}{flag}\n     {r['uid']}")
    store.close()
    return 0


def _cmd_mark(args, config) -> int:
    store = Store(config.settings.database)
    ok = store.set_user_status(args.uid, args.status)
    store.close()
    print("updated" if ok else f"no posting with id {args.uid}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="jobalert", description="Agentic internship alert system")
    parser.add_argument("--config", default="config", help="config directory (default: config)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="fetch, filter, assess and send the digest")
    p_run.add_argument("--dry-run", action="store_true", help="write out/digest.html instead of emailing")
    p_run.add_argument("--no-llm", action="store_true", help="rules only, skip the agent")
    p_run.add_argument("--company", help="only this watchlist key")
    p_run.add_argument("--limit", type=int, help="max postings the agent assesses this run")

    sub.add_parser("check", help="check every job board and Ollama")

    p_list = sub.add_parser("list", help="show assessed open postings")
    p_list.add_argument("--top", type=int, default=20)

    p_mark = sub.add_parser("mark", help="record what you did with a posting")
    p_mark.add_argument("uid")
    p_mark.add_argument("status", choices=["applied", "ignored", "saved", "new"])

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    )
    config = load_config(args.config)
    handlers = {"run": _cmd_run, "check": _cmd_check, "list": _cmd_list, "mark": _cmd_mark}
    return handlers[args.command](args, config)


if __name__ == "__main__":
    sys.exit(main())
