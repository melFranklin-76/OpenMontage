"""Tests for the FISH long-form roundup script builder (offline paths only)."""

from __future__ import annotations

import pytest

from studio.fish import long_roundup_script as lrs


DIGEST = {
    "show": "What's the LGBT, Fish?",
    "date": "2026-07-08",
    "items": [
        {
            "title": f"Story number {i}",
            "source": f"Source {i}",
            "url": "",   # no URL → no network fetch in tests
            "published_at": "2026-07-08T00:00:00+00:00",
            "summary": f"Summary text for story {i} with enough words to matter.",
            "matched_lane": lane,
            "relevance_score": 1.0 - i * 0.05,
        }
        for i, lane in enumerate(
            ["legacy", "gay", "lesbian", "bisexual", "Black trans",
             "gay", "lesbian", "gay", "Black trans", "legacy"],
            start=1,
        )
    ],
}


def _build():
    return lrs.build_roundup_script(DIGEST, enrich_via_jina=False)


def test_has_cold_open_intro_outro():
    script = _build()
    ids = [s["id"] for s in script["sections"]]
    assert ids[0] == "cold_open"
    assert ids[1] == "intro"
    assert ids[-1] == "outro"


def test_ten_stories_produce_title_and_body_each():
    script = _build()
    ids = [s["id"] for s in script["sections"]]
    for i in range(1, 11):
        assert f"ch{i}_title" in ids
        assert f"ch{i}_body" in ids


def test_chapter_timestamps_monotonic_and_start_near_zero():
    script = _build()
    ts = [c["seconds"] for c in script["chapter_timestamps"]]
    assert ts == sorted(ts)
    assert ts[0] < 60  # intro chapter starts within the first minute


def test_duration_scales_with_story_count():
    short = lrs.build_roundup_script(DIGEST, story_count=3, enrich_via_jina=False)
    full = _build()
    assert full["target_duration_seconds"] > short["target_duration_seconds"]


def test_stories_metadata_preserved():
    script = _build()
    assert script["story_count"] == 10
    assert script["stories"][0]["rank"] == 1
    assert script["stories"][0]["lane"] == "legacy"


def test_raises_on_empty_digest():
    with pytest.raises(ValueError):
        lrs.build_roundup_script({"items": []})


def test_no_hashtags_spoken_anywhere():
    """Narration must never contain '#' — hashtags live in descriptions only."""
    script = _build()
    for sec in script["sections"]:
        assert "#" not in sec["narration"], f"hashtag spoken in {sec['id']}"


def test_transition_pool_has_variety():
    assert len(lrs.TRANSITION_LINES) >= 12


def test_extract_key_sentences_filters_boilerplate():
    text = (
        "Subscribe to our newsletter for more content every day of the week. "
        "The organization announced a $2 million grant on March 3, 2026 to fund "
        "housing for Black trans elders across five cities. "
        "Accept cookies to continue reading this article on our website today. "
        '"This is the largest single investment in our history," said the director '
        "of the foundation during the press conference on Tuesday afternoon."
    )
    picked = lrs._extract_key_sentences(text, max_sentences=3)
    joined = " ".join(picked).lower()
    assert "newsletter" not in joined
    assert "cookies" not in joined
    assert any("grant" in s.lower() or "investment" in s.lower() for s in picked)


def test_extract_key_sentences_strips_urls():
    text = (
        "The organization launched at https://example.com/donate today. "
        "Visit www.example.org for more. Contact admin@example.com for info. "
        "The grant will fund housing for Black trans elders in five major cities."
    )
    picked = lrs._extract_key_sentences(text, max_sentences=3)
    joined = " ".join(picked)
    assert "https://" not in joined
    assert "www." not in joined
    assert "@" not in joined


def test_no_urls_in_narration():
    """Narration must never contain URLs — TTS spells them out."""
    script = _build()
    for sec in script["sections"]:
        narration = sec["narration"]
        assert "http://" not in narration, f"URL in {sec['id']}"
        assert "https://" not in narration, f"URL in {sec['id']}"
        assert "www." not in narration, f"URL in {sec['id']}"
