"""Source configuration for What's the LGBT, Fish?"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeedSource:
    name: str
    url: str
    source_type: str = "rss"
    category: str = "general"


DEFAULT_SOURCES: tuple[FeedSource, ...] = (
    FeedSource(
        name="LGBTQ Nation",
        url="https://www.lgbtqnation.com/feed/",
        category="lgbtq-news",
    ),
)


def list_sources() -> list[dict[str, str]]:
    return [
        {
            "name": source.name,
            "url": source.url,
            "source_type": source.source_type,
            "category": source.category,
        }
        for source in DEFAULT_SOURCES
    ]
