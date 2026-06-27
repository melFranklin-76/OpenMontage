"""Shared Creator Studio paths and media configuration.

Keeping path configuration in one module prevents path strings from
spreading across the codebase as the studio grows.
"""

from __future__ import annotations

from pathlib import Path


STUDIO_ROOT = Path(__file__).resolve().parent
REPO_ROOT = STUDIO_ROOT.parent
PERSONAS_DIR = STUDIO_ROOT / "personas"
PLATFORMS_DIR = STUDIO_ROOT / "platforms"
INBOX_DIR = STUDIO_ROOT / "inbox"
PROJECTS_DIR = STUDIO_ROOT / "projects"
OUTPUTS_DIR = STUDIO_ROOT / "outputs"
ARCHIVE_DIR = STUDIO_ROOT / "archive"
LOGS_DIR = STUDIO_ROOT / "logs"

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".m4v", ".avi"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}

