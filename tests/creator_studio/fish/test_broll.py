"""Tests for the Pexels b-roll helper (offline — no API calls)."""

from __future__ import annotations

from pathlib import Path

from studio.fish import broll


def _capture_queries(monkeypatch):
    """Stub search_broll, recording every query the ladder sends out."""
    sent: list[str] = []

    def fake_search(query, orientation="landscape", **kw):
        sent.append(query)
        return None

    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    monkeypatch.setattr(broll, "search_broll", fake_search)
    return sent


def test_fetch_never_sends_raw_headline_words(monkeypatch, tmp_path):
    """Literal headline words must never reach Pexels.

    Pexels fuzzy-matches any single word: a headline ending in "the Mother
    Road" once returned a mom-with-kids clip under a story about gay bars.
    Only curated concept queries (topic map, lane term) may go out.
    """
    sent = _capture_queries(monkeypatch)
    broll.fetch_broll_for_story(
        "Dispatches from Route 66: What I found at the end of the Mother Road",
        "lesbian", tmp_path / "x.mp4",
    )
    joined = " ".join(sent)
    assert "mother" not in joined and "route" not in joined
    assert sent == [broll.LANE_SEARCH_TERMS["lesbian"]]


def test_fetch_mode_specific_sends_only_topic_query(monkeypatch, tmp_path):
    sent = _capture_queries(monkeypatch)
    broll.fetch_broll_for_story(
        "Historic gay bar closes after 40 years", "gay",
        tmp_path / "x.mp4", mode="specific",
    )
    assert sent == ["nightclub stage lights"]

    sent.clear()
    broll.fetch_broll_for_story(
        "Zzzz qqqq wwww", "gay", tmp_path / "x.mp4", mode="specific",
    )
    assert sent == []      # no topic match → no query at all in specific mode


def test_fetch_mode_lane_sends_only_lane_term(monkeypatch, tmp_path):
    sent = _capture_queries(monkeypatch)
    broll.fetch_broll_for_story(
        "Historic gay bar closes after 40 years", "gay",
        tmp_path / "x.mp4", mode="lane",
    )
    assert sent == [broll.LANE_SEARCH_TERMS["gay"]]


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


def test_topic_query_uses_word_boundaries_not_substrings():
    """'barred' must not trip the 'bar' → nightclub mapping."""
    assert broll.topic_query("Turkey barred a cruise with gay travelers") == ""
    assert broll.topic_query("Barbara marches for equality") == "protest march crowd"
    # but a real bar still maps, including the plural
    assert broll.topic_query("Historic gay bar closes") == "nightclub stage lights"
    assert broll.topic_query("Gay bars see a revival") == "nightclub stage lights"


def test_mentions_public_person_ignores_venues_and_title_case():
    # A named venue is a place, not a person.
    assert not broll.mentions_public_person("The Stonewall Inn reopens as a museum")
    # All-title-case headlines carry no name signal.
    assert not broll.mentions_public_person("Why Trans Elders Deserve Better Care")


def test_lane_search_terms_cover_the_four_lanes():
    assert set(broll.LANE_SEARCH_TERMS) == {"gay", "lesbian", "bisexual", "trans"}
    assert "legacy" not in broll.LANE_SEARCH_TERMS


def test_mentions_public_person_detects_named_people():
    assert broll.mentions_public_person("Laverne Cox honored at awards gala")
    assert broll.mentions_public_person("Pete Buttigieg responds to the ruling")


def test_mentions_public_person_ignores_institutions_and_places():
    """Capitalized bigrams that are orgs/places must not read as people."""
    for title in (
        "Supreme Court hears marriage case",
        "White House issues new guidance",
        "New York council reverses book ban",
        "Trevor Project reports record demand",
        "Pride Month kicks off nationwide",
    ):
        assert not broll.mentions_public_person(title), title


def test_mentions_public_person_false_for_plain_headline():
    assert not broll.mentions_public_person("Lesbian author banned from library")


def test_search_broll_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert broll.search_broll("anything") is None


def test_fetch_broll_returns_none_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    got = broll.fetch_broll_for_story("Title", "gay", tmp_path / "x.mp4")
    assert got is None
    assert not (tmp_path / "x.mp4").exists()
