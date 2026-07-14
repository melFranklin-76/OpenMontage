"""Tests for the Pexels b-roll helper (offline — no API calls)."""

from __future__ import annotations

from pathlib import Path

from studio.fish import broll


def test_build_query_strips_stopwords():
    q = broll.build_query("The community rallies at the Stonewall after the ruling", "gay")
    assert "the" not in q.split()
    assert "community" in q


def test_build_query_is_story_specific_not_lane_flavored():
    """The primary query must reflect the story, not a generic lane booster.

    Appending 'gay pride rainbow crowd' to every search made Pexels return
    generic pride footage instead of story-relevant clips, so the lane term
    is reserved for the fallback query only.
    """
    q = broll.build_query("Supreme Court hears marriage case", "gay")
    assert "supreme" in q
    assert "court" in q
    assert "pride" not in q  # lane booster must not pollute the primary query


def test_build_query_empty_title_falls_back():
    q = broll.build_query("", "")
    assert q == broll.DEFAULT_SEARCH_TERM


def test_topic_query_maps_story_subject_to_stock_concept():
    """Stock libraries have no news footage, so we search the story's subject."""
    assert broll.topic_query("Lesbian author banned from library board") == \
        "library bookshelves reading"
    assert broll.topic_query("Supreme Court hears marriage case") == \
        "courthouse justice gavel"
    assert broll.topic_query("Trans swimmer wins state championship") == \
        "stadium athlete sport"


def test_topic_query_death_outranks_profession():
    """An obituary gets a vigil, not party footage from the subject's job."""
    assert broll.topic_query("Beloved drag performer dies at 71") == \
        "candle vigil memorial"


def test_topic_query_returns_empty_when_no_subject_matches():
    assert broll.topic_query("Zzzz qqqq wwww") == ""


def test_lane_search_terms_cover_the_four_lanes():
    assert set(broll.LANE_SEARCH_TERMS) == {"gay", "lesbian", "bisexual", "Black trans"}
    assert "legacy" not in broll.LANE_SEARCH_TERMS


def test_search_broll_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert broll.search_broll("anything") is None


def test_fetch_broll_returns_none_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    got = broll.fetch_broll_for_story("Title", "gay", tmp_path / "x.mp4")
    assert got is None
    assert not (tmp_path / "x.mp4").exists()
