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
