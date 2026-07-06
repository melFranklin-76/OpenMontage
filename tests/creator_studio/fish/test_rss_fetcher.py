from studio.fish.rss_fetcher import normalize_entry


def test_normalize_entry_maps_common_feed_fields() -> None:
    entry = {
        "title": "  Gay artist announces   new project ",
        "link": "https://example.com/story",
        "published": "Mon, 06 Jul 2026 10:00:00 -0500",
        "summary": "  A short   summary. ",
    }

    story = normalize_entry(entry, "Example Source")

    assert story == {
        "title": "Gay artist announces new project",
        "source": "Example Source",
        "url": "https://example.com/story",
        "published_at": "2026-07-06T10:00:00-05:00",
        "summary": "A short summary.",
    }


def test_normalize_entry_strips_html_markup() -> None:
    entry = {
        "title": "Story with &amp; entity",
        "link": "https://example.com/story",
        "summary": (
            '<img src="https://example.com/photo.jpg" /><br /><p>Victoria Cruz, '
            "one of the matriarchs, has died.</p><p>She was 79.</p>"
        ),
    }

    story = normalize_entry(entry, "Example Source")

    assert story["title"] == "Story with & entity"
    assert story["summary"] == "Victoria Cruz, one of the matriarchs, has died. She was 79."
    assert "<" not in story["summary"]


def test_normalize_entry_handles_missing_fields() -> None:
    story = normalize_entry({}, "Example Source")

    assert story["title"] == ""
    assert story["source"] == "Example Source"
    assert story["url"] == ""
    assert story["published_at"] == ""
    assert story["summary"] == ""
