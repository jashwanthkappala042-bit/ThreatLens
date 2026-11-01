"""Text helpers shared by scanners and routes."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'`]+")
TRAILING_PUNCT = ".,;:!?)]}'\"”’>"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    value = dt
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def clamp(text: str, limit: int) -> str:
    """Hard truncation without ellipsis characters (safe for storage)."""
    return (text or "")[:limit]


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_excerpt(text: str, limit: int = 220) -> str:
    return truncate(normalize_whitespace(text), limit)


def extract_urls(text: str, limit: int = 25) -> list[str]:
    """Extract http(s)/www URLs from untrusted text.

    A missing scheme on www.* URLs is normalised to https, but plain domains
    are not guessed in order to avoid false positives.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.finditer(text):
        candidate = match.group(0).strip().rstrip(TRAILING_PUNCT)
        if not candidate:
            continue
        if candidate.lower().startswith("www."):
            candidate = "https://" + candidate
        try:
            parts = urlsplit(candidate)
        except ValueError:
            continue
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)
        if len(found) >= limit:
            break
    return found


def strip_fragment(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
