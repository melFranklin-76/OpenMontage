"""Tests for creator watch (offline — no feeds, no yt-dlp)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

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
    # TS Madison runs two channels and they are easy to mix up: "Outlaws" is
    # the sit-down commentary show, the other is her main channel. Pin both
    # IDs so a rename can't silently repoint one at the wrong feed.
    assert cw.WATCHED_CHANNELS["Outlaws with TS Madison"] == "UCsOACvK3jQaqeNsWfiW_kUg"
    assert cw.WATCHED_CHANNELS["Ts Madison"] == "UCE81T3u_YFLIJM6xxp7YJvg"
    assert cw.WATCHED_CHANNELS["Funky Dineva"] == "UChIkZ9tdYNG78qoFF6oWSvA"


# ── feed scanning ────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, text: str):
        self._text = text

    def read(self) -> bytes:
        return self._text.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _feed(*entries) -> str:
    """Channel feed XML. Entries are (video_id, title, age_hours)."""
    now = datetime.now(timezone.utc)
    blocks = "".join(
        f"<entry><yt:videoId>{vid}</yt:videoId><title>{title}</title>"
        f"<published>{(now - timedelta(hours=age)).isoformat()}</published></entry>"
        for vid, title, age in entries
    )
    return f"<feed>{blocks}</feed>"


def test_recent_videos_collects_the_window_not_just_the_newest():
    xml = _feed(("v1", "Short", 1), ("v2", "Live episode", 5))
    with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(xml)):
        videos = cw.recent_videos("CID")
    assert [v["video_id"] for v in videos] == ["v1", "v2"]


def test_recent_videos_stops_at_the_first_stale_entry():
    # Feeds are ordered newest-first, so a stale entry means everything after
    # it is older still — v4 is inside the window but unreachable.
    xml = _feed(("v1", "Recent", 1), ("v3", "Stale", 500), ("v4", "Unreachable", 2))
    with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(xml)):
        videos = cw.recent_videos("CID")
    assert [v["video_id"] for v in videos] == ["v1"]


def test_recent_videos_unescapes_titles_for_topic_extraction():
    xml = _feed(("v1", "Pastor &amp; church fallout", 1))
    with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(xml)):
        videos = cw.recent_videos("CID")
    assert videos[0]["title"] == "Pastor & church fallout"


def test_recent_videos_is_soft_on_unreachable_feeds():
    with mock.patch("urllib.request.urlopen", side_effect=OSError("no network")):
        assert cw.recent_videos("CID") == []


# ── episode selection ────────────────────────────────────────────────────────

def _iso(age_hours: float) -> str:
    """Timestamp `age_hours` old. Relative on purpose: a hardcoded date would
    quietly drift out of the freshness window and fail months from now."""
    return (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()


def _videos(*pairs) -> list[dict]:
    return [{"video_id": v, "title": t, "published": _iso(2)} for v, t in pairs]


def _on_beat(words: int) -> str:
    """A transcript that is both long enough and about the show's beat."""
    return ("gay lesbian black trans " * cw.MIN_EDITORIAL_MENTIONS) + ("word " * words)


def test_pick_episode_walks_past_shorts_and_thin_uploads():
    """The newest upload is usually a Short; the episode is further back.

    Taking the newest slot blindly cost the channel its whole night of signal,
    because a Short's handful of caption words never clears extract_topics'
    recurrence threshold.
    """
    videos = _videos(
        ("s1", "In Antigua #Shorts"),      # skipped on title — costs no fetch
        ("c1", "Quick clip"),              # fetched, too thin
        ("e1", "Live - Thursday night"),   # the episode
    )
    transcripts = {"c1": "word " * 50, "e1": _on_beat(cw.MIN_TRANSCRIPT_WORDS)}
    with mock.patch.object(cw, "recent_videos", return_value=videos), \
         mock.patch.object(cw, "fetch_transcript",
                           side_effect=lambda vid: transcripts.get(vid, "")) as fetch:
        episode = cw.pick_episode("CID", label="Chan")

    assert episode["video_id"] == "e1"
    assert episode["transcript"]
    assert [call.args[0] for call in fetch.call_args_list] == ["c1", "e1"]


def test_pick_episode_rejects_long_but_off_beat_uploads():
    """Length proves long-form, not commentary.

    A live run accepted 2,388 words of holiday vlog from a watched channel;
    its filler ("sandwich", "camera") then lifted 19% of the digest.
    """
    videos = _videos(("vlog", "In Antigua"), ("ep", "Pastor pushed out"))
    transcripts = {
        "vlog": "word " * (cw.MIN_TRANSCRIPT_WORDS + 500),   # long, zero beat
        "ep": _on_beat(cw.MIN_TRANSCRIPT_WORDS),
    }
    with mock.patch.object(cw, "recent_videos", return_value=videos), \
         mock.patch.object(cw, "fetch_transcript",
                           side_effect=lambda vid: transcripts.get(vid, "")):
        episode = cw.pick_episode("CID", label="Chan")
    assert episode["video_id"] == "ep"


