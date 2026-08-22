"""Keep FISH nights from repeating the same stories.

Three separate leaks produced identical roundups:

1. Recency was not a ranking factor. TransGriot's RSS still serves 2020
   posts, and those match the Black-trans lane at a perfect 1.0, so they
   beat actual 2026 news every night.
2. The same wire story arrives from Advocate and them. (and others) with
   nearly identical titles. Both ranked. Both made the show.
3. Nothing remembered last night's top 10, so a story that stayed in the
   feeds for a week was the show for a week.

This module is the nightly gate: drop stale items, collapse syndication
duplicates, and skip URLs/titles already used while they are still current.
CI persists the used-story file with actions/cache, same pattern as
creator-watch state.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse

DEFAULT_STATE_PATH = Path("creator-studio/out/fish/used_stories.json")

# A nightly news show. Anything older than this is archive, not tonight.
MAX_STORY_AGE_DAYS = 7

# After a story makes the roundup, keep it off the show this long even if
# the feed still lists it. Long enough to cover a slow news week; short
# enough that a genuine follow-up with a new URL can return.
USED_TTL_DAYS = 14

# How many of tonight's ranked stories to remember. Matches the long
# roundup count — Shorts are a subset of the same list.
RECORD_COUNT = 10

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SMART_QUOTES = str.maketrans({
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
})


def title_key(title: str) -> str:
    """Collapse a headline to a syndication-stable fingerprint."""
    text = (title or "").translate(_SMART_QUOTES).lower()
    return _NON_ALNUM.sub(" ", text).strip()


def url_key(url: str) -> str:
    """Host + path only. Query strings and trailing slashes are tracking."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(("", host, path, "", "", "")).lstrip("/")


def parse_published(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_fresh(
    published_at: str,
    *,
    now: datetime | None = None,
    max_age_days: int = MAX_STORY_AGE_DAYS,
) -> bool:
    """True when the story is recent enough, or has no parseable date.

    Undated items stay in. Dropping them would hide feeds that omit dates;
    the used-story list still prevents those from looping.
    """
    parsed = parse_published(published_at)
    if parsed is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return (current - parsed) <= timedelta(days=max_age_days)


def recency_sort_key(item: dict) -> float:
    """Newer stories sort higher when relevance scores tie."""
    parsed = parse_published(item.get("published_at", ""))
    if parsed is None:
        return 0.0
    return parsed.timestamp()


def sort_stories(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda row: (row.get("relevance_score", 0.0), recency_sort_key(row)),
        reverse=True,
    )


def _item_keys(item: dict) -> set[str]:
    keys = set()
    uk = url_key(item.get("url", ""))
    tk = title_key(item.get("title", ""))
    if uk:
        keys.add("url:" + uk)
    if tk:
        keys.add("title:" + tk)
    return keys


def dedupe_stories(items: list[dict]) -> tuple[list[dict], int]:
    """Keep the first (highest-ranked) copy of a syndicated story."""
    seen: set[str] = set()
    kept: list[dict] = []
    dropped = 0
    for item in items:
        keys = _item_keys(item)
        if keys & seen:
            dropped += 1
            continue
        seen.update(keys)
        kept.append(item)
    return kept, dropped


def load_state(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {"version": 1, "stories": []}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "stories": []}
    if not isinstance(data, dict) or not isinstance(data.get("stories"), list):
        return {"version": 1, "stories": []}
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")


def _active_used_keys(state: dict, *, today: date) -> set[str]:
    keys: set[str] = set()
    for row in state.get("stories", []):
        expires = row.get("expires_on", "")
        if expires and expires < today.isoformat():
            continue
        if row.get("url_key"):
            keys.add("url:" + row["url_key"])
        if row.get("title_key"):
            keys.add("title:" + row["title_key"])
    return keys


def drop_used(
    items: list[dict],
    state: dict,
    *,
    today: date | None = None,
) -> tuple[list[dict], int]:
    used = _active_used_keys(state, today=today or date.today())
    if not used:
        return items, 0
    kept: list[dict] = []
    dropped = 0
    for item in items:
        if _item_keys(item) & used:
            dropped += 1
            continue
        kept.append(item)
    return kept, dropped


def record_used(
    state: dict,
    items: list[dict],
    *,
    used_on: date | None = None,
    ttl_days: int = USED_TTL_DAYS,
    limit: int = RECORD_COUNT,
) -> dict:
    """Remember tonight's top stories and drop entries past TTL."""
    today = used_on or date.today()
    expires_on = (today + timedelta(days=ttl_days)).isoformat()
    today_s = today.isoformat()
    existing_keys = _active_used_keys(state, today=today)
    stories = [
        row for row in state.get("stories", [])
        if row.get("expires_on", "") >= today_s
    ]
    for item in items[:limit]:
        keys = _item_keys(item)
        if not keys or keys & existing_keys:
            continue
        uk = url_key(item.get("url", ""))
        tk = title_key(item.get("title", ""))
        stories.append({
            "url": item.get("url", ""),
            "url_key": uk,
            "title": item.get("title", ""),
            "title_key": tk,
            "used_on": today_s,
            "expires_on": expires_on,
        })
        existing_keys.update(keys)
    return {"version": 1, "stories": stories}


def apply_nightly_gates(
    items: list[dict],
    *,
    now: datetime | None = None,
    today: date | None = None,
    used_state: dict | None = None,
    max_age_days: int = MAX_STORY_AGE_DAYS,
) -> tuple[list[dict], dict]:
    """Freshness → used-memory → score/recency sort → syndication dedup."""
    current = now or datetime.now(timezone.utc)
    on_day = today or current.date()
    stale = 0
    fresh: list[dict] = []
    for item in items:
        if is_fresh(item.get("published_at", ""), now=current, max_age_days=max_age_days):
            fresh.append(item)
        else:
            stale += 1

    unused, used_dropped = drop_used(fresh, used_state or {}, today=on_day)
    ranked = sort_stories(unused)
    unique, dup_dropped = dedupe_stories(ranked)
    stats = {
        "max_age_days": max_age_days,
        "dropped_stale": stale,
        "dropped_used": used_dropped,
        "dropped_duplicate": dup_dropped,
    }
    return unique, stats
