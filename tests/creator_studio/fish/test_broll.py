"""Tests for the Pexels b-roll helper (offline — no API calls)."""

from __future__ import annotations

from pathlib import Path

from studio.fish import broll


def test_build_query_strips_stopwords():
    q = broll.build_query("The community rallies at the Stonewall after the ruling", "gay")
    assert "the" not in q.split()
    assert "community" in q
    assert "pride" in q  # gay lane booster


def test_build_query_empty_title_falls_back():
    q = broll.build_query("", "")
    assert q == broll.DEFAULT_SEARCH_TERM


def test_build_query_lane_booster_per_lane():
    for lane, term in broll.LANE_SEARCH_TERMS.items():
        q = broll.build_query("Some headline words here", lane)
        assert term.split()[0] in q


def test_search_broll_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    assert broll.search_broll("anything") is None


def test_fetch_broll_returns_none_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    got = broll.fetch_broll_for_story("Title", "gay", tmp_path / "x.mp4")
    assert got is None
    assert not (tmp_path / "x.mp4").exists()
