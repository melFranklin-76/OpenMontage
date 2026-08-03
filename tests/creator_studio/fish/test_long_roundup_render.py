import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest import mock

import pytest

from studio.fish import long_roundup_render as lrr
from studio.fish.long_roundup_render import (
    HEIGHT,
    WIDTH,
    _darken_eq,
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


needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg/ffprobe required to render a real roundup",
)


def _make_solid_png(path: Path, color: tuple[int, int, int]) -> None:
    from PIL import Image
    Image.new("RGB", (800, 500), color).save(path, format="PNG")


def _silent_wav(text: str, out_wav: Path, model=None) -> None:
    """Stand-in for _piper_tts: a short silent WAV, no TTS engine needed."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
         "-t", "1.2", "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le",
         str(out_wav)],
        capture_output=True, check=True,
    )


@needs_ffmpeg
@pytest.mark.slow
def test_hero_image_does_not_bleed_into_following_sections(tmp_path):
    """Regression: zoompan's `d` is frames *per input frame*, not total output
    frames. A `-loop 1 -t {dur} -i hero.png` input still delivers
    dur * default-image2-fps (25) discrete frames, so without an explicit trim
    after the overlay a chN_body segment rendered ~25-30x longer than its slot
    and swallowed every following section's screen time in the concat —
    indistinguishable from "the wrong story's image shows up later".
    """
    rank_colors = {1: (220, 30, 30), 2: (30, 30, 220)}

    def fake_hero(url: str, out_path: Path, timeout: int = 15):
        _make_solid_png(out_path, rank_colors[int(url.rsplit("rank", 1)[-1])])
        return out_path

    def story(rank, lane, title):
        return {"rank": rank, "lane": lane, "title": title,
                "url": f"https://example.com/rank{rank}", "summary": ""}

    script = {
        "story_count": 2,
        "hashtags": ["#test"],
        "stories": [story(1, "gay", "Story one"), story(2, "lesbian", "Story two")],
        "sections": [
            {"id": "cold_open", "narration": "Cold open."},
            {"id": "intro", "narration": "Intro."},
            {"id": "ch1_title", "narration": "Story one.", "story_rank": 1, "lane": "gay"},
            {"id": "ch1_body", "narration": "Body one.", "story_rank": 1, "lane": "gay"},
            {"id": "ch1_transition", "narration": "Next.", "story_rank": 1},
            {"id": "ch2_title", "narration": "Story two.", "story_rank": 2, "lane": "lesbian"},
            {"id": "ch2_body", "narration": "Body two.", "story_rank": 2, "lane": "lesbian"},
            {"id": "outro", "narration": "Outro."},
        ],
    }

    output = tmp_path / "roundup.mp4"
    # Narration is mocked out, so skip the real TTS engine's binary precheck.
    with mock.patch.object(lrr, "USE_EDGE_TTS", True), \
         mock.patch.object(lrr, "_fetch_hero_image", fake_hero), \
         mock.patch.object(lrr, "_piper_tts", _silent_wav), \
         mock.patch.object(lrr, "resolve_story_media", lambda *a, **k: None), \
         mock.patch.object(lrr, "fetch_broll_for_story", lambda **k: None), \
         mock.patch.object(lrr, "mentions_public_person", lambda *a, **k: False):
        report = lrr.render_roundup(script, output, tmp_path / "work")

    # The bug inflated real length ~25-30x while the voice-derived duration
    # stayed short, so container duration is the sharpest, cheapest signal.
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(output)],
        capture_output=True, text=True, check=True,
    )
    actual = float(probe.stdout.strip())
    assert actual <= report["duration_seconds"] + 1.0, (
        f"final video ({actual:.2f}s) far exceeds the voice duration "
        f"({report['duration_seconds']:.2f}s) — a hero segment overran its slot"
    )

    def sample(t: float) -> tuple[int, int, int]:
        from PIL import Image
        frame = tmp_path / f"frame_{t:.2f}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", str(output),
             "-frames:v", "1", str(frame)],
            capture_output=True, check=True,
        )
        img = Image.open(frame).convert("RGB")
        return img.getpixel((img.size[0] // 2, int(img.size[1] * 0.3)))

    samples = {sec["id"]: sample(0.6 + 1.2 * i)
               for i, sec in enumerate(script["sections"])}

    def reddish(px):
        r, g, b = px
        return r > g + 20 and r > b + 20

    def bluish(px):
        r, g, b = px
        return b > r + 20 and b > g + 20

    # Each rank's hero belongs in its own body slot and nowhere else.
    assert reddish(samples["ch1_body"]), samples["ch1_body"]
    assert bluish(samples["ch2_body"]), samples["ch2_body"]
    assert not reddish(samples["ch1_transition"]), samples["ch1_transition"]
    assert not reddish(samples["ch2_title"]), samples["ch2_title"]
    assert not reddish(samples["outro"]), samples["outro"]
