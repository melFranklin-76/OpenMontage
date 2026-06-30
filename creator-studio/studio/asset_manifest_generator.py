"""Deterministic local Asset Manifest artifact generator for Creator Studio."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "asset"


def _asset_type_for(scene: dict[str, Any], required_asset: dict[str, Any]) -> str:
    raw_type = str(required_asset.get("type") or scene.get("type") or "image").lower()

    if raw_type in {"image", "video", "audio", "narration", "music", "sfx", "diagram", "animation", "code_snippet", "subtitle", "font", "lut"}:
        return raw_type

    scene_type = str(scene.get("type") or "").lower()
    if scene_type == "animation":
        return "animation"
    if scene_type == "diagram":
        return "diagram"
    if scene_type == "text_card":
        return "subtitle"

    return "image"


def _format_for(asset_type: str) -> str:
    if asset_type in {"narration", "music", "audio", "sfx"}:
        return "mp3"
    if asset_type in {"animation", "video"}:
        return "mp4"
    if asset_type == "subtitle":
        return "srt"
    return "png"


def _path_for(asset_type: str, asset_id: str, fmt: str) -> str:
    if asset_type in {"narration", "music", "audio", "sfx"}:
        return f"assets/audio/{asset_id}.{fmt}"
    if asset_type in {"animation", "video"}:
        return f"assets/video/{asset_id}.{fmt}"
    if asset_type == "subtitle":
        return f"assets/subtitles/{asset_id}.{fmt}"
    return f"assets/images/{asset_id}.{fmt}"


def _source_tool_for(asset_type: str) -> str:
    if asset_type == "narration":
        return "local_narration_placeholder"
    if asset_type == "music":
        return "local_music_placeholder"
    if asset_type in {"animation", "video"}:
        return "local_animation_placeholder"
    if asset_type == "subtitle":
        return "local_subtitle_placeholder"
    if asset_type == "diagram":
        return "local_diagram_placeholder"
    return "local_asset_placeholder"


def _prompt_for(scene: dict[str, Any], required_asset: dict[str, Any]) -> str:
    description = str(required_asset.get("description") or scene.get("description") or "Scene asset")
    style = ", ".join(scene.get("texture_keywords") or ["clean", "flat-motion-graphics"])
    return f"{description}. Style: {style}."


def build_asset_manifest(
    *,
    scene_plan: dict[str, Any],
    script: dict[str, Any],
    proposal_packet: dict[str, Any],
    run_manifest: dict[str, Any],
    stage_request: dict[str, Any],
) -> dict[str, Any]:
    topic = str(run_manifest.get("topic") or script.get("title") or "Untitled topic")
    platform = str(run_manifest.get("platform") or "instagram")
    scenes = list(scene_plan.get("scenes") or [])

    assets: list[dict[str, Any]] = []

    for scene_index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("id") or f"scene_{scene_index:02d}")
        required_assets = list(scene.get("required_assets") or [])

        if not required_assets:
            required_assets = [
                {
                    "type": scene.get("type") or "image",
                    "description": scene.get("description") or f"Visual asset for {scene_id}",
                    "source": "generate",
                }
            ]

        for asset_index, required_asset in enumerate(required_assets, start=1):
            asset_type = _asset_type_for(scene, required_asset)
            fmt = _format_for(asset_type)
            asset_id = f"{_slug(asset_type)}_{scene_index:02d}_{asset_index:02d}"

            assets.append(
                {
                    "id": asset_id,
                    "type": asset_type,
                    "path": _path_for(asset_type, asset_id, fmt),
                    "source_tool": _source_tool_for(asset_type),
                    "scene_id": scene_id,
                    "prompt": _prompt_for(scene, required_asset),
                    "seed": 1000 + scene_index * 10 + asset_index,
                    "model": "local-placeholder",
                    "cost_usd": 0.0,
                    "duration_seconds": max(
                        0.0,
                        float(scene.get("end_seconds") or 0) - float(scene.get("start_seconds") or 0),
                    ),
                    "resolution": "1080x1920" if platform in {"instagram", "tiktok"} else "1920x1080",
                    "format": fmt,
                    "quality_score": 0.75,
                    "subtype": "planned_placeholder",
                    "generation_summary": "Planned locally from the scene plan; no provider call or media generation performed.",
                    "provider": "local",
                    "license": "project-internal-placeholder",
                }
            )

    if not any(asset["type"] == "narration" for asset in assets):
        assets.append(
            {
                "id": "narration_01",
                "type": "narration",
                "path": "assets/audio/narration_01.mp3",
                "source_tool": "local_narration_placeholder",
                "scene_id": str(scenes[0].get("id") if scenes else "scene_01"),
                "prompt": f"Narration placeholder for {topic}.",
                "seed": 2001,
                "model": "local-placeholder",
                "cost_usd": 0.0,
                "duration_seconds": float(script.get("total_duration_seconds") or 60),
                "format": "mp3",
                "quality_score": 0.75,
                "subtype": "planned_placeholder",
                "generation_summary": "Narration asset placeholder planned locally from script duration.",
                "provider": "local",
                "license": "project-internal-placeholder",
            }
        )

    return {
        "version": "1.0",
        "assets": assets,
        "total_cost_usd": 0.0,
        "metadata": {
            "generated_by": "creator-studio/studio/asset_manifest_generator.py",
            "generation_mode": "deterministic_local",
            "topic": topic,
            "platform": platform,
            "total_assets": len(assets),
            "stage_request_status": stage_request.get("status"),
            "selected_concept_id": (proposal_packet.get("selected_concept") or {}).get("concept_id"),
        },
    }


def generate_asset_manifest(project_dir: Path) -> Path:
    run_manifest = _read_json(project_dir / "run.json")
    stage_request = _read_json(project_dir / "assets" / "stage_request.json")
    scene_plan = _read_json(project_dir / "scene_plan" / "scene_plan.json")
    script = _read_json(project_dir / "script" / "script.json")
    proposal_packet = _read_json(project_dir / "proposal" / "proposal_packet.json")

    manifest = build_asset_manifest(
        scene_plan=scene_plan,
        script=script,
        proposal_packet=proposal_packet,
        run_manifest=run_manifest,
        stage_request=stage_request,
    )

    output_path = project_dir / "assets" / "asset_manifest.json"
    _write_json(output_path, manifest)
    return output_path
