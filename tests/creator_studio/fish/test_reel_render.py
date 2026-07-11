"""Tests for FISH reel_render.

These tests validate the pure logic (word wrap, filter chain construction)
without requiring piper/ffmpeg to be installed on the CI runner. The end-to-
end MP4 render is exercised by the workflow itself.
"""

from __future__ import annotations

from studio.fish import reel_render


def test_wrap_words_caps_at_five_lines():
    text = " ".join(["word"] * 50)
    lines = reel_render._wrap_words(text, chars_per_line=10)
    assert len(lines) <= 5
    assert all(len(ln) <= 12 for ln in lines)


def test_wrap_words_respects_line_width():
    text = "the quick brown fox jumps over"
    lines = reel_render._wrap_words(text, chars_per_line=15)
    for ln in lines:
        assert len(ln) <= 15


def test_wrap_words_handles_single_long_word():
    lines = reel_render._wrap_words("supercalifragilistic", chars_per_line=10)
    assert lines == ["supercalifragilistic"]


def test_lane_bg_contains_all_lanes():
    for lane in ("gay", "lesbian", "bisexual", "trans"):
        assert lane in reel_render.LANE_BG
        assert reel_render.LANE_BG[lane].startswith("0x")


def test_no_legacy_lane_anywhere():
    for mapping in (reel_render.LANE_BG, reel_render.LANE_VOICE, reel_render.EDGE_LANE_VOICE):
        assert "legacy" not in mapping


def test_default_piper_model_path_shape():
    # Should end in an .onnx path under the user's home dir
    assert str(reel_render.DEFAULT_PIPER_MODEL).endswith(".onnx")


def test_lane_voice_map_covers_all_lanes():
    for lane in ("gay", "lesbian", "bisexual", "trans"):
        assert lane in reel_render.LANE_VOICE
        assert reel_render.LANE_VOICE[lane].endswith(".onnx")


def test_voice_for_lane_returns_edge_voice_when_available(monkeypatch):
    """With Edge TTS available, _voice_for_lane returns a voice name string."""
    monkeypatch.setattr(reel_render, "USE_EDGE_TTS", True)
    result = reel_render._voice_for_lane("gay")
    assert isinstance(result, str)
    assert "Neural" in result


def test_voice_for_lane_falls_back_to_piper(monkeypatch, tmp_path):
    """Without Edge TTS, falls back to Piper model path."""
    monkeypatch.setattr(reel_render, "USE_EDGE_TTS", False)
    monkeypatch.setattr(reel_render, "PIPER_MODEL_DIR", tmp_path)
    fallback = tmp_path / "en_US-lessac-medium.onnx"
    fallback.write_bytes(b"stub")
    monkeypatch.setattr(reel_render, "DEFAULT_PIPER_MODEL", fallback)
    result = reel_render._voice_for_lane("gay")
    assert result == fallback


def test_clean_for_tts_dates():
    assert "July 8, 2026" in reel_render._clean_for_tts("Filed on 7/8/2026 today")


def test_clean_for_tts_slashes():
    assert "lesbian and gay" in reel_render._clean_for_tts("lesbian/gay community")


def test_clean_for_tts_urls():
    result = reel_render._clean_for_tts("Visit https://example.com/path for more")
    assert "https" not in result
    assert "example" not in result


def test_clean_for_tts_abbreviations():
    assert "Governor" in reel_render._clean_for_tts("Gov. Smith signed the bill")
    assert "percent" in reel_render._clean_for_tts("75% of respondents")


def test_brand_and_music_constants():
    assert reel_render.BRAND_LEAD_SECONDS > 0
    assert reel_render.BRAND_OUTRO_SECONDS > 0
    assert reel_render.MUSIC_DUCK_DB < 0
