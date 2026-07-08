"""Render a long-form FISH roundup script to 1920×1080 MP4.

Companion to reel_render.py — same tooling (Piper + PIL + ffmpeg overlay
chain) but horizontal, with per-story hero images/backgrounds swapping in
during each chapter body, lane-tinted title cards between chapters, and
a bottom-third caption band.

Structure per section id:
    cold_open        → brand hero + full-screen text
    intro            → brand card
    chN_title        → lane-tinted chapter card, story N of 10
    chN_body         → hero image + Ken Burns + lower-third caption
    chN_transition   → brand ident, 1-second beat
    outro            → brand card

Usage:
    python -m studio.fish.long_roundup_render \\
      --script roundup-script.json \\
      --output out/roundup.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .broll import fetch_broll_for_story
from .reel_render import (
    _fetch_hero_image,
    _piper_tts,
    _prepare_hero_bg,
    _render_brand_card,
    _render_caption_png,
    _voice_for_lane,
    _wav_duration,
    _wrap_words,
    DEFAULT_PIPER_MODEL,
    LANE_BG,
    DEFAULT_BG,
    MUSIC_DUCK_DB,
)

# 16:9 horizontal, YouTube long-form standard
WIDTH = 1920
HEIGHT = 1080
FPS = 30

# Bigger fonts for the horizontal band
CAPTION_FONTSIZE = 44
TITLE_FONTSIZE = 96
CAPTION_Y_FRAC = 0.75      # Lower-third at 75%


# ── caption/card overrides tuned for 16:9 ─────────────────────────────────────

def _render_horizontal_caption(text: str, out_png: Path) -> None:
    """Wide lower-third caption strip, PIL-based."""
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            try:
                font = ImageFont.truetype(candidate, CAPTION_FONTSIZE)
                break
            except OSError:
                pass
    if font is None:
        font = ImageFont.load_default()

    lines = _wrap_words(text, chars_per_line=70)[:3]
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_h = int(CAPTION_FONTSIZE * 1.28)
    block_h = line_h * len(lines)
    pad_x, pad_y = 48, 26

    widest = max(
        (draw.textbbox((0, 0), ln, font=font)[2] for ln in lines),
        default=0,
    )
    box_w = widest + pad_x * 2
    box_h = block_h + pad_y * 2
    box_x = (WIDTH - box_w) // 2
    box_y = int(HEIGHT * CAPTION_Y_FRAC)

    draw.rounded_rectangle(
        [(box_x, box_y), (box_x + box_w, box_y + box_h)],
        radius=20, fill=(0, 0, 0, 170),
    )
    for i, ln in enumerate(lines):
        tw = draw.textbbox((0, 0), ln, font=font)[2]
        tx = box_x + (box_w - tw) // 2
        ty = box_y + pad_y + i * line_h
        draw.text((tx, ty), ln, fill=(255, 255, 255, 255), font=font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def _render_horizontal_card(title: str, subtitle: str, out_png: Path, bg_hex: str) -> None:
    """Full-frame 1920×1080 title card."""
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

    title_font = _font(TITLE_FONTSIZE)
    sub_font = _font(52)

    lines = _wrap_words(title, chars_per_line=32)
    line_h = 118
    block_h = len(lines) * line_h
    y0 = (HEIGHT - block_h) // 2 - 60
    for i, ln in enumerate(lines):
        tw = draw.textbbox((0, 0), ln, font=title_font)[2]
        draw.text(((WIDTH - tw) // 2, y0 + i * line_h),
                  ln, fill=(255, 255, 255, 255), font=title_font)

    sw = draw.textbbox((0, 0), subtitle, font=sub_font)[2]
    draw.text(((WIDTH - sw) // 2, y0 + block_h + 40),
              subtitle, fill=(255, 255, 255, 220), font=sub_font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)


def _prepare_horizontal_hero(img_src: Path, out_png: Path, bg_hex: str) -> None:
    """Cover-crop hero image to 1920x1080 with lane tint + darken for caption legibility."""
    from PIL import Image, ImageEnhance, ImageFilter

    img = Image.open(img_src).convert("RGB")
    tw, th = WIDTH, HEIGHT
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - tw) // 2
    y = (nh - th) // 2
    img = img.crop((x, y, x + tw, y + th))
    img = ImageEnhance.Color(img).enhance(0.9)
    img = ImageEnhance.Brightness(img).enhance(0.6)
    img = img.filter(ImageFilter.GaussianBlur(radius=1.5))
    r = int(bg_hex[2:4], 16); g = int(bg_hex[4:6], 16); b = int(bg_hex[6:8], 16)
    tint = Image.new("RGB", (tw, th), (r, g, b))
    img = Image.blend(img, tint, 0.28)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")


# ── render ───────────────────────────────────────────────────────────────────

def _check_bin(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"[long_roundup_render] required binary not on PATH: {name}")


def _voice_wav_for_section(section: dict, tmp_dir: Path, idx: int, voice: Path) -> Path:
    wav = tmp_dir / f"seg_{idx:03d}_{section['id']}.wav"
    _piper_tts(section["narration"], wav, model=voice)
    return wav


def render_roundup(
    script: dict, output: Path, tmp_dir: Path, music_path: Path | None = None,
) -> dict:
    """Render a long-form roundup script to a horizontal MP4."""
    _check_bin("piper")
    _check_bin("ffmpeg")
    _check_bin("ffprobe")

    if not DEFAULT_PIPER_MODEL.exists():
        sys.exit(f"[long_roundup_render] Piper voice not found: {DEFAULT_PIPER_MODEL}")

    tmp_dir.mkdir(parents=True, exist_ok=True)
    sections = script.get("sections", [])
    if not sections:
        sys.exit("[long_roundup_render] script has no sections")

    stories = {s["rank"]: s for s in script.get("stories", [])}

    # 1. TTS each section using the voice that matches its lane (fallback host voice)
    host_voice = DEFAULT_PIPER_MODEL
    seg_wavs: list[Path] = []
    seg_durations: list[float] = []
    seg_lanes: list[str] = []
    for i, sec in enumerate(sections):
        lane = sec.get("lane", "")
        voice = _voice_for_lane(lane) if lane else host_voice
        wav = _voice_wav_for_section(sec, tmp_dir, i, voice)
        dur = _wav_duration(wav)
        seg_wavs.append(wav)
        seg_durations.append(dur)
        seg_lanes.append(lane)
        print(f"  [{i:02d} {sec['id']:20s}] {dur:6.1f}s ({lane or 'host'})", file=sys.stderr)

    total = sum(seg_durations)
    print(f"  total voice: {total:.1f}s ({total/60:.1f} min)", file=sys.stderr)

    # 2. Concat all voices into one track (concat filter — CI-safe)
    voice_wav = tmp_dir / "voice.wav"
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
         str(voice_wav)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        sys.exit(f"[long_roundup_render] voice concat failed:\n{proc.stderr[-2000:]}")

    # 3. Pre-fetch per-story visuals. Ladder: Pexels b-roll clip → article
    #    hero image → lane color card (handled downstream by absence).
    broll_mp4s: dict[int, Path] = {}
    hero_pngs: dict[int, Path] = {}
    for rank, story in stories.items():
        lane = story.get("lane") or "legacy"
        bg = LANE_BG.get(lane, DEFAULT_BG)

        clip = fetch_broll_for_story(
            title=story.get("title", ""),
            lane=lane,
            out_path=tmp_dir / f"broll_{rank:02d}.mp4",
            orientation="landscape",
        )
        if clip:
            broll_mp4s[rank] = clip
            continue    # motion beats stills; skip hero fetch

        url = story.get("url", "")
        if not url:
            continue
        raw = tmp_dir / f"hero_{rank:02d}_raw.bin"
        got = _fetch_hero_image(url, raw)
        if not got:
            continue
        hero_png = tmp_dir / f"hero_{rank:02d}.png"
        try:
            _prepare_horizontal_hero(got, hero_png, bg)
            hero_pngs[rank] = hero_png
        except Exception as exc:  # noqa: BLE001
            print(f"[long_roundup_render] hero prep failed for rank {rank}: {exc}",
                  file=sys.stderr)

    # 4. Pre-render every section's visual layer:
    #    - Chapter titles + intro/outro: full-frame lane-tinted cards
    #    - Story bodies: hero image if available else lane-tinted, + lower-third caption
    #    - Transitions: solid brand ident with tag
    section_visuals: list[Path] = []
    default_bg_hex = LANE_BG.get("legacy", DEFAULT_BG)

    for i, sec in enumerate(sections):
        sid = sec["id"]
        lane = sec.get("lane") or "legacy"
        bg_hex = LANE_BG.get(lane, default_bg_hex)
        vis = tmp_dir / f"vis_{i:03d}_{sid}.png"

        if sid == "cold_open":
            _render_horizontal_card(
                "What's the LGBT, Fish?", "Daily LGBT news roundup", vis, bg_hex,
            )
        elif sid == "intro":
            _render_horizontal_card(
                script.get("stories", [{}])[0].get("title", "Today's roundup")[:80],
                f"Today's top {script.get('story_count', 10)} stories", vis, bg_hex,
            )
        elif sid == "outro":
            hashtags = " ".join(script.get("hashtags", [])[:5])
            _render_horizontal_card(
                hashtags or "#whatsthelgbtfish",
                "Follow for daily LGBT news", vis, bg_hex,
            )
        elif sid.endswith("_title"):
            rank = sec.get("story_rank")
            title = stories.get(rank, {}).get("title", sec.get("narration", ""))
            _render_horizontal_card(
                title[:80], f"Story {rank} of {script.get('story_count', 10)}",
                vis, bg_hex,
            )
        elif sid.endswith("_body"):
            _render_horizontal_caption(sec.get("narration", ""), vis)
        elif sid.endswith("_transition"):
            _render_horizontal_card("...", "What's the LGBT, Fish?", vis, bg_hex)
        else:
            _render_horizontal_caption(sec.get("narration", ""), vis)

        section_visuals.append(vis)

    # 5. Compose. Approach: build a base video that is a concatenation of per-
    #    section 1920x1080 frames sized by their measured audio duration,
    #    then overlay the voice track. For body sections that have a hero
    #    image, we overlay the caption strip on top of the hero (both PNGs
    #    are already full-frame RGBA).
    #
    # Build a filter_complex where each section is a segment of duration N,
    # then all segments concat.

    output.parent.mkdir(parents=True, exist_ok=True)

    # Input list: one image per visual, plus hero images. We stream loop each
    # image for its section duration, then concat all video segments.
    ffmpeg_inputs: list[str] = []
    input_idx = 0
    # Track which input index corresponds to each visual and each hero
    visual_input_idx: list[int] = []
    hero_input_idx: dict[int, int] = {}

    def _body_duration(rank: int) -> float:
        for i, sec in enumerate(sections):
            if sec.get("id", "").endswith("_body") and sec.get("story_rank") == rank:
                return seg_durations[i]
        return 0.0

    broll_input_idx: dict[int, Path] = {}

    for vis, dur in zip(section_visuals, seg_durations):
        ffmpeg_inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(vis)]
        visual_input_idx.append(input_idx)
        input_idx += 1
    for rank, hero in hero_pngs.items():
        ffmpeg_inputs += ["-loop", "1", "-t", f"{_body_duration(rank):.3f}", "-i", str(hero)]
        hero_input_idx[rank] = input_idx
        input_idx += 1
    for rank, clip in broll_mp4s.items():
        # Loop the clip so short stock footage covers a long narration block
        ffmpeg_inputs += [
            "-stream_loop", "-1", "-t", f"{_body_duration(rank):.3f}", "-i", str(clip),
        ]
        broll_input_idx[rank] = input_idx
        input_idx += 1

    voice_input_idx = input_idx
    ffmpeg_inputs += ["-i", str(voice_wav)]
    input_idx += 1

    music_input_idx = None
    if music_path and music_path.exists():
        ffmpeg_inputs += ["-stream_loop", "-1", "-i", str(music_path)]
        music_input_idx = input_idx
        input_idx += 1

    # Build per-section video: if it's a body section with a hero, overlay
    # the caption strip on top of a Ken Burns hero; otherwise just scale/pad
    # the visual as-is.
    filter_parts: list[str] = []
    seg_labels: list[str] = []

    for i, sec in enumerate(sections):
        sid = sec["id"]
        rank = sec.get("story_rank")
        dur = seg_durations[i]
        vis_in = visual_input_idx[i]
        seg_label = f"vseg{i}"

        if sid.endswith("_body") and rank in broll_input_idx:
            clip_in = broll_input_idx[rank]
            # Motion b-roll: cover-crop to frame, mute, caption on top
            filter_parts.append(
                f"[{clip_in}:v]scale={WIDTH}:{HEIGHT}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},"
                f"eq=brightness=-0.15:saturation=0.9,"
                f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[clip{i}];"
                f"[clip{i}][{vis_in}:v]overlay=0:0:format=auto[{seg_label}]"
            )
        elif sid.endswith("_body") and rank in hero_input_idx:
            hero_in = hero_input_idx[rank]
            frames = int(dur * FPS)
            # Ken Burns zoom on hero + caption overlay
            filter_parts.append(
                f"[{hero_in}:v]scale={WIDTH*2}x{HEIGHT*2},"
                f"zoompan=z='min(zoom+0.0005,1.10)':d={frames}:"
                f"x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':"
                f"s={WIDTH}x{HEIGHT}:fps={FPS}[hero{i}];"
                f"[hero{i}][{vis_in}:v]overlay=0:0:format=auto[{seg_label}]"
            )
        else:
            # Non-body sections: just format the visual as a video track
            filter_parts.append(
                f"[{vis_in}:v]scale={WIDTH}x{HEIGHT},fps={FPS},"
                f"format=yuv420p[{seg_label}]"
            )
        seg_labels.append(seg_label)

    # Concat all segments
    concat_ins = "".join(f"[{lbl}]" for lbl in seg_labels)
    filter_parts.append(f"{concat_ins}concat=n={len(seg_labels)}:v=1:a=0[vfinal]")

    # Audio
    audio_out = f"{voice_input_idx}:a"
    if music_input_idx is not None:
        filter_parts.append(
            f"[{music_input_idx}:a]volume={MUSIC_DUCK_DB}dB,"
            f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS[mus];"
            f"[{voice_input_idx}:a][mus]amix=inputs=2:duration=first:"
            f"dropout_transition=0[amix]"
        )
        audio_out = "[amix]"

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y", *ffmpeg_inputs,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]", "-map", audio_out,
        "-c:v", "libx264", "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", f"{total:.3f}",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"[long_roundup_render] compose failed:\n{proc.stderr[-3000:]}")

    return {
        "output": str(output),
        "duration_seconds": round(total, 2),
        "duration_min": round(total / 60, 2),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "sections": len(sections),
        "story_count": script.get("story_count"),
        "hero_images_used": len(hero_pngs),
        "broll_clips_used": len(broll_mp4s),
        "music_bed": music_input_idx is not None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a FISH roundup script to horizontal MP4")
    parser.add_argument("--script", required=True, help="Path to a roundup script JSON")
    parser.add_argument("--output", required=True, help="Output MP4 path")
    parser.add_argument("--tmp-dir", default="", help="Working directory")
    parser.add_argument("--music", default="",
                        help="Optional music bed (looped and ducked)")
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text())
    output = Path(args.output)
    tmp_dir = Path(args.tmp_dir) if args.tmp_dir else output.parent / f".{output.stem}_work"
    music = Path(args.music) if args.music else None

    report = render_roundup(script, output, tmp_dir, music_path=music)
    print(f"\n[long_roundup_render] wrote {report['output']} "
          f"({report['duration_min']} min)")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
