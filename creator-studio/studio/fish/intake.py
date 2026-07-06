"""RSS intake for What's the LGBT, Fish?

Fetches and normalizes story candidates from the configured RSS sources so the
daily digest can run on live news instead of a static sample file.
"""

from __future__ import annotations

from .rss_fetcher import fetch_sources
from .sources import list_sources


def get_configured_sources() -> list[dict[str, str]]:
    return list_sources()


def fetch_live_stories(limit_per_source: int = 20) -> list[dict[str, str]]:
    """Fetch and normalize stories from every configured RSS source."""
    return fetch_sources(get_configured_sources(), limit_per_source=limit_per_source)
