import sys
from types import ModuleType

from studio.fish.long_roundup_render import (
    HEIGHT,
    WIDTH,
    _darken_eq,
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
