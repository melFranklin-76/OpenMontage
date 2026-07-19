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
import os
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

# ── TTS engine selection ────────────────────────────────────────────────────
# Prefer Edge TTS (free, neural, expressive) over Piper (free, local, robotic).
# Edge needs internet; Piper is the offline fallback.

USE_EDGE_TTS = True
try:
    import edge_tts  # noqa: F401
except ImportError:
    USE_EDGE_TTS = False

DEFAULT_EDGE_VOICE = "en-US-BrianNeural"

# Delivery pace. The default read was a touch slow for a news roundup; +10%
# is noticeably snappier while leaving the comedic pauses ("...") intact.
EDGE_TTS_RATE = "+10%"

EDGE_LANE_VOICE = {
    "gay":         "en-US-BrianNeural",
    "lesbian":     "en-US-BrianNeural",
    "bisexual":    "en-US-BrianNeural",
    "trans": "en-US-BrianNeural",
}

# Offline Piper voices (fallback when Edge TTS is unavailable)
LANE_VOICE = {
    "gay":         "en_US-ryan-high.onnx",
    "lesbian":     "en_US-amy-medium.onnx",
    "bisexual":    "en_US-amy-medium.onnx",
    "trans": "en_US-amy-medium.onnx",
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


def _render_brand_overlay(title: str, subtitle: str, out_png: Path) -> None:
    """Transparent brand card: centered text on a scrim, no full-frame fill.

    Used for the opening title beat when b-roll motion is available, so the
    reel opens over moving footage instead of a static solid color card.
    """
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
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

    lines = _wrap_words(title, chars_per_line=18)
    line_h = 108
    block_h = len(lines) * line_h + (72 if subtitle else 0)
    y0 = (HEIGHT - block_h) // 2 - 100

    widest = max(
        [draw.textbbox((0, 0), ln, font=title_font)[2] for ln in lines]
        + ([draw.textbbox((0, 0), subtitle, font=sub_font)[2]] if subtitle else [0]),
        default=0,
    )
    pad_x, pad_y = 60, 50
    box_w = min(widest + pad_x * 2, WIDTH - 60)
    box_x = (WIDTH - box_w) // 2
    draw.rounded_rectangle(
        [(box_x, y0 - pad_y), (box_x + box_w, y0 + block_h + pad_y)],
        radius=28, fill=(0, 0, 0, 140),
    )

    for i, ln in enumerate(lines):
        tw = draw.textbbox((0, 0), ln, font=title_font)[2]
        draw.text(((WIDTH - tw) // 2, y0 + i * line_h),
                  ln, fill=(255, 255, 255, 255), font=title_font)
    if subtitle:
        sw = draw.textbbox((0, 0), subtitle, font=sub_font)[2]
        draw.text(((WIDTH - sw) // 2, y0 + len(lines) * line_h + 16),
                  subtitle, fill=(255, 255, 255, 225), font=sub_font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def _voice_for_lane(lane: str) -> Path | str:
    """Return the voice for a lane — Edge TTS name or Piper model path."""
    if USE_EDGE_TTS:
        return EDGE_LANE_VOICE.get(lane, DEFAULT_EDGE_VOICE)
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
    "trans": "0x1a3e2a",   # deep green
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


def _clean_for_tts(text: str) -> str:
    """Sanitize text so TTS reads it naturally instead of spelling symbols."""
    # URLs (belt-and-suspenders with the script-level strip)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)
    # Dates with slashes: 7/8/2026 → July 8, 2026
    _MONTHS = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    def _date_repl(m: re.Match) -> str:
        mo, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= mo <= 12:
            return f"{_MONTHS[mo - 1]} {day}, {yr}"
        return m.group(0)
    text = re.sub(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", _date_repl, text)
    # Bare slashes between words: "lesbian/gay" → "lesbian and gay"
    text = re.sub(r"(\w)/(\w)", r"\1 and \2", text)
    # Ampersands
    text = re.sub(r"\s*&\s*", " and ", text)
    # Common abbreviations TTS might stumble on
    text = re.sub(r"\bvs\.", "versus", text, flags=re.IGNORECASE)
    text = re.sub(r"\bDr\.", "Doctor", text)
    text = re.sub(r"\bSt\.", "Saint", text)
    text = re.sub(r"\bGov\.", "Governor", text)
    text = re.sub(r"\bRep\.", "Representative", text)
    text = re.sub(r"\bSen\.", "Senator", text)
    # Percent sign
    text = re.sub(r"(\d)\s*%", r"\1 percent", text)
    # Dollar amounts
    text = re.sub(r"\$(\d[\d,]*(?:\.\d+)?)\s*(million|billion|trillion)?",
                  lambda m: f"{m.group(1)} {'dollars' if not m.group(2) else m.group(2) + ' dollars'}",
                  text, flags=re.IGNORECASE)
    # Clean up extra whitespace
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def _edge_tts(text: str, out_wav: Path, voice: str | None = None) -> list[dict]:
    """Generate audio via Edge TTS and convert to WAV for ffmpeg.

    Returns word-level timings [{word, startMs, endMs}, ...] harvested from
    the stream's WordBoundary events (offsets are 100-nanosecond ticks).
    They drive the Remotion word-highlight captions.
    """
    import asyncio

    voice = voice or DEFAULT_EDGE_VOICE
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    mp3_path = out_wav.with_suffix(".mp3")

    async def _generate() -> list[dict]:
        communicate = edge_tts.Communicate(text, voice, rate=EDGE_TTS_RATE)
        words: list[dict] = []
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start_ms = chunk["offset"] / 10_000
                    words.append({
                        "word": chunk["text"],
                        "startMs": round(start_ms, 1),
                        "endMs": round(start_ms + chunk["duration"] / 10_000, 1),
                    })
        return words

    words = asyncio.run(_generate())

    if not mp3_path.exists() or mp3_path.stat().st_size < 100:
        raise RuntimeError(f"Edge TTS failed for voice {voice}")

    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp3_path),
         "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
        capture_output=True, text=True, timeout=30,
    )
    mp3_path.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"Edge TTS mp3→wav conversion failed: {proc.stderr}")
    return words


def _piper_tts_raw(text: str, out_wav: Path, model: Path | None = None) -> None:
    """Generate a WAV from text using Piper (offline fallback)."""
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


def _piper_tts(text: str, out_wav: Path, model: Path | str | None = None) -> list[dict] | None:
    """Generate speech — Edge TTS if available, Piper as fallback.

    Returns word timings when Edge produced them, else None (Piper has no
    word boundaries; callers synthesize even spacing if they need captions).
    """
    text = _clean_for_tts(text)
    if USE_EDGE_TTS:
        voice = model if isinstance(model, str) else None
        return _edge_tts(text, out_wav, voice=voice)
    piper_model = model if isinstance(model, Path) else None
    _piper_tts_raw(text, out_wav, model=piper_model)
    return None


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

def _remotion_available() -> bool:
    """True when the Remotion composer can render (npx + installed deps)."""
    if shutil.which("npx") is None:
        return False
    composer = Path(__file__).resolve().parents[3] / "remotion-composer"
    return (composer / "node_modules" / "remotion").exists()


def _build_word_captions(
    sections: list[dict],
    seg_durations: list[float],
    seg_words: list[list[dict] | None],
    lead_seconds: float,
) -> list[dict]:
    """Global word-caption track: per-section timings shifted onto the reel
    timeline. Sections without real timings (Piper) get even spacing so the
    captions still track the voice approximately."""
    captions: list[dict] = []
    cursor_ms = lead_seconds * 1000
    for sec, dur, words in zip(sections, seg_durations, seg_words):
        if words:
            for w in words:
                captions.append({
                    "word": w["word"],
                    "startMs": round(cursor_ms + w["startMs"], 1),
                    "endMs": round(cursor_ms + w["endMs"], 1),
                })
        else:
            tokens = sec["narration"].split()
            if tokens:
                step = (dur * 1000) / len(tokens)
                for j, tok in enumerate(tokens):
                    captions.append({
                        "word": tok,
                        "startMs": round(cursor_ms + j * step, 1),
                        "endMs": round(cursor_ms + (j + 1) * step, 1),
                    })
        cursor_ms += dur * 1000
    return captions


# Word-highlight color per lane, so the captions carry the lane identity the
# old solid background cards used to.
LANE_HIGHLIGHT = {
    "gay":         "#38BDF8",
    "lesbian":     "#FB7185",
    "bisexual":    "#A78BFA",
    "trans":       "#34D399",
}
DEFAULT_HIGHLIGHT = "#22D3EE"


def _finish_reel_remotion(
    *, script: dict, output: Path, tmp_dir: Path, music_path: Path | None,
    inputs: list[str], bg_filter_prefix: str, bg_label: str,
    sections: list[dict], seg_durations: list[float],
    seg_words: list[list[dict] | None], total: float, total_padded: float,
    lane: str, bg: str, voice, broll_clip, have_hero: bool,
) -> dict:
    """Remotion finish: ffmpeg builds the background+voice base track, then
    the TalkingHead composition lays word-highlight captions and animated
    brand cards on top — the shorts-native look, fully unattended."""
    # 1. Base video: background motion + voice (+ ducked music), no overlays.
    base_mp4 = tmp_dir / "remotion_base.mp4"
    base_inputs = list(inputs)
    music_idx = None
    if music_path and music_path.exists():
        base_inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_idx = 2
    filter_complex = bg_filter_prefix.rstrip(";")
    audio_map = "1:a"
    if music_idx is not None:
        music_part = (
            f"[{music_idx}:a]volume={MUSIC_DUCK_DB}dB,"
            f"atrim=0:{total_padded:.3f},asetpts=PTS-STARTPTS[mus];"
            f"[1:a][mus]amix=inputs=2:duration=first:dropout_transition=0[amix]"
        )
        filter_complex = f"{filter_complex};{music_part}" if filter_complex else music_part
        audio_map = "[amix]"
    cmd = ["ffmpeg", "-y", *base_inputs]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex]
    cmd += [
        "-map", f"[{bg_label}]" if bg_label == "bg" else bg_label,
        "-map", audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total_padded:.3f}",
        str(base_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"[reel_render] base compose failed:\n{proc.stderr[-2000:]}")

    # 2. Composition props: word captions + animated brand cards.
    captions = _build_word_captions(
        sections, seg_durations, seg_words, BRAND_LEAD_SECONDS)
    hashtags = " ".join(script.get("hashtags", [])[:4])
    overlays = [
        {
            "type": "hero_title", "position": "full_overlay",
            "in_seconds": 0.0, "out_seconds": BRAND_LEAD_SECONDS,
            "text": script.get("topic", "")[:80],
            "subtitle": "What's the LGBT, Fish?",
        },
        {
            "type": "text_card", "position": "full_overlay",
            "in_seconds": round(total_padded - BRAND_OUTRO_SECONDS, 3),
            "out_seconds": round(total_padded, 3),
            "text": f"{hashtags or '#whatsthelgbtfish'}\nFollow for daily LGBT news",
        },
    ]
    # The renderer only streams http(s) or bundled public/ assets, so stage
    # the base track in the composer's public dir and pass its bare name
    # (TalkingHead resolves it via staticFile).
    composer = Path(__file__).resolve().parents[3] / "remotion-composer"
    staged_name = f"fish_base_{os.getpid()}_{output.stem}.mp4"
    staged = composer / "public" / staged_name
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(base_mp4, staged)

    props = {
        "videoSrc": staged_name,
        "captions": captions,
        "overlays": overlays,
        "wordsPerPage": 4,
        "fontSize": 58,
        "highlightColor": LANE_HIGHLIGHT.get(lane, DEFAULT_HIGHLIGHT),
        "durationSeconds": round(total_padded, 3),
    }
    props_path = tmp_dir / "remotion_props.json"
    props_path.write_text(json.dumps(props))

    # 3. Render TalkingHead over the base track.
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            ["npx", "remotion", "render",
             str(composer / "src" / "index.tsx"), "TalkingHead",
             str(output.resolve()), "--props", str(props_path)],
            capture_output=True, text=True, cwd=composer, timeout=1800,
        )
    finally:
        staged.unlink(missing_ok=True)
    if proc.returncode != 0:
        sys.exit(f"[reel_render] remotion render failed:\n{proc.stderr[-3000:]}")

    return {
        "output": str(output),
        "engine": "remotion",
        "duration_seconds": round(total_padded, 2),
        "voice_seconds": round(total, 2),
        "sections": len(sections),
        "lane": lane,
        "topic": script.get("topic", ""),
        "background_color": bg,
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "voice_model": voice if isinstance(voice, str) else voice.name,
        "hero_image": have_hero,
        "broll_clip": broll_clip is not None,
        "word_captions": len(captions),
        "music_bed": music_idx is not None,
    }


