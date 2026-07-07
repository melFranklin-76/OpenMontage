"""FISH reel renderer — smoke-test stage.

Takes a reel_script.json (from reel_script.py) and produces a 9:16 MP4:
  - Piper TTS voiceover for each section (locally, no API keys)
  - ffmpeg concat + burned captions on a lane-tinted background

This is the deterministic-local floor per AGENT_GUIDE: a real MP4 out,
not more placeholder JSON. Later revisions can swap the background layer
for SD-Turbo b-roll and route through Remotion, but the audio + caption +
compose spine stays the same.

Usage:
    python -m studio.fish.reel_render \\
      --script fish-script-rank1.json \\
      --output out/fish/2026-07-07/rank1.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────

DEFAULT_PIPER_MODEL = Path.home() / ".piper" / "models" / "en_US-lessac-medium.onnx"

# 9:16 vertical, Reels-safe
WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Lane background tints (dark, high-contrast for white captions)
LANE_BG = {
    "gay":         "0x1a1a3e",   # deep blue
    "lesbian":     "0x3e1a2a",   # deep magenta
    "bisexual":    "0x2a1a3e",   # deep purple
    "Black trans": "0x1a3e2a",   # deep green
    "legacy":      "0x3e2a1a",   # deep amber
}
DEFAULT_BG = "0x111111"

# Caption band at bottom third
CAPTION_Y_FRAC = 0.55
CAPTION_FONTSIZE = 56


# ── helpers ──────────────────────────────────────────────────────────────────

def _check_bin(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"[reel_render] required binary not on PATH: {name}")


def _piper_tts(text: str, out_wav: Path, model: Path = DEFAULT_PIPER_MODEL) -> None:
    """Generate a WAV from text using Piper. Raises on failure."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["piper", "-m", str(model), "-f", str(out_wav)],
        input=text,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"Piper failed: {proc.stderr}")


def _wav_duration(wav: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(wav),
        ],
        capture_output=True, text=True, timeout=15,
    )
    return float(proc.stdout.strip())


def _wrap_words(text: str, chars_per_line: int = 22) -> list[str]:
    """Word-wrap into a list of lines (capped at 5 lines)."""
    words, lines, current = text.split(), [], ""
    for w in words:
        if not current:
            current = w
        elif len(current) + 1 + len(w) <= chars_per_line:
            current += " " + w
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines[:5]


def _render_caption_png(text: str, out_png: Path) -> None:
    """Render a caption as a transparent PNG the width of the video.

    Uses PIL — no fancy font loading required, falls back to the default bitmap
    font if no system font is found. This is the smoke-test tier; typography
    comes later.
    """
    from PIL import Image, ImageDraw, ImageFont

    # Find a bundled system font
    font = None
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ):
        if Path(candidate).exists():
            try:
                font = ImageFont.truetype(candidate, CAPTION_FONTSIZE)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    lines = _wrap_words(text)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Measure block height
    line_h = int(CAPTION_FONTSIZE * 1.25)
    block_h = line_h * len(lines)
    pad_x, pad_y = 40, 30

    # Compute widest line
    widest = max(
        (draw.textbbox((0, 0), ln, font=font)[2] for ln in lines),
        default=0,
    )
    box_w = widest + pad_x * 2
    box_h = block_h + pad_y * 2
    box_x = (WIDTH - box_w) // 2
    box_y = int(HEIGHT * CAPTION_Y_FRAC)

    # Semi-transparent black backdrop
    draw.rounded_rectangle(
        [(box_x, box_y), (box_x + box_w, box_y + box_h)],
        radius=24,
        fill=(0, 0, 0, 165),
    )

    # Draw each line centred inside the box
    for i, ln in enumerate(lines):
        tw = draw.textbbox((0, 0), ln, font=font)[2]
        tx = box_x + (box_w - tw) // 2
        ty = box_y + pad_y + i * line_h
        draw.text((tx, ty), ln, fill=(255, 255, 255, 255), font=font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


# ── render ───────────────────────────────────────────────────────────────────

def render_reel(script: dict, output: Path, tmp_dir: Path) -> dict:
    """Render a FISH reel_script to an MP4. Returns render report."""
    _check_bin("piper")
    _check_bin("ffmpeg")
    _check_bin("ffprobe")

    if not DEFAULT_PIPER_MODEL.exists():
        sys.exit(f"[reel_render] Piper voice not found: {DEFAULT_PIPER_MODEL}")

    tmp_dir.mkdir(parents=True, exist_ok=True)
    lane = script.get("lane", "")
    sections = script.get("sections", [])
    if not sections:
        sys.exit("[reel_render] script has no sections")

    bg = LANE_BG.get(lane, DEFAULT_BG)

    # 1. TTS each section, measure actual duration
    seg_wavs: list[Path] = []
    seg_durations: list[float] = []
    for i, sec in enumerate(sections):
        wav = tmp_dir / f"seg_{i:02d}_{sec['id']}.wav"
        _piper_tts(sec["narration"], wav)
        dur = _wav_duration(wav)
        seg_wavs.append(wav)
        seg_durations.append(dur)
        print(f"  [{sec['id']}] {dur:.1f}s → {wav.name}")

    total = sum(seg_durations)

    # 2. Concat all wavs into a single voiceover track
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{w}'\n" for w in seg_wavs))
    voice_wav = tmp_dir / "voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(voice_wav)],
        check=True, capture_output=True,
    )

    # 3. Pre-render each caption as a transparent PNG
    caption_pngs: list[Path] = []
    for i, sec in enumerate(sections):
        png = tmp_dir / f"cap_{i:02d}.png"
        _render_caption_png(sec["narration"], png)
        caption_pngs.append(png)

    # 4. Compose: solid bg + voice + PNG overlays, each on its own time window
    output.parent.mkdir(parents=True, exist_ok=True)

    inputs: list[str] = [
        "-f", "lavfi", "-i", f"color=c={bg}:s={WIDTH}x{HEIGHT}:r={FPS}:d={total:.3f}",
        "-i", str(voice_wav),
    ]
    for png in caption_pngs:
        inputs += ["-i", str(png)]

    # Build overlay chain: [0:v][2:v] overlay ...  [t][3:v] overlay ...
    filter_parts: list[str] = []
    prev_label = "0:v"
    t_cursor = 0.0
    for i, dur in enumerate(seg_durations):
        start, end = t_cursor, t_cursor + dur
        in_label = f"{i + 2}:v"          # inputs 0=bg, 1=audio, 2+=pngs
        out_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{in_label}]"
            f"overlay=enable='between(t,{start:.3f},{end:.3f})'"
            f"[{out_label}]"
        )
        prev_label = out_label
        t_cursor = end

    filter_complex = ";".join(filter_parts)
    final_v = f"[{prev_label}]"

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", final_v, "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"[reel_render] ffmpeg failed:\n{proc.stderr[-2000:]}")

    return {
        "output": str(output),
        "duration_seconds": round(total, 2),
        "sections": len(sections),
        "lane": lane,
        "topic": script.get("topic", ""),
        "background_color": bg,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "voice_model": DEFAULT_PIPER_MODEL.name,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Render a FISH reel_script to MP4")
    parser.add_argument("--script", required=True, help="Path to a reel_script JSON")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--tmp-dir", default="", help="Working dir (default: alongside output)")
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text())
    output = Path(args.output)
    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else output.parent / f".{output.stem}_work"

    report = render_reel(script, output, tmp_dir)
    print(f"\n[reel_render] wrote {report['output']} ({report['duration_seconds']}s)")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
