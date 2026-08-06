"""Tests for host-recorded narration intake."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from studio.fish import voice_intake as vi


# ── discovering takes ────────────────────────────────────────────────────────

def _touch(directory: Path, name: str, mtime: float | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"\0")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_find_takes_keys_on_the_number_not_the_name(tmp_path):
    _touch(tmp_path, "001-cold-open.wav")
    _touch(tmp_path, "002-whatever the host called it.m4a")
    _touch(tmp_path, "010-story-five-body.mp3")
    found = vi.find_takes(tmp_path)
    assert sorted(found) == [1, 2, 10]
    assert found[2].suffix == ".m4a"


def test_find_takes_ignores_notes_and_unnumbered_files(tmp_path):
    _touch(tmp_path, "001-intro.wav")
    _touch(tmp_path, "notes.txt")
    _touch(tmp_path, "scratch.wav")          # no leading number
    _touch(tmp_path, ".DS_Store")
    assert sorted(vi.find_takes(tmp_path)) == [1]


def test_newest_file_wins_when_a_line_is_re_recorded(tmp_path):
    """Dropping 003-body-v2.wav next to 003-body.wav should do the obvious thing."""
    now = time.time()
    _touch(tmp_path, "003-body.wav", mtime=now - 600)
    newer = _touch(tmp_path, "003-body-v2.wav", mtime=now)
    assert vi.find_takes(tmp_path)[3] == newer


def test_missing_takes_are_reported_not_silently_skipped(tmp_path):
    _touch(tmp_path, "001-a.wav")
    _touch(tmp_path, "003-c.wav")
    result = vi.match_takes(4, tmp_path)
    assert sorted(result.takes) == [1, 3]
    assert result.missing == [2, 4]
    assert not result.complete
    assert "002" in result.describe() and "004" in result.describe()


def test_takes_beyond_the_script_are_flagged(tmp_path):
    """An extra file usually means the host's numbering drifted."""
    _touch(tmp_path, "001-a.wav")
    _touch(tmp_path, "002-b.wav")
    _touch(tmp_path, "003-c.wav")
    result = vi.match_takes(2, tmp_path)
    assert result.unexpected == [3]
    assert not result.complete


def test_complete_take_set(tmp_path):
    for i in range(1, 4):
        _touch(tmp_path, f"{i:03d}-section.wav")
    result = vi.match_takes(3, tmp_path)
    assert result.complete
    assert result.describe() == "all 3 sections recorded"


def test_missing_folder_is_not_an_error(tmp_path):
    assert vi.find_takes(tmp_path / "not-recorded-yet") == {}


def test_takes_dir_layout(tmp_path):
    assert vi.takes_dir("2026-08-03", "short-1", tmp_path) == (
        tmp_path / "voice" / "2026-08-03" / "short-1"
    )


# ── caption timings ──────────────────────────────────────────────────────────

def test_word_timings_span_the_whole_take():
    words = vi.word_timings("one two three four", 4.0)
    assert len(words) == 4
    assert words[0]["startMs"] == 0.0
    assert words[-1]["endMs"] == pytest.approx(4000, abs=1)


def test_long_words_get_more_screen_time_than_short_ones():
    """Even spacing gave "a" the same time as "extraordinarily", which reads
    as drift against a real delivery."""
    words = vi.word_timings("a extraordinarily", 4.0)
    short = words[0]["endMs"] - words[0]["startMs"]
    long = words[1]["endMs"] - words[1]["startMs"]
    assert long > short * 3


def test_word_timings_are_contiguous():
    words = vi.word_timings("the school board banned the books", 6.0)
    for earlier, later in zip(words, words[1:]):
        assert later["startMs"] == pytest.approx(earlier["endMs"], abs=0.2)


def test_word_timings_handle_empty_and_zero_duration():
    assert vi.word_timings("", 4.0) == []
    assert vi.word_timings("some words", 0) == []


# ── recording script ─────────────────────────────────────────────────────────

SCRIPT = {
    "sections": [
        {"id": "cold_open", "narration": "Tonight on the show."},
        {"id": "ch1_body", "narration": "The school board voted.", "lane": "gay"},
        {"id": "outro", "narration": ""},
    ]
}


