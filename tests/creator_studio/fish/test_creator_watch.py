"""Tests for creator watch (offline — no feeds, no yt-dlp)."""

from __future__ import annotations

from studio.fish import creator_watch as cw


VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
so the school board voted last night

00:00:02.000 --> 00:00:04.000
so the school board voted last night

00:00:04.000 --> 00:00:06.000
to ban the <c>library</c> books honey
"""


def test_vtt_to_text_strips_cues_and_rolling_repeats():
    text = cw._vtt_to_text(VTT)
    assert "-->" not in text and "WEBVTT" not in text
    assert text.count("school board voted") == 1
    assert "<c>" not in text and "library" in text


def test_extract_topics_needs_recurrence_in_transcript():
    transcript = (
        "the school board banned the books and the school board "
        "heard from parents about the books and the school kept the books out "
    )
    topics = cw.extract_topics(transcript)
    assert "school" in topics and "books" in topics
    assert "parents" not in topics          # mentioned once — passing mention
    assert "honey" not in cw.extract_topics("honey honey honey honey")


def test_extract_topics_title_words_count_without_recurrence():
    topics = cw.extract_topics("nothing here overlaps", video_title="Pastor tithes backlash")
    assert "pastor" in topics and "tithes" in topics


def _digest(*stories):
    return {"items": [
        {"title": t, "summary": s, "relevance_score": r}
        for t, s, r in stories
    ]}


SIGNALS = {"Funky Dineva": {
    "video_id": "abc", "title": "ep", "published": "",
    "topics": ["pastor", "tithes", "church", "facebook"],
}}


def test_boost_candidates_lifts_overlapping_story_and_reorders():
    digest = _digest(
        ("Lesbian filmmaker wins award", "festival premiere", 0.90),
        ("Gay pastor pushed out over tithes post", "church facebook dispute", 0.86),
    )
    out = cw.boost_candidates(digest, SIGNALS)
    top = out["items"][0]
    assert top["title"].startswith("Gay pastor")
    assert top["creator_signal"]["channel"] == "Funky Dineva"
    assert top["relevance_score"] > 0.90
    assert out["creator_watch"]["Funky Dineva"]["topics"]


def test_boost_is_capped():
    digest = _digest(("pastor tithes church facebook", "pastor tithes church facebook", 0.5))
    out = cw.boost_candidates(digest, SIGNALS)
    assert out["items"][0]["relevance_score"] <= 0.5 + cw.MAX_BOOST + 1e-9


def test_single_topic_overlap_is_coincidence_not_coverage():
    digest = _digest(("Church choir wins national title", "gospel", 0.8))
    out = cw.boost_candidates(digest, SIGNALS)   # only 'church' overlaps
    assert "creator_signal" not in out["items"][0]
    assert out["items"][0]["relevance_score"] == 0.8


def test_no_signals_is_a_noop():
    digest = _digest(("Gay pastor story", "church", 0.8))
    out = cw.boost_candidates(digest, {})
    assert "creator_signal" not in out["items"][0]
    assert "creator_watch" not in out


def test_watched_channels_configured():
    assert "Funky Dineva" in cw.WATCHED_CHANNELS
    assert "Outlaws with TS Madison" in cw.WATCHED_CHANNELS
