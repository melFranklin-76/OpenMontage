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
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ── constants ────────────────────────────────────────────────────────────────

PIPER_MODEL_DIR = Path.home() / ".piper" / "models"
DEFAULT_PIPER_MODEL = PIPER_MODEL_DIR / "en_US-lessac-medium.onnx"

# Per-lane voice picks. Falls back to lessac if the mapped model is missing.
# lessac  = neutral female, dignified
# amy     = warm female
# ryan    = warm male
LANE_VOICE = {
    "gay":         "en_US-ryan-high.onnx",
    "lesbian":     "en_US-amy-medium.onnx",
    "bisexual":    "en_US-amy-medium.onnx",
    "Black trans": "en_US-amy-medium.onnx",
    "legacy":      "en_US-lessac-medium.onnx",
}


def _fetch_hero_image(url: str, out_path: Path, timeout: int = 15) -> Path | None:
    """Try to grab an og:image from the story URL. Returns None on failure.

    No external deps: parses <meta property="og:image"...> with a regex on the
    fetched HTML. Skips gracefully if the site blocks bots or has no og:image.
    """
    if not url:
        return None
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; fish-pipeline/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read(200_000).decode("utf-8", errors="replace")
        m = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        ) or re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html, re.IGNORECASE,
        )
        if not m:
            return None
        img_url = urllib.parse.urljoin(url, m.group(1))
        img_req = urllib.request.Request(img_url, headers=req.headers)
        with urllib.request.urlopen(img_req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 2000:
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path
    except Exception as exc:  # noqa: BLE001
        print(f"[reel_render] hero image fetch failed: {exc}", file=sys.stderr)
        return None


def _prepare_hero_bg(img_src: Path, out_png: Path, bg_hex: str) -> None:
    """Crop-cover the hero image to 1080x1920 with a lane-tinted vignette."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(img_src).convert("RGB")
    # Cover-fit into 1080x1920 (crop overflow)
    tw, th = WIDTH, HEIGHT
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - tw) // 2
    y = (nh - th) // 2
    img = img.crop((x, y, x + tw, y + th))
    # Slight desaturation + darken so captions read
    img = ImageEnhance.Color(img).enhance(0.85)
    img = ImageEnhance.Brightness(img).enhance(0.55)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    # Lane-tinted overlay at 25%
    r = int(bg_hex[2:4], 16); g = int(bg_hex[4:6], 16); b = int(bg_hex[6:8], 16)
    tint = Image.new("RGB", (tw, th), (r, g, b))
    img = Image.blend(img, tint, 0.35)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")


def _render_brand_card(title: str, subtitle: str, out_png: Path, bg_hex: str) -> None:
    """Render a full-frame brand/title card as PNG."""
    from PIL import Image, ImageDraw, ImageFont

    r = int(bg_hex[2:4], 16); g = int(bg_hex[4:6], 16); b = int(bg_hex[6:8], 16)
    img = Image.new("RGBA", (WIDTH, HEIGHT), (r, g, b, 255))
    draw = ImageDraw.Draw(img)

    def _font(size: int):
        for cand in (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            if Path(cand).exists():
                try:
                    return ImageFont.truetype(cand, size)
                except OSError:
                    pass
        return ImageFont.load_default()

    title_font = _font(96)
    sub_font = _font(48)

    # Wrap the title
    lines = _wrap_words(title, chars_per_line=18)
    line_h = 108
    block_h = len(lines) * line_h
    y0 = (HEIGHT - block_h) // 2 - 100
    for i, ln in enumerate(lines):
        tw = draw.textbbox((0, 0), ln, font=title_font)[2]
        x = (WIDTH - tw) // 2
        draw.text((x, y0 + i * line_h), ln, fill=(255, 255, 255, 255), font=title_font)

    # Subtitle
    sw = draw.textbbox((0, 0), subtitle, font=sub_font)[2]
    draw.text(
        ((WIDTH - sw) // 2, y0 + block_h + 60),
        subtitle, fill=(255, 255, 255, 220), font=sub_font,
    )

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def _voice_for_lane(lane: str) -> Path:
    """Return the Piper voice for a lane, falling back to lessac."""
    preferred = PIPER_MODEL_DIR / LANE_VOICE.get(lane, DEFAULT_PIPER_MODEL.name)
    if preferred.exists():
        return preferred
    return DEFAULT_PIPER_MODEL

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

BRAND_LEAD_SECONDS = 2.0        # Title card at head
BRAND_OUTRO_SECONDS = 3.0       # Hashtag card at tail
MUSIC_DUCK_DB = -18             # Music level under voice


# ── helpers ──────────────────────────────────────────────────────────────────

def _check_bin(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"[reel_render] required binary not on PATH: {name}")


def _piper_tts(text: str, out_wav: Path, model: Path | None = None) -> None:
    """Generate a WAV from text using Piper. Raises on failure."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    model = model or DEFAULT_PIPER_MODEL
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

def render_reel(
    script: dict,
    output: Path,
    tmp_dir: Path,
    music_path: Path | None = None,
) -> dict:
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
    voice = _voice_for_lane(lane)

    # 1. TTS each section, measure actual duration
    seg_wavs: list[Path] = []
    seg_durations: list[float] = []
    for i, sec in enumerate(sections):
        wav = tmp_dir / f"seg_{i:02d}_{sec['id']}.wav"
        _piper_tts(sec["narration"], wav, model=voice)
        dur = _wav_duration(wav)
        seg_wavs.append(wav)
        seg_durations.append(dur)
        print(f"  [{sec['id']}] {dur:.1f}s → {wav.name}")

    total = sum(seg_durations)

    # 2. Concat all wavs into a single voiceover track,
    #    padded by BRAND_LEAD/OUTRO of silence for the title/outro cards.
    concat_list = tmp_dir / "concat.txt"
    concat_list.write_text("".join(f"file '{w}'\n" for w in seg_wavs))
    voice_raw = tmp_dir / "voice_raw.wav"
    # Re-encode to a uniform PCM format instead of stream-copying:
    # different Piper voices can emit different sample rates (lessac/amy
    # 22050 Hz, ryan-high 22050 Hz but could shift), and concat -c copy
    # requires identical codecs / sample rates / channel layouts. Ubuntu
    # CI ffmpeg is stricter than macOS about this and errors out. Re-encoding
    # to 22050/mono is lossless-adjacent for Piper output and always works.
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", str(voice_raw)],
        check=True, capture_output=True,
    )
    voice_wav = tmp_dir / "voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(voice_raw),
         "-af", f"adelay={int(BRAND_LEAD_SECONDS*1000)}|{int(BRAND_LEAD_SECONDS*1000)},"
                f"apad=pad_dur={BRAND_OUTRO_SECONDS}",
         str(voice_wav)],
        check=True, capture_output=True,
    )
    total_padded = BRAND_LEAD_SECONDS + total + BRAND_OUTRO_SECONDS

    # 3. Pre-render each caption as a transparent PNG + brand cards
    caption_pngs: list[Path] = []
    for i, sec in enumerate(sections):
        png = tmp_dir / f"cap_{i:02d}.png"
        _render_caption_png(sec["narration"], png)
        caption_pngs.append(png)

    # Brand lead card + hashtag outro card (full-frame opaque overlays)
    lead_card = tmp_dir / "brand_lead.png"
    _render_brand_card(
        title=script.get("topic", "")[:80],
        subtitle="What's the LGBT, Fish?",
        out_png=lead_card,
        bg_hex=bg,
    )
    hashtags = " ".join(script.get("hashtags", [])[:4])
    outro_card = tmp_dir / "brand_outro.png"
    _render_brand_card(
        title=hashtags or "#whatsthelgbtfish",
        subtitle="Follow for daily LGBT news",
        out_png=outro_card,
        bg_hex=bg,
    )

    # 3.5 Try to fetch a hero image from the story URL for Ken Burns background
    story_url = (
        script.get("source_attribution", {}).get("url")
        or script.get("story_url", "")
    )
    hero_bg = tmp_dir / "hero_bg.png"
    hero_src = _fetch_hero_image(story_url, tmp_dir / "hero_raw.bin") if story_url else None
    have_hero = False
    if hero_src:
        try:
            _prepare_hero_bg(hero_src, hero_bg, bg)
            have_hero = True
        except Exception as exc:  # noqa: BLE001
            print(f"[reel_render] hero prep failed, using solid bg: {exc}", file=sys.stderr)

    # 4. Compose: bg + voice + PNG overlays, each on its own time window
    output.parent.mkdir(parents=True, exist_ok=True)

    if have_hero:
        # Ken Burns: slow zoom-in over the entire duration
        frames = int(total_padded * FPS)
        zoompan = (
            f"scale={WIDTH * 2}x{HEIGHT * 2},"
            f"zoompan=z='min(zoom+0.0006,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':"
            f"s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
        inputs: list[str] = [
            "-loop", "1", "-t", f"{total_padded:.3f}", "-i", str(hero_bg),
            "-i", str(voice_wav),
        ]
        bg_filter_prefix = f"[0:v]{zoompan}[bg];"
        bg_label = "bg"
    else:
        inputs = [
            "-f", "lavfi", "-i",
            f"color=c={bg}:s={WIDTH}x{HEIGHT}:r={FPS}:d={total_padded:.3f}",
            "-i", str(voice_wav),
        ]
        bg_filter_prefix = ""
        bg_label = "0:v"

    # Add brand lead + outro cards + captions as extra inputs
    extra_pngs = [lead_card] + caption_pngs + [outro_card]
    for png in extra_pngs:
        inputs += ["-i", str(png)]

    # Add music track as last input if provided
    music_input_idx = None
    if music_path and music_path.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_input_idx = 2 + len(extra_pngs) + 1  # +1 for voice, +1 for music
    for png in caption_pngs:
        inputs += ["-i", str(png)]

    # Build overlay chain — layer 0 = lead card (0..BRAND_LEAD),
    # layers 1..N = section captions (each on its own window, offset by BRAND_LEAD),
    # layer N+1 = outro card (last BRAND_OUTRO seconds).
    filter_parts: list[str] = []
    prev_label = bg_label
    # extra_pngs starts at input index 2 (0=bg, 1=voice audio)
    lead_idx = 2
    outro_idx = 2 + 1 + len(caption_pngs)

    # Lead card
    filter_parts.append(
        f"[{prev_label}][{lead_idx}:v]"
        f"overlay=enable='between(t,0,{BRAND_LEAD_SECONDS:.3f})'"
        f"[vlead]"
    )
    prev_label = "vlead"

    # Captions
    t_cursor = BRAND_LEAD_SECONDS
    for i, dur in enumerate(seg_durations):
        start, end = t_cursor, t_cursor + dur
        in_idx = lead_idx + 1 + i
        out_label = f"v{i}"
        filter_parts.append(
            f"[{prev_label}][{in_idx}:v]"
            f"overlay=enable='between(t,{start:.3f},{end:.3f})'"
            f"[{out_label}]"
        )
        prev_label = out_label
        t_cursor = end

    # Outro card
    outro_start = t_cursor
    outro_end = total_padded
    filter_parts.append(
        f"[{prev_label}][{outro_idx}:v]"
        f"overlay=enable='between(t,{outro_start:.3f},{outro_end:.3f})'"
        f"[vfinal]"
    )
    final_v = "[vfinal]"

    filter_complex = bg_filter_prefix + ";".join(filter_parts)

    # Audio: mix voice + optional ducked music
    audio_map = "1:a"
    if music_input_idx is not None:
        filter_complex += (
            f";[{music_input_idx}:a]volume={MUSIC_DUCK_DB}dB,"
            f"atrim=0:{total_padded:.3f},asetpts=PTS-STARTPTS[mus];"
            f"[1:a][mus]amix=inputs=2:duration=first:dropout_transition=0[amix]"
        )
        audio_map = "[amix]"

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", filter_complex,
        "-map", final_v, "-map", audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_padded:.3f}",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"[reel_render] ffmpeg failed:\n{proc.stderr[-2000:]}")

    return {
        "output": str(output),
        "duration_seconds": round(total_padded, 2),
        "voice_seconds": round(total, 2),
        "sections": len(sections),
        "lane": lane,
        "topic": script.get("topic", ""),
        "background_color": bg,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "voice_model": voice.name,
        "hero_image": have_hero,
        "brand_cards": True,
        "music_bed": music_input_idx is not None,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Render a FISH reel_script to MP4")
    parser.add_argument("--script", required=True, help="Path to a reel_script JSON")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--tmp-dir", default="", help="Working dir (default: alongside output)")
    parser.add_argument(
        "--music", default="",
        help="Optional music bed .mp3/.wav (ducked -18dB under voice)",
    )
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text())
    output = Path(args.output)
    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else output.parent / f".{output.stem}_work"
    music = Path(args.music) if args.music else None

    report = render_reel(script, output, tmp_dir, music_path=music)
    print(f"\n[reel_render] wrote {report['output']} ({report['duration_seconds']}s)")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