def test_off_beat_upload_does_not_count_as_a_yt_dlp_failure():
    """Captions arrived — yt-dlp is healthy, the video was just off-beat."""
    budget = cw._FetchBudget(max_consecutive_failures=2)
    with mock.patch.object(cw, "recent_videos",
                           return_value=_videos(("vlog", "In Antigua"))), \
         mock.patch.object(cw, "fetch_transcript",
                           return_value="word " * (cw.MIN_TRANSCRIPT_WORDS + 10)):
        assert cw.pick_episode("CID", budget=budget) is None
    assert budget.consecutive_failures == 0


def test_editorial_mentions_counts_recurrence_not_presence():
    assert cw.editorial_mentions("a holiday in antigua with the girls") == 0
    # One passing mention across an episode is not coverage.
    assert cw.editorial_mentions("we went to a gay bar once") < cw.MIN_EDITORIAL_MENTIONS
    assert cw.editorial_mentions(
        "the gay pastor story, gay clergy, gay congregations"
    ) >= cw.MIN_EDITORIAL_MENTIONS
    assert cw.editorial_mentions("", title="Gay gay gay pastor") >= cw.MIN_EDITORIAL_MENTIONS


def test_pick_episode_caps_transcript_fetches_per_channel():
    videos = _videos(*[(f"v{i}", f"Clip {i}") for i in range(6)])
    with mock.patch.object(cw, "recent_videos", return_value=videos), \
         mock.patch.object(cw, "fetch_transcript", return_value="") as fetch:
        assert cw.pick_episode("CID") is None
    assert fetch.call_count == cw.MAX_TRANSCRIPT_ATTEMPTS


def test_pick_episode_gives_up_once_yt_dlp_looks_blocked():
    """A bot-walled yt-dlp looks identical to "no captions" — but retrying it
    across every channel burns minutes of two-minute timeouts for nothing."""
    budget = cw._FetchBudget(max_consecutive_failures=1)
    budget.record(usable=False)
    assert budget.exhausted

    with mock.patch.object(cw, "recent_videos", return_value=_videos(("e1", "Live"))), \
         mock.patch.object(cw, "fetch_transcript") as fetch:
        assert cw.pick_episode("CID", budget=budget) is None
    fetch.assert_not_called()


def test_fetch_budget_resets_after_a_usable_transcript():
    budget = cw._FetchBudget(max_consecutive_failures=2)
    budget.record(usable=False)
    budget.record(usable=True)
    budget.record(usable=False)
    assert not budget.exhausted


def test_signals_never_persist_creator_transcripts(tmp_path):
    """Signals land in the digest artifact. Their words must not."""
    episode = {
        "video_id": "e1", "title": "Pastor tithes backlash",
        "published": _iso(2),
        "transcript": "pastor pastor pastor tithes tithes tithes church church church",
    }
    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Chan": "CID"}), \
         mock.patch.object(cw, "recent_videos", return_value=[]), \
         mock.patch.object(cw, "pick_episode", return_value=episode):
        signals = cw.creator_topic_signals(tmp_path / "state.json")

    assert signals["Chan"]["topics"]
    assert "transcript" not in signals["Chan"]
    # ...and not into the remembered state either, which outlives the run.
    assert "transcript" not in (tmp_path / "state.json").read_text()


def test_signals_skip_channels_with_no_usable_episode(tmp_path):
    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Chan": "CID"}), \
         mock.patch.object(cw, "recent_videos", return_value=[]), \
         mock.patch.object(cw, "pick_episode", return_value=None):
        assert cw.creator_topic_signals(tmp_path / "state.json") == {}


# ── remembering episodes between runs ────────────────────────────────────────

def test_an_episode_still_counts_on_the_nights_after_it_airs(tmp_path):
    """The reason this exists: Funky Dineva goes live ~5 nights a week, and a
    36h window meant a Tuesday episode was invisible by Thursday."""
    state = tmp_path / "state.json"
    videos = _videos(("live1", "Dineva LIVE: pastor tithes backlash"))

    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Dineva": "CID"}), \
         mock.patch.object(cw, "recent_videos", return_value=videos), \
         mock.patch.object(cw, "fetch_transcript",
                           return_value=_on_beat(500)) as fetch:
        first = cw.creator_topic_signals(state)
        assert fetch.call_count == 1

        # Next night: nothing new posted. The episode is still current, so it
        # still contributes — and without a second caption fetch.
        second = cw.creator_topic_signals(state)
        assert fetch.call_count == 1

    assert first["Dineva"]["topics"] == second["Dineva"]["topics"]
    assert second["Dineva"]["video_id"] == "live1"