def test_recording_script_numbers_match_the_filenames_it_asks_for(tmp_path):
    out = vi.write_recording_script(
        SCRIPT, tmp_path / "rec.md", video_key="roundup", show_date="2026-08-03")
    text = out.read_text()
    # The numbering in the script is the contract for the take filenames.
    assert "## 001 — cold_open" in text
    assert "## 002 — ch1_body" in text
    assert "## 003 — outro" in text
    assert "001-anything.wav" in text
    assert "voice/2026-08-03/roundup/" in text


def test_recording_script_carries_the_words_to_read(tmp_path):
    out = vi.write_recording_script(
        SCRIPT, tmp_path / "rec.md", video_key="roundup", show_date="2026-08-03")
    text = out.read_text()
    assert "Tonight on the show." in text
    assert "The school board voted." in text
    assert "gay" in text                       # lane shown alongside the heading
    assert "_(no narration for this section)_" in text


# ── normalization (needs ffmpeg) ─────────────────────────────────────────────

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe required",
)


def _tone(path: Path, seconds: float, rate: int, channels: int) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}",
         "-t", str(seconds), "-ac", str(channels), str(path)],
        capture_output=True, check=True,
    )
    return path


@needs_ffmpeg
def test_normalize_take_conforms_odd_recordings_to_the_render_format(tmp_path):
    """The host may record at any rate, in stereo, in any container; the
    downstream ffmpeg concat assumes every narration segment matches."""
    src = _tone(tmp_path / "take.wav", 1.0, rate=48000, channels=2)
    out = vi.normalize_take(src, tmp_path / "seg.wav")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,codec_name",
         "-of", "default=noprint_wrappers=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert f"sample_rate={vi.SAMPLE_RATE}" in probe
    assert f"channels={vi.CHANNELS}" in probe
    assert f"codec_name={vi.CODEC}" in probe


@needs_ffmpeg
def test_probe_duration_reads_real_length(tmp_path):
    src = _tone(tmp_path / "take.wav", 2.0, rate=22050, channels=1)
    assert vi.probe_duration(src) == pytest.approx(2.0, abs=0.1)


@needs_ffmpeg
def test_normalize_take_fails_loudly_on_a_corrupt_file(tmp_path):
    bad = tmp_path / "001-not-audio.wav"
    bad.write_text("this is not audio")
    with pytest.raises(RuntimeError, match="could not normalize"):
        vi.normalize_take(bad, tmp_path / "seg.wav")


# ── the point of all this ────────────────────────────────────────────────────

@needs_ffmpeg
@pytest.mark.slow
def test_fully_recorded_roundup_renders_with_no_tts_engine_installed(tmp_path):
    """A host-voiced episode must not need Edge TTS or Piper to exist.

    This is the whole reason for the `_fully_recorded` guard: the renderer used
    to hard-exit on a missing `piper` binary before it ever looked at whether
    narration was already recorded.
    """
    from unittest import mock
    from studio.fish import long_roundup_render as lrr

    script = {
        "story_count": 1,
        "hashtags": ["#test"],
        "stories": [{"rank": 1, "lane": "gay", "title": "Story one",
                     "url": "https://example.com/1", "summary": ""}],
        "sections": [
            {"id": "cold_open", "narration": "Tonight on the show."},
            {"id": "ch1_title", "narration": "Story one.", "story_rank": 1,
             "lane": "gay"},
            {"id": "outro", "narration": "That is the show."},
        ],
    }

    takes = tmp_path / "takes"
    takes.mkdir()
    durations = [1.0, 2.0, 1.5]
    for i, secs in enumerate(durations, start=1):
        _tone(takes / f"{i:03d}-section.wav", secs, rate=48000, channels=2)

    take_set = vi.match_takes(len(script["sections"]), takes)
    assert take_set.complete

    def explode(*a, **k):
        raise AssertionError("TTS must not be called when every section is recorded")

    with mock.patch.object(lrr, "USE_EDGE_TTS", False), \
         mock.patch.object(lrr, "_piper_tts", explode), \
         mock.patch.object(lrr, "resolve_story_media", lambda *a, **k: None), \
         mock.patch.object(lrr, "fetch_broll_for_story", lambda **k: None), \
         mock.patch.object(lrr, "mentions_public_person", lambda *a, **k: False):
        report = lrr.render_roundup(
            script, tmp_path / "out.mp4", tmp_path / "work",
            voice_takes=take_set.takes,
        )

    # Duration comes from the host's takes, so it tracks what was recorded.
    assert report["duration_seconds"] == pytest.approx(sum(durations), abs=0.5)
    assert (tmp_path / "out.mp4").exists()
