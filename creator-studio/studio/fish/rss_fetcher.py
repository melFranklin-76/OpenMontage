"""RSS fetching and normalization for What's the LGBT, Fish?"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class NormalizedStory:
    title: str
    source: str
    url: str
    published_at: str
    summary: str


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return " ".join(html.unescape(text).split())


def _published_at(entry: Any) -> str:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except (TypeError, ValueError, IndexError, OverflowError):
            return _clean_text(value)
    return ""


def normalize_entry(entry: Any, source_name: str) -> dict[str, str]:
    return {
        "title": _clean_text(entry.get("title", "")),
        "source": source_name,
        "url": _clean_text(entry.get("link", "")),
        "published_at": _published_at(entry),
        "summary": _clean_text(entry.get("summary", entry.get("description", ""))),
    }


def fetch_feed(url: str, source_name: str, limit: int = 20) -> list[dict[str, str]]:
    parsed = feedparser.parse(url)
    entries = getattr(parsed, "entries", [])[:limit]
    return [normalize_entry(entry, source_name) for entry in entries]


def fetch_sources(sources: list[dict[str, str]], limit_per_source: int = 20) -> list[dict[str, str]]:
    stories: list[dict[str, str]] = []

    for source in sources:
        if source.get("source_type", "rss") != "rss":
            continue
        stories.extend(
            fetch_feed(
                source["url"],
                source["name"],
                limit=limit_per_source,
            )
        )

    return stories