def test_a_new_episode_replaces_the_remembered_one(tmp_path):
    state = tmp_path / "state.json"
    on_beat = _on_beat(500)

    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Dineva": "CID"}):
        with mock.patch.object(cw, "recent_videos",
                               return_value=_videos(("old", "Older episode"))), \
             mock.patch.object(cw, "fetch_transcript", return_value=on_beat):
            cw.creator_topic_signals(state)

        # A newer non-Short appears — it must win over the remembered episode.
        newer = _videos(("new", "Newer episode"), ("old", "Older episode"))
        with mock.patch.object(cw, "recent_videos", return_value=newer), \
             mock.patch.object(cw, "fetch_transcript", return_value=on_beat) as fetch:
            signals = cw.creator_topic_signals(state)

    assert signals["Dineva"]["video_id"] == "new"
    fetch.assert_called_once_with("new")


def test_a_short_posted_after_the_episode_does_not_discard_it(tmp_path):
    """A Short is not "something newer worth reading" — without this the
    channel would lose its episode the moment it posted a clip."""
    state = tmp_path / "state.json"
    on_beat = _on_beat(500)

    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Dineva": "CID"}):
        with mock.patch.object(cw, "recent_videos",
                               return_value=_videos(("live1", "The episode"))), \
             mock.patch.object(cw, "fetch_transcript", return_value=on_beat):
            cw.creator_topic_signals(state)

        with_short = _videos(("clip", "Best bit #shorts"), ("live1", "The episode"))
        with mock.patch.object(cw, "recent_videos", return_value=with_short), \
             mock.patch.object(cw, "fetch_transcript") as fetch:
            signals = cw.creator_topic_signals(state)

    assert signals["Dineva"]["video_id"] == "live1"
    fetch.assert_not_called()


def test_an_unusable_new_upload_falls_back_to_the_remembered_episode(tmp_path):
    """A vacation vlog posted after the real episode shouldn't cost the channel
    its signal — it should just fail to replace it."""
    state = tmp_path / "state.json"
    on_beat = _on_beat(500)
    off_beat = " ".join(["sandwich", "camera", "beach"] * 200)

    with mock.patch.object(cw, "WATCHED_CHANNELS", {"Dineva": "CID"}):
        with mock.patch.object(cw, "recent_videos",
                               return_value=_videos(("live1", "The episode"))), \
             mock.patch.object(cw, "fetch_transcript", return_value=on_beat):
            cw.creator_topic_signals(state)

        newer = _videos(("vlog", "Antigua day 3"), ("live1", "The episode"))
        with mock.patch.object(cw, "recent_videos", return_value=newer), \
             mock.patch.object(cw, "fetch_transcript", return_value=off_beat):
            signals = cw.creator_topic_signals(state)

    assert signals["Dineva"]["video_id"] == "live1"


def test_a_remembered_episode_expires_once_it_leaves_the_window():
    """Otherwise a channel that stopped posting would lift stories forever."""
    fresh = {"video_id": "a", "title": "t", "published": _iso(10), "topics": ["x"]}
    stale = {"video_id": "b", "title": "t",
             "published": _iso(cw.MAX_VIDEO_AGE_HOURS + 12), "topics": ["y"]}
    kept = cw.prune_state({"FRESH": fresh, "STALE": stale})
    assert list(kept) == ["FRESH"]


def test_undated_state_entries_are_dropped_rather_than_trusted():
    assert cw.prune_state({"C": {"video_id": "a", "topics": ["x"]}}) == {}
    assert cw.prune_state({"C": {"published": "not-a-date", "topics": ["x"]}}) == {}


def test_unreadable_state_is_not_fatal(tmp_path):
    bad = tmp_path / "state.json"
    bad.write_text("{not json")
    assert cw.load_state(bad) == {}
    assert cw.load_state(tmp_path / "missing.json") == {}


def test_window_is_wide_enough_for_a_five_nights_a_week_channel():
    # Guards the actual regression: at 36h a Tuesday episode was already gone
    # by Thursday's 8pm run. 96h covers a mid-week miss; 120h also covers a
    # weekend gap for a channel that posts ~5 nights a week.
    assert cw.MAX_VIDEO_AGE_HOURS >= 96


def test_filler_topics_are_dropped_from_a_real_sized_digest():
    """Regression: a watched channel on vacation lifted 19% of a live digest
    on words like "only" and "used" before this filter existed."""
    stories = [(f"Story {i} about only used things", "", 0.5) for i in range(30)]
    digest = _digest(*stories)
    signals = {"Chan": {"video_id": "v", "title": "t", "published": "p",
                        "topics": ["only", "used"]}}
    out = cw.boost_candidates(digest, signals)
    assert not [i for i in out["items"] if "creator_signal" in i]
    assert out["creator_watch"]["Chan"]["topics"] == []


def test_rare_topics_survive_the_digest_share_filter():
    stories = [(f"Story {i} about only used things", "", 0.5) for i in range(30)]
    stories[0] = ("School board banned the books", "", 0.5)
    digest = _digest(*stories)
    signals = {"Chan": {"video_id": "v", "title": "t", "published": "p",
                        "topics": ["school", "board", "only"]}}
    out = cw.boost_candidates(digest, signals)
    boosted = [i for i in out["items"] if "creator_signal" in i]
    assert len(boosted) == 1
    assert sorted(boosted[0]["creator_signal"]["matched_topics"]) == ["board", "school"]
