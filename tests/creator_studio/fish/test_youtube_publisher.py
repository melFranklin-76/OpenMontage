"""Tests for FISH YouTube publisher (metadata + config, no live upload)."""

from __future__ import annotations

from studio.fish import youtube_publisher as yt


SCRIPT = {
    "topic": "Marsha P. Johnson: Stonewall hero",
    "lane": "legacy",
    "hashtags": ["#lgbtq", "#lgbthistory"],
    "source_attribution": {
        "name": "The Advocate",
        "url": "https://example.com/story",
    },
}


def test_build_metadata_shape():
    meta = yt.build_metadata(SCRIPT, privacy="unlisted")
    assert "snippet" in meta and "status" in meta
    assert meta["snippet"]["categoryId"] == "25"  # News & Politics
    assert meta["status"]["privacyStatus"] == "unlisted"
    assert meta["status"]["selfDeclaredMadeForKids"] is False


def test_title_stays_under_100_chars_with_shorts_tag():
    long_script = dict(SCRIPT, topic="x" * 200)
    meta = yt.build_metadata(long_script)
    assert len(meta["snippet"]["title"]) <= 100
    # Note: title is truncated by 99-char cap so #Shorts may be cut. That's ok
    # — YouTube Shorts is detected by aspect ratio + duration regardless.


def test_description_contains_source_and_topic():
    meta = yt.build_metadata(SCRIPT)
    desc = meta["snippet"]["description"]
    assert SCRIPT["topic"] in desc
    assert "The Advocate" in desc
    assert "https://example.com/story" in desc


def test_lane_tags_merged_in():
    for lane, expected in [
        ("gay", "gay"),
        ("lesbian", "lesbian"),
        ("Black trans", "Black trans"),
        ("legacy", "lgbthistory"),
    ]:
        script = dict(SCRIPT, lane=lane)
        meta = yt.build_metadata(script)
        assert expected in meta["snippet"]["tags"]


def test_privacy_choices_are_respected():
    for p in ("private", "unlisted", "public"):
        meta = yt.build_metadata(SCRIPT, privacy=p)
        assert meta["status"]["privacyStatus"] == p


def test_scopes_are_youtube_upload_only():
    assert yt.SCOPES == ["https://www.googleapis.com/auth/youtube.upload"]


ROUNDUP = {
    "format": "roundup",
    "digest_date": "2026-07-08",
    "story_count": 3,
    "stories": [
        {"rank": 1, "title": "Story one", "source": "SrcA",
         "url": "https://a.example/1", "lane": "legacy"},
        {"rank": 2, "title": "Story two", "source": "SrcB",
         "url": "https://b.example/2", "lane": "Black trans"},
        {"rank": 3, "title": "Story three", "source": "SrcC",
         "url": "https://c.example/3", "lane": "lesbian"},
    ],
    "chapter_timestamps": [
        {"seconds": 0, "label": "Intro"},
        {"seconds": 75, "label": "1. Story one"},
        {"seconds": 190, "label": "2. Story two"},
        {"seconds": 4000, "label": "3. Story three"},
    ],
    "hashtags": ["#lgbtq"],
}


def test_long_metadata_has_chapters_and_sources():
    meta = yt.build_metadata(ROUNDUP, fmt="long")
    desc = meta["snippet"]["description"]
    assert "0:00" in desc
    assert "1:15 1. Story one" in desc
    assert "1:06:40 3. Story three" in desc   # H:MM:SS formatting
    assert "https://a.example/1" in desc
    assert "SrcB" in desc


def test_long_metadata_excludes_shorts_tag():
    meta = yt.build_metadata(ROUNDUP, fmt="long")
    assert "Shorts" not in meta["snippet"]["tags"]
    assert "#Shorts" not in meta["snippet"]["description"]


def test_long_title_contains_date_and_count():
    meta = yt.build_metadata(ROUNDUP, fmt="long")
    title = meta["snippet"]["title"]
    assert "2026-07-08" in title
    assert "3 stories" in title
    assert len(title) <= 100


def test_short_format_is_default():
    meta = yt.build_metadata(SCRIPT)
    assert "#Shorts" in meta["snippet"]["title"]
