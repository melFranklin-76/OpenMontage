"""Intake for host-recorded narration.

FISH narrates with Edge TTS by default. That is fine for a draft but works
against monetization: YouTube's inauthentic-content policy names synthetic
narration over stock visuals as an example of what it will not pay for, and
the related reused-content judgement is applied to a channel as a whole rather
than per video. A real host voice is the single largest change available.

The host records one take per script section. Sections are short, so a fluffed
line costs one retake instead of a whole episode, and the running order stays
under the pipeline's control rather than depending on a clean continuous read.

Layout — one folder per video, per show date:

    creator-studio/inbox/voice/2026-08-03/roundup/001-cold-open.wav
    creator-studio/inbox/voice/2026-08-03/roundup/002-intro.wav
    creator-studio/inbox/voice/2026-08-03/short-1/001-hook.wav

Takes match sections by the *leading zero-padded index*, not by section id.
Hand-typing three dozen ids is a worse failure mode than counting, and a
missing index is detectable where a typo'd id silently is not. Everything
after the index is free text for the host's own benefit.

`write_recording_script` emits the numbered list to read from, so filenames
and running order come from one place.

Usage:

    python -m studio.fish.voice_intake \\
        --script fish-roundup-script.json --video-key roundup \\
        --output recording-script.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# Whatever the host's recorder produces. Everything is normalized on the way in.
SUPPORTED_SUFFIXES = (".wav", ".m4a", ".mp3", ".flac", ".aiff", ".aif", ".ogg")

# The format both renderers already feed to ffmpeg (see _edge_tts).
SAMPLE_RATE = 22050
CHANNELS = 1
CODEC = "pcm_s16le"

_INDEX_RE = re.compile(r"^(\d+)")


def takes_dir(show_date: str | date, video_key: str, root: Path) -> Path:
    """Folder the host drops one video's takes into."""
    return Path(root) / "voice" / str(show_date) / video_key


# ── discovering takes ────────────────────────────────────────────────────────

def find_takes(directory: Path) -> dict[int, Path]:
    """Map 1-based section index → audio file, from filename number prefixes.

    Files without a leading number, and unsupported extensions, are ignored so
    the host can keep notes or scratch files in the same folder.

    Re-recording is expected, so when several files share an index the most
    recently modified one wins: dropping `003-body-v2.wav` next to
    `003-body.wav` does the obvious thing.
    """
    directory = Path(directory)
    if not directory.is_dir():
        return {}

    by_index: dict[int, Path] = {}
    for path in sorted(directory.iterdir()):
        if path.name.startswith(".") or not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        match = _INDEX_RE.match(path.name)
        if not match:
            continue
        index = int(match.group(1))
        previous = by_index.get(index)
        if previous is None or path.stat().st_mtime > previous.stat().st_mtime:
            if previous is not None:
                print(f"[voice_intake] {index:03d}: using {path.name} "
                      f"(newer than {previous.name})", file=sys.stderr)
            by_index[index] = path
    return by_index


@dataclass(frozen=True)
class TakeSet:
    """Which sections the host has recorded, and what doesn't line up."""

    takes: dict[int, Path] = field(default_factory=dict)
    missing: list[int] = field(default_factory=list)
    unexpected: list[int] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.unexpected

    def describe(self) -> str:
        if self.complete:
            return f"all {len(self.takes)} sections recorded"
        parts = []
        if self.missing:
            parts.append("missing " + ", ".join(f"{i:03d}" for i in self.missing))
        if self.unexpected:
            parts.append("no section for " + ", ".join(f"{i:03d}"
                                                       for i in self.unexpected))
        return "; ".join(parts)


def match_takes(section_count: int, directory: Path) -> TakeSet:
    """Line recorded takes up against the sections the script expects."""
    found = find_takes(directory)
    expected = range(1, section_count + 1)
    return TakeSet(
        takes={i: found[i] for i in expected if i in found},
        missing=[i for i in expected if i not in found],
        unexpected=sorted(i for i in found if i < 1 or i > section_count),
    )


# ── normalizing and measuring ────────────────────────────────────────────────

