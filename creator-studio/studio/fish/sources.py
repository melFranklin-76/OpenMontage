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
    FeedSource(
        name="The Advocate",
        url="https://www.advocate.com/feed",
        category="lgbtq-news",
    ),
    FeedSource(
        name="them.",
        url="https://www.them.us/feed/rss",
        category="lgbtq-culture",
    ),
    FeedSource(
        name="Out Magazine",
        url="https://www.out.com/feed",
        category="lgbtq-culture",
    ),
    FeedSource(
        name="INTO More",
        url="https://www.intomore.com/feed/",
        category="lgbtq-culture",
    ),
    FeedSource(
        name="Autostraddle",
        url="https://www.autostraddle.com/feed/",
        category="lesbian",
    ),
    FeedSource(
        name="Bi.org News",
        url="https://bi.org/en/feed",
        category="bisexual",
    ),
    FeedSource(
        name="TransGriot",
        url="https://transgriot.blogspot.com/feeds/posts/default?alt=rss",
        category="black-trans",
    ),
    FeedSource(
        name="Washington Blade",
        url="https://www.washingtonblade.com/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="Gay Times",
        url="https://www.gaytimes.com/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="Towleroad",
        url="https://www.towleroad.com/feed/",
        category="gay",
    ),
    FeedSource(
        name="Metro Weekly",
        url="https://www.metroweekly.com/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="PinkNews",
        url="https://www.pinknews.co.uk/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="Erin in the Morning",
        url="https://www.erininthemorning.com/feed",
        category="trans-news",
    ),
    FeedSource(
        name="Queerty",
        url="https://www.queerty.com/feed",
        category="lgbtq-culture",
    ),
    FeedSource(
        name="Los Angeles Blade",
        url="https://www.losangelesblade.com/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="Gay City News",
        url="https://www.gaycitynews.com/feed/",
        category="lgbtq-news",
    ),
    FeedSource(
        name="Prism Reports",
        url="https://prismreports.org/feed/",
        category="black-trans",
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
