"""Send the digest over SMTP (settings come from environment variables / .env)."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("jobalert.notify")

REQUIRED = ("SMTP_SERVER", "EMAIL_USER", "EMAIL_PASS", "EMAIL_TO")


def email_configured() -> tuple[bool, list[str]]:
    missing = [k for k in REQUIRED if not os.getenv(k)]
    return not missing, missing


def send_email(subject: str, html_body: str, text_body: str) -> None:
    ok, missing = email_configured()
    if not ok:
        raise RuntimeError(f"Email not configured; missing: {', '.join(missing)}")
    server = os.environ["SMTP_SERVER"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.environ["EMAIL_USER"]
    to = os.environ["EMAIL_TO"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    log.info("Sending digest via %s:%s", server, port)
    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, os.environ["EMAIL_PASS"])
        smtp.sendmail(user, [to], msg.as_string())
    log.info("Digest sent")
