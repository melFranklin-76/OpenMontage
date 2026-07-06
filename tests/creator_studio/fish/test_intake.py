from studio.fish import rss_fetcher
from studio.fish.intake import fetch_live_stories, get_configured_sources


class _FakeParsed:
    def __init__(self, entries):
        self.entries = entries


def test_get_configured_sources_returns_sources() -> None:
    sources = get_configured_sources()
    assert sources
    assert sources[0]["url"].startswith("http")


def test_fetch_live_stories_normalizes_configured_feeds(monkeypatch) -> None:
    def fake_parse(url):
        return _FakeParsed(
            [
                {
                    "title": "  Gay artist announces   new project ",
                    "link": "https://example.com/story",
                    "published": "Mon, 06 Jul 2026 10:00:00 -0500",
                    "summary": "  A short   summary. ",
                }
            ]
        )

    monkeypatch.setattr(rss_fetcher.feedparser, "parse", fake_parse)

    stories = fetch_live_stories(limit_per_source=5)

    assert len(stories) == len(get_configured_sources())
    story = stories[0]
    assert story["title"] == "Gay artist announces new project"
    assert story["url"] == "https://example.com/story"
    assert story["published_at"] == "2026-07-06T10:00:00-05:00"
    assert story["source"] == get_configured_sources()[0]["name"]


def test_fetch_live_stories_respects_limit(monkeypatch) -> None:
    def fake_parse(url):
        return _FakeParsed(
            [
                {"title": f"Gay story {i}", "link": f"https://example.com/{i}"}
                for i in range(10)
            ]
        )

    monkeypatch.setattr(rss_fetcher.feedparser, "parse", fake_parse)

    stories = fetch_live_stories(limit_per_source=3)

    assert len(stories) == 3 * len(get_configured_sources())