def normalize_take(src: Path, out_wav: Path) -> Path:
    """Convert a host recording to the WAV shape the renderers expect.

    The host may record at any rate, in stereo, in any container. Downstream
    ffmpeg concat assumes every narration segment matches, so normalize rather
    than hope.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "-c:a", CODEC,
         str(out_wav)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"could not normalize take {src.name}: {proc.stderr}")
    return out_wav


def probe_duration(wav: Path) -> float:
    """Duration in seconds via ffprobe."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(wav)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"could not probe {wav.name}: {proc.stderr}")
    return float(proc.stdout.strip())


# ── caption timings ──────────────────────────────────────────────────────────

def word_timings(text: str, duration_seconds: float) -> list[dict]:
    """Approximate per-word timings across a recorded take.

    Edge TTS reports real word boundaries as it synthesizes; a recorded WAV has
    none, and the renderers' existing fallback spaces words evenly by count —
    which gives "a" the same screen time as "extraordinarily" and visibly
    drifts against a human read. Weighting by character count is a better
    proxy for how long a word takes to say and costs nothing.

    This is an approximation, not forced alignment: it cannot know where the
    host paused. Per-section recording is what keeps it usable — error cannot
    accumulate past the end of a section, because the next section re-anchors
    to its own take. If word-perfect highlighting is ever needed, swap this for
    real alignment (the repo already wraps WhisperX in tools/analysis).
    """
    tokens = text.split()
    if not tokens or duration_seconds <= 0:
        return []

    # +1 per token approximates the gap that follows each word, so a run of
    # short words doesn't collapse to nothing.
    weights = [len(tok) + 1 for tok in tokens]
    total_weight = sum(weights)
    total_ms = duration_seconds * 1000

    timings: list[dict] = []
    cursor = 0.0
    for tok, weight in zip(tokens, weights):
        span = total_ms * weight / total_weight
        timings.append({
            "word": tok,
            "startMs": round(cursor, 1),
            "endMs": round(cursor + span, 1),
        })
        cursor += span
    return timings


# ── recording script ─────────────────────────────────────────────────────────

def write_recording_script(
    script: dict, out_path: Path, *, video_key: str, show_date: str | date,
    inbox_hint: str = "creator-studio/inbox",
) -> Path:
    """Emit the numbered script the host reads from.

    Filenames and running order come from this file, so the numbers here are
    the contract: `001` in the list means `001-*.wav` in the folder.
    """
    sections = script.get("sections", [])
    folder = f"{inbox_hint}/voice/{show_date}/{video_key}/"

    lines = [
        f"# Recording script — {video_key} — {show_date}",
        "",
        f"{len(sections)} sections. Record one file per section into:",
        "",
        f"    {folder}",
        "",
        "Name each file with its number first — `001-anything.wav`. Everything "
        "after the number is for you. wav, m4a, mp3, flac, aiff and ogg all "
        "work, at any sample rate.",
        "",
        "Re-recording a line? Drop the new file in with the same number; the "
        "newest one wins.",
        "",
        "---",
        "",
    ]

    for index, section in enumerate(sections, start=1):
        label = section.get("id", f"section-{index}")
        lane = section.get("lane")
        heading = f"## {index:03d} — {label}"
        if lane:
            heading += f"  ·  {lane}"
        lines.append(heading)
        lines.append("")
        narration = (section.get("narration") or "").strip()
        lines.append(narration or "_(no narration for this section)_")
        lines.append("")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the numbered recording script for a FISH video")
    parser.add_argument("--script", required=True, help="Rendered script JSON")
    parser.add_argument("--video-key", required=True,
                        help="Folder name for this video, e.g. roundup, short-1")
    parser.add_argument("--date", default=str(date.today()),
                        help="Show date (default: today)")
    parser.add_argument("--output", required=True, help="Markdown path to write")
    args = parser.parse_args()

    script = json.loads(Path(args.script).read_text())
    out = write_recording_script(
        script, Path(args.output),
        video_key=args.video_key, show_date=args.date,
    )
    print(f"Wrote {len(script.get('sections', []))}-section recording script to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
