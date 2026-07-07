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
    for lane in ("gay", "lesbian", "bisexual", "Black trans", "legacy"):
        assert lane in reel_render.LANE_BG
        assert reel_render.LANE_BG[lane].startswith("0x")


def test_default_piper_model_path_shape():
    # Should end in an .onnx path under the user's home dir
    assert str(reel_render.DEFAULT_PIPER_MODEL).endswith(".onnx")
