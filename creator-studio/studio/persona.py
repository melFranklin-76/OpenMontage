"""Persona loading and validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REQUIRED_FIELDS = {
    "name",
    "voice",
    "platforms",
    "default_pipeline",
    "default_platform",
    "branding",
}


def load_persona(path: Path) -> dict[str, Any]:
    """Load a persona YAML file and validate the minimum contract.

    The early schema is intentionally small so the persona format can evolve
    without forcing a heavyweight validation layer during Milestone 1.
    """

    if not path.exists():
        raise FileNotFoundError(f"Persona file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError("Persona file must contain a YAML mapping.")

    missing_fields = sorted(REQUIRED_FIELDS - raw_data.keys())
    if missing_fields:
        raise ValueError(
            f"Persona file is missing required fields: {', '.join(missing_fields)}"
        )

    platforms = raw_data["platforms"]
    if not isinstance(platforms, list) or not platforms:
        raise ValueError("Persona 'platforms' must be a non-empty list.")
    if not all(isinstance(platform, str) and platform.strip() for platform in platforms):
        raise ValueError("Persona 'platforms' entries must be non-empty strings.")

    default_platform = raw_data["default_platform"]
    if default_platform not in platforms:
        raise ValueError("Persona 'default_platform' must be listed in 'platforms'.")

    branding = raw_data["branding"]
    if not isinstance(branding, dict):
        raise ValueError("Persona 'branding' must be a mapping.")

    return {
        "name": str(raw_data["name"]).strip(),
        "voice": str(raw_data["voice"]).strip(),
        "platforms": [platform.strip() for platform in platforms],
        "default_pipeline": str(raw_data["default_pipeline"]).strip(),
        "default_platform": str(default_platform).strip(),
        "branding": branding,
    }

