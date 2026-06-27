"""Inbox scanning utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import AUDIO_EXTENSIONS, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS


def scan_inbox(inbox_dir: Path) -> dict[str, Any]:
    """Scan the inbox and classify supported media files by type.

    Unknown files are ignored so the inbox can hold notes or scratch files
    without breaking the scan step.
    """

    if not inbox_dir.exists():
        return {"videos": [], "images": [], "audio": [], "total": 0}

    videos: list[Path] = []
    images: list[Path] = []
    audio: list[Path] = []

    for path in sorted(inbox_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.name.startswith("."):
            continue

        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            videos.append(path)
        elif suffix in IMAGE_EXTENSIONS:
            images.append(path)
        elif suffix in AUDIO_EXTENSIONS:
            audio.append(path)

    return {
        "videos": videos,
        "images": images,
        "audio": audio,
        "total": len(videos) + len(images) + len(audio),
    }

