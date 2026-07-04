"""Deterministic local edit-decision generation for Creator Studio smoke runs.

This generator is intentionally local-only. It reads existing Creator Studio
artifacts and writes a schema-shaped edit/edit_decisions.json without provider
calls, rendering, or network access.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _assets_from_manifest(asset_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    assets = asset_manifest.get("assets")
    if isinstance(assets, list):
        return [asset for asset in assets if isinstance(asset, dict)]
    return []


def _primary_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocked_types = {"subtitle", "font", "lut", "music", "sfx", "audio", "narration"}
    candidates = [
        asset
        for asset in assets
        if str(asset.get("type", "")).lower() not in blocked_types
    ]
    return candidates or assets


def _asset_source(asset: dict[str, Any], fallback: str) -> str:
    for key in ("id", "path", "output_path"):
        value = asset.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return fallback


def _script_sections(script: dict[str, Any]) -> list[dict[str, Any]]:
    sections = script.get("sections")
    if isinstance(sections, list) and sections:
        return [section for section in sections if isinstance(section, dict)]
    return [
        {
            "id": "section_01",
            "start_seconds": 0,
            "end_seconds": 5,
            "title": "Preview section",
        }
    ]


def _section_start(section: dict[str, Any], fallback: float) -> float:
    value = section.get("start_seconds")
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return fallback


def _section_end(section: dict[str, Any], start: float, fallback: float) -> float:
    value = section.get("end_seconds")
    if isinstance(value, (int, float)) and value > start:
        return float(value)
    return max(start + 3.0, fallback)


def _render_runtime(run_json: dict[str, Any], proposal_packet: dict[str, Any]) -> str:
    for source in (proposal_packet, run_json):
        value = source.get("render_runtime")
        if isinstance(value, str) and value.strip():
            return value
    return "remotion"


def _renderer_family(proposal_packet: dict[str, Any]) -> str:
    value = proposal_packet.get("renderer_family")
    if isinstance(value, str) and value.strip():
        return value
    return "explainer-data"


def generate_edit_decisions(project_dir: Path) -> Path:
    """Generate edit/edit_decisions.json from local Creator Studio artifacts."""

    run_json = _read_json(project_dir / "run.json")
    script = _read_json(project_dir / "script" / "script.json")
    scene_plan = _read_json(project_dir / "scene_plan" / "scene_plan.json")
    asset_manifest = _read_json(project_dir / "assets" / "asset_manifest.json")
    proposal_packet = _read_json(project_dir / "proposal" / "proposal_packet.json")

    assets = _assets_from_manifest(asset_manifest)
    visual_assets = _primary_assets(assets)
    sections = _script_sections(script)

    cuts: list[dict[str, Any]] = []
    cursor = 0.0

    for index, section in enumerate(sections, start=1):
        start = _section_start(section, cursor)
        end = _section_end(section, start, start + 4.0)
        asset = visual_assets[(index - 1) % len(visual_assets)] if visual_assets else {}

        cuts.append(
            {
                "id": f"cut_{index:02d}",
                "source": _asset_source(asset, f"local_preview_{index:02d}"),
                "in_seconds": start,
                "out_seconds": end,
                "layer": "primary",
                "transition_in": "fade" if index == 1 else "cut",
                "transition_duration": 0.25 if index == 1 else 0,
                "reason": f"Local preview cut for section {index}",
            }
        )
        cursor = end

    subtitle_asset = next(
        (
            asset
            for asset in assets
            if str(asset.get("type", "")).lower() == "subtitle"
            or str(asset.get("path", "")).lower().endswith(".srt")
        ),
        None,
    )
    narration_asset = next(
        (
            asset
            for asset in assets
            if str(asset.get("type", "")).lower() == "narration"
        ),
        None,
    )
    music_asset = next(
        (
            asset
            for asset in assets
            if str(asset.get("type", "")).lower() == "music"
        ),
        None,
    )

    payload: dict[str, Any] = {
        "version": "1.0",
        "render_runtime": _render_runtime(run_json, proposal_packet),
        "renderer_family": _renderer_family(proposal_packet),
        "cuts": cuts,
        "overlays": [],
        "audio": {
            "narration": {
                "segments": []
            }
        },
        "subtitles": {
            "enabled": subtitle_asset is not None,
            "style": "sentence",
            "font": "Inter",
            "font_size": 36,
            "color": "#FFFFFF",
            "outline_color": "#000000",
            "background": "#00000066",
            "position": "bottom-center",
            "max_words_per_line": 8,
        },
        "slideshow_risk_score": {
            "average": 0.25,
            "verdict": "acceptable",
        },
        "metadata": {
            "topic": run_json.get("topic") or run_json.get("name") or "local-preview",
            "platform": run_json.get("platform") or "local",
            "total_cuts": len(cuts),
            "source": "local_edit_decision_generator",
        },
    }

    if narration_asset is not None:
        payload["audio"]["narration"]["segments"].append(
            {
                "asset_id": _asset_source(narration_asset, "narration_01"),
                "start_seconds": 0,
                "end_seconds": max((cut["out_seconds"] for cut in cuts), default=0),
            }
        )

    if music_asset is not None:
        payload["audio"]["music"] = {
            "asset_id": _asset_source(music_asset, "music_01"),
            "volume": 0.15,
            "fade_in_seconds": 1.0,
            "fade_out_seconds": 2.0,
            "ducking": True,
        }

    if subtitle_asset is not None:
        payload["subtitles"]["source"] = _asset_source(subtitle_asset, "subtitle_01")

    return _write_json(project_dir / "edit" / "edit_decisions.json", payload)


__all__ = ["generate_edit_decisions"]
