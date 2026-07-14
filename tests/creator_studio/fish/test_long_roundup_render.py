import sys
from types import ModuleType

from studio.fish.long_roundup_render import HEIGHT, WIDTH, _render_transparent_overlay


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
