"""Text helpers: turn job-board HTML into clean plain text."""
from __future__ import annotations

import html
import re

_BLOCK_TAGS = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr|/ul|/ol)\b[^>]*>", re.IGNORECASE)
_LI = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<\s*(script|style)\b.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)


def html_to_text(raw: str | None) -> str:
    """Convert (possibly double-escaped) HTML to readable plain text."""
    if not raw:
        return ""
    text = raw
    # Greenhouse returns HTML that is itself HTML-escaped; unescape until stable.
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    text = _SCRIPT.sub(" ", text)
    text = _LI.sub("\n- ", text)
    text = _BLOCK_TAGS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize(text: str | None) -> str:
    """Lowercase and collapse whitespace, for matching."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()