def render_reel(
    script: dict,
    output: Path,
    tmp_dir: Path,
    music_path: Path | None = None,
    engine: str = "auto",
) -> dict:
    """Render a FISH reel_script to an MP4. Returns render report.

    engine: "remotion" (word-highlight captions + animated cards over the
    footage), "ffmpeg" (static PNG overlays), or "auto" — remotion when the
    composer is installed, else ffmpeg.
    """
    if not USE_EDGE_TTS:
        _check_bin("piper")
        if not DEFAULT_PIPER_MODEL.exists():
            sys.exit(f"[reel_render] Piper voice not found: {DEFAULT_PIPER_MODEL}")
    _check_bin("ffmpeg")
    _check_bin("ffprobe")

    if engine == "auto":
        engine = "remotion" if _remotion_available() else "ffmpeg"
    if engine == "remotion" and not _remotion_available():
        print("[reel_render] remotion requested but unavailable; using ffmpeg",
              file=sys.stderr)
        engine = "ffmpeg"
    print(f"[reel_render] engine: {engine}", file=sys.stderr)

    tmp_dir.mkdir(parents=True, exist_ok=True)
    lane = script.get("lane", "")
    sections = script.get("sections", [])
    if not sections:
        sys.exit("[reel_render] script has no sections")

    bg = LANE_BG.get(lane, DEFAULT_BG)
    voice = _voice_for_lane(lane)

    # 1. TTS each section, measure actual duration (+ word timings from Edge)
    seg_wavs: list[Path] = []
    seg_durations: list[float] = []
    seg_words: list[list[dict] | None] = []
    for i, sec in enumerate(sections):
        wav = tmp_dir / f"seg_{i:02d}_{sec['id']}.wav"
        words = _piper_tts(sec["narration"], wav, model=voice)
        dur = _wav_duration(wav)
        seg_wavs.append(wav)
        seg_durations.append(dur)
        seg_words.append(words)
        print(f"  [{sec['id']}] {dur:.1f}s → {wav.name}")

    total = sum(seg_durations)

    # 2. Concat all wavs via the concat FILTER (not demuxer). The demuxer
    #    is picky about identical stream parameters across inputs even with
    #    -c copy overridden; the filter decodes each input independently
    #    into a uniform PCM stream and always works.
    voice_raw = tmp_dir / "voice_raw.wav"
    concat_inputs: list[str] = []
    for w in seg_wavs:
        concat_inputs += ["-i", str(w)]
    concat_streams = "".join(f"[{i}:a]" for i in range(len(seg_wavs)))
    concat_filter = f"{concat_streams}concat=n={len(seg_wavs)}:v=0:a=1[out]"
    proc = subprocess.run(
        ["ffmpeg", "-y", *concat_inputs,
         "-filter_complex", concat_filter,
         "-map", "[out]",
         "-ar", "22050", "-ac", "1", "-c:a", "pcm_s16le",
         str(voice_raw)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"[reel_render] voice concat failed:\n{proc.stderr[-2000:]}")

    voice_wav = tmp_dir / "voice.wav"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(voice_raw),
         "-af", f"adelay={int(BRAND_LEAD_SECONDS*1000)}|{int(BRAND_LEAD_SECONDS*1000)},"
                f"apad=pad_dur={BRAND_OUTRO_SECONDS}",
         str(voice_wav)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"[reel_render] voice pad failed:\n{proc.stderr[-2000:]}")
    total_padded = BRAND_LEAD_SECONDS + total + BRAND_OUTRO_SECONDS

    # 3. Pre-render each caption as a transparent PNG + brand cards
    caption_pngs: list[Path] = []
    for i, sec in enumerate(sections):
        png = tmp_dir / f"cap_{i:02d}.png"
        _render_caption_png(sec["narration"], png)
        caption_pngs.append(png)

    # 3.5 Background ladder: licensed exact image → Pexels b-roll clip →
    #     article hero image w/ Ken Burns → lane color card. Fetch this
    #     first so the opening title beat can play over the motion instead of
    #     sitting on a static solid color card.
    from .broll import fetch_broll_for_story, mentions_public_person
    from .media_resolver import download_media, resolve_story_media, write_media_manifest

    story_url = (
        script.get("source_attribution", {}).get("url")
        or script.get("story_url", "")
    )
    topic = script.get("topic", "")

    hero_bg = tmp_dir / "hero_bg.png"
    have_hero = False
    licensed_assets = []

    def _try_hero() -> bool:
        """Fetch + prepare the article hero image. True if it landed."""
        if not story_url:
            return False
        hero_src = _fetch_hero_image(story_url, tmp_dir / "hero_raw.bin")
        if not hero_src:
            return False
        try:
            _prepare_hero_bg(hero_src, hero_bg, bg)
        except Exception as exc:  # noqa: BLE001
            print(f"[reel_render] hero prep failed: {exc}", file=sys.stderr)
            return False
        return True

    broll_clip = None
    licensed = resolve_story_media(topic)
    if licensed:
        if licensed.kind == "video":
            # Real footage of the story's subject (e.g. C-SPAN/government
            # video from Commons) — play it as the background, don't still it.
            clip = download_media(licensed, tmp_dir / "licensed_clip.bin")
            if clip:
                broll_clip = clip
                licensed_assets.append(licensed)
                print(f"[reel_render] exact {licensed.provider} FOOTAGE",
                      file=sys.stderr)
        else:
            licensed_src = download_media(licensed, tmp_dir / "licensed_raw.bin")
            if licensed_src:
                try:
                    _prepare_hero_bg(licensed_src, hero_bg, bg)
                    have_hero = True
                    licensed_assets.append(licensed)
                    print(f"[reel_render] exact {licensed.provider} image",
                          file=sys.stderr)
                except Exception as exc:  # noqa: BLE001
                    print(f"[reel_render] licensed image prep failed: {exc}",
                          file=sys.stderr)

    # For a named person with no reusable match, the source article's hero is
    # still more relevant than stock footage.
    if broll_clip is not None:
        pass    # licensed footage already carries the background
    elif not have_hero and mentions_public_person(topic) and _try_hero():
        have_hero = True
        print("[reel_render] named person → hero image over stock b-roll",
              file=sys.stderr)
    elif not have_hero:
        # Subject-mapped stock only — never literal headline words, which
        # Pexels fuzzy-matches into unrelated footage (a "Mother Road"
        # headline once produced a mom-with-kids clip). If the subject maps
        # to no stock concept, the article's own image beats guessing, and
        # generic lane footage is the true last resort.
        broll_clip = fetch_broll_for_story(
            title=topic,
            lane=lane,
            out_path=tmp_dir / "broll_bg.mp4",
            orientation="portrait",
            mode="specific",
        )
        if not broll_clip and _try_hero():
            have_hero = True
        if not broll_clip and not have_hero:
            broll_clip = fetch_broll_for_story(
                title=topic,
                lane=lane,
                out_path=tmp_dir / "broll_bg.mp4",
                orientation="portrait",
                mode="lane",
            )

    # Brand lead card + hashtag outro card. Over motion (b-roll or hero) the
    # opening is a transparent overlay so footage shows through; on a solid
    # background it stays a full-frame card so the text is legible.
    over_motion = bool(broll_clip) or have_hero
    lead_card = tmp_dir / "brand_lead.png"
    if over_motion:
        _render_brand_overlay(
            title=script.get("topic", "")[:80],
            subtitle="What's the LGBT, Fish?",
            out_png=lead_card,
        )
    else:
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

    # 4. Compose: bg + voice + PNG overlays, each on its own time window
    output.parent.mkdir(parents=True, exist_ok=True)

    if broll_clip:
        # Loop the stock clip over the whole reel, cover-crop, slight darken
        inputs: list[str] = [
            "-stream_loop", "-1", "-t", f"{total_padded:.3f}", "-i", str(broll_clip),
            "-i", str(voice_wav),
        ]
        bg_filter_prefix = (
            f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},fps={FPS},"
            f"eq=brightness=-0.15:saturation=0.9,"
            f"trim=duration={total_padded:.3f},setpts=PTS-STARTPTS[bg];"
        )
        bg_label = "bg"
    elif have_hero:
        # Ken Burns: slow zoom-in over the entire duration
        frames = int(total_padded * FPS)
        zoompan = (
            f"scale={WIDTH * 2}x{HEIGHT * 2},"
            f"zoompan=z='min(zoom+0.0006,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':"
            f"s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
        inputs = [
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

    if engine == "remotion":
        return _finish_reel_remotion(
            script=script, output=output, tmp_dir=tmp_dir,
            music_path=music_path, inputs=inputs,
            bg_filter_prefix=bg_filter_prefix, bg_label=bg_label,
            sections=sections, seg_durations=seg_durations,
            seg_words=seg_words, total=total, total_padded=total_padded,
            lane=lane, bg=bg, voice=voice, broll_clip=broll_clip,
            have_hero=have_hero,
        )

    # Add brand lead + outro cards + captions as extra inputs
    extra_pngs = [lead_card] + caption_pngs + [outro_card]
    for png in extra_pngs:
        inputs += ["-i", str(png)]

    # Add music track as last input if provided
    music_input_idx = None
    if music_path and music_path.exists():
        inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_input_idx = 2 + len(extra_pngs)   # 0=bg, 1=voice, then pngs

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

    media_manifest = write_media_manifest(output, licensed_assets)
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
        "voice_model": voice if isinstance(voice, str) else voice.name,
        "hero_image": have_hero,
        "broll_clip": broll_clip is not None,
        "licensed_media": bool(licensed_assets),
        "media_manifest": str(media_manifest),
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
    parser.add_argument(
        "--engine", default="auto", choices=["auto", "remotion", "ffmpeg"],
        help="Caption/card renderer: remotion (word-highlight captions), "
             "ffmpeg (static PNGs), or auto (remotion when installed)",
    )
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text())
    output = Path(args.output)
    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else output.parent / f".{output.stem}_work"
    music = Path(args.music) if args.music else None

    report = render_reel(script, output, tmp_dir, music_path=music, engine=args.engine)
    print(f"\n[reel_render] wrote {report['output']} ({report['duration_seconds']}s)")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
