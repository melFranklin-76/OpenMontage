import sys
from types import ModuleType

from studio.fish.long_roundup_render import (
    FPS,
    HEIGHT,
    WIDTH,
    _darken_eq,
    _hero_ken_burns_filter,
    _normalize_segment,
    _render_transparent_overlay,
)


def test_render_transparent_overlay_creates_clear_full_size_png(monkeypatch, tmp_path) -> None:
    output = tmp_path / "overlay.png"
    calls: dict[str, object] = {}

    class FakeImage:
        @staticmethod
        def new(mode, size, color):
            calls.update(mode=mode, size=size, color=color)
            return FakeImage()

        def save(self, path) -> None:
            calls["path"] = path

    fake_pil = ModuleType("PIL")
    fake_pil.Image = FakeImage
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)

    _render_transparent_overlay(output)

    assert calls == {
        "mode": "RGBA",
        "size": (WIDTH, HEIGHT),
        "color": (0, 0, 0, 0),
        "path": output,
    }


def test_darken_eq_shifts_brightness_without_changing_saturation():
    result = _darken_eq("eq=brightness=0.100:saturation=0.95", extra=-0.12)

    assert result == "eq=brightness=-0.020:saturation=0.95"


def test_darken_eq_clamps_to_ffmpeg_range():
    assert _darken_eq("eq=brightness=-0.950:saturation=0.95", -0.12) == (
        "eq=brightness=-1.000:saturation=0.95"
    )


def test_darken_eq_leaves_unknown_filter_unchanged():
    assert _darken_eq("eq=saturation=0.95", -0.12) == "eq=saturation=0.95"


def test_normalize_segment_forces_square_pixels_and_concat_pixel_format():
    assert _normalize_segment("vraw7", "vseg7") == (
        "[vraw7]setsar=1,format=yuv420p[vseg7]"
    )


def test_hero_ken_burns_filter_clamps_duration_to_prevent_zoompan_overrun():
    # Regression guard for the hero-leak bug: zoompan emits `d` frames for every
    # input frame, and the hero input is looped (`-loop 1 -t dur`). Without a
    # `trim=duration`/`setpts` clamp the first body segment out-runs the whole
    # `-t total` output, so concat never advances and every story shows story
    # 1's hero. The Ken Burns chain MUST clamp each segment to its duration.
    f = _hero_ken_burns_filter(hero_in=9, vis_in=3, dur=4.0, seg_index=3, raw_label="vraw3")
    assert "zoompan=" in f
    assert "trim=duration=4.000" in f
    assert "setpts=PTS-STARTPTS[hero3]" in f
    # The clamp must apply before the hero label is overlaid/consumed.
    assert f.index("trim=duration") < f.index("[hero3][3:v]overlay")


def test_hero_ken_burns_filter_uses_distinct_inputs_and_labels():
    a = _hero_ken_burns_filter(9, 3, 4.0, 3, "vraw3")
    b = _hero_ken_burns_filter(10, 5, 4.0, 5, "vraw5")
    assert "[9:v]" in a and "[hero3]" in a and "[3:v]overlay" in a
    assert "[10:v]" in b and "[hero5]" in b and "[5:v]overlay" in b
    assert a != b


def test_hero_ken_burns_frame_count_tracks_fps_and_duration():
    assert f"d={int(2.0 * FPS)}" in _hero_ken_burns_filter(9, 3, 2.0, 3, "vraw3")
