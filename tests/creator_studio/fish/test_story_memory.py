from datetime import date, datetime, timezone

from studio.fish.daily_digest import build_daily_candidates
from studio.fish.story_memory import (
    apply_nightly_gates,
    drop_used,
    is_fresh,
    record_used,
    title_key,
    url_key,
)


NOW = datetime(2026, 8, 22, 5, 0, tzinfo=timezone.utc)
TODAY = date(2026, 8, 22)


def test_url_key_strips_tracking_and_www() -> None:
    assert url_key("https://www.Advocate.com/story/?utm_source=rss#comments") == (
        "advocate.com/story"
    )


def test_title_key_collapses_syndication_punctuation() -> None:
    a = title_key("Former CIA officers warn Trump's administration")
    b = title_key("Former CIA Officers Warn Trump’s Administration")
    assert a == b


def test_is_fresh_drops_archive_posts() -> None:
    assert is_fresh("2020-08-13T17:00:00+00:00", now=NOW) is False
    assert is_fresh("2026-08-21T12:45:01+00:00", now=NOW) is True
    assert is_fresh("", now=NOW) is True


def test_apply_nightly_gates_drops_stale_used_and_duplicates() -> None:
    items = [
        {
            "title": "Not Feeling The (White) Trans Community Hatred Of Kamala Harris",
            "url": "https://transgriot.blogspot.com/2020/08/not-feeling.html",
            "published_at": "2020-08-13T17:00:00+00:00",
            "relevance_score": 1.0,
        },
        {
            "title": "Former CIA officers warn Trump's administration is reviving the Lavender Scare",
            "url": "https://www.advocate.com/politics/cia-officers-warn-lavender-scare",
            "published_at": "2026-08-21T12:45:01+00:00",
            "relevance_score": 0.96,
        },
        {
            "title": "Former CIA Officers Warn Trump’s Administration Is Reviving the Lavender Scare",
            "url": "https://www.them.us/cia-officers-warn-lavender-scare",
            "published_at": "2026-08-21T12:45:01+00:00",
            "relevance_score": 0.96,
        },
        {
            "title": "Gay artist announces new project",
            "url": "https://example.com/already-used",
            "published_at": "2026-08-21T10:00:00+00:00",
            "relevance_score": 0.90,
        },
        {
            "title": "Washington elects first out Black trans woman",
            "url": "https://www.erininthemorning.com/p/washington",
            "published_at": "2026-08-17T11:52:47+00:00",
            "relevance_score": 1.0,
        },
    ]
    used = record_used(
        {"version": 1, "stories": []},
        [{"title": "Gay artist announces new project", "url": "https://example.com/already-used"}],
        used_on=date(2026, 8, 21),
        limit=1,
    )
    kept, stats = apply_nightly_gates(
        items, now=NOW, today=TODAY, used_state=used,
    )
    titles = [row["title"] for row in kept]
    assert stats["dropped_stale"] == 1
    assert stats["dropped_used"] == 1
    assert stats["dropped_duplicate"] == 1
    assert titles[0].startswith("Washington")
    assert any("Lavender Scare" in t for t in titles)
    assert sum("Lavender Scare" in t for t in titles) == 1
    assert "Gay artist announces new project" not in titles
    assert not any("Kamala" in t for t in titles)


def test_used_stories_expire_after_ttl() -> None:
    state = record_used(
        {"version": 1, "stories": []},
        [{"title": "Old used story", "url": "https://example.com/old"}],
        used_on=date(2026, 8, 1),
        ttl_days=14,
        limit=1,
    )
    kept, dropped = drop_used(
        [{"title": "Old used story", "url": "https://example.com/old"}],
        state,
        today=TODAY,
    )
    assert dropped == 0
    assert len(kept) == 1


def test_digest_drops_stale_black_trans_archive() -> None:
    digest = build_daily_candidates(
        [
            {
                "title": "Black trans organizer leads Milwaukee safety initiative",
                "source": "TransGriot",
                "url": "https://transgriot.blogspot.com/2020/08/old.html",
                "published_at": "2020-08-13T17:00:00+00:00",
                "summary": "Community safety and health resources.",
            },
            {
                "title": "Black trans organizer wins 2026 city race",
                "source": "Erin in the Morning",
                "url": "https://www.erininthemorning.com/p/new",
                "published_at": "2026-08-21T11:00:00+00:00",
                "summary": "Community safety and health resources.",
            },
        ],
        now=NOW,
    )
    assert len(digest["items"]) == 1
    assert digest["items"][0]["source"] == "Erin in the Morning"
    assert digest["selection"]["dropped_stale"] == 1
