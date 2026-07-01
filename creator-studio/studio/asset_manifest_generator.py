"""Deterministic local Asset Manifest generator for Creator Studio.

Milestone 4E intentionally plans asset records only. It does not call provider
APIs, render media, or create image/audio/video files. The resulting manifest is
a stable contract for later stages and is derived from already-approved local
artifacts in the project workspace.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _slugify(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or fallback


def _stable_seed(*parts: object) -> int:
    joined = "|".join(str(part) for part in parts)
    return int(hashlib.sha256(joined.encode("utf-8")).hexdigest()[:8], 16)


def _script_sections_by_id(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get("id")): section
        for section in script.get("sections") or []
        if section.get("id") is not None
    }


def _duration(start: object, end: object, *, fallback: float = 5.0) -> float:
    try:
        start_seconds = float(start)
        end_seconds = float(end)
    except (TypeError, ValueError):
        return fallback
    return max(round(end_seconds - start_seconds, 2), 0.0)


def _visual_type(asset_type: str, scene_type: str) -> str:
    if asset_type in {"diagram", "animation", "image", "video"}:
        return asset_type
    if scene_type == "animation":
        return "animation"
    return "diagram"


def _visual_format(asset_type: str) -> str:
    if asset_type == "video":
        return "mp4"
    return "svg"


def _visual_path(asset_type: str, scene_id: str, description: str) -> str:
    stem = _slugify(description[:48], fallback=scene_id)
    if asset_type == "video":
        return f"assets/video/{scene_id}-{stem}.mp4"
    return f"assets/visuals/{scene_id}-{stem}.svg"


def _scene_prompt(
    *,
    scene: dict[str, Any],
    required_asset: dict[str, Any],
    proposal_packet: dict[str, Any],
) -> str:
    production_plan = proposal_packet.get("production_plan") or {}
    playbook = production_plan.get("playbook") or proposal_packet.get("style_playbook") or "flat-motion-graphics"
    delivery = production_plan.get("delivery_promise") or {}
    description = str(required_asset.get("description") or scene.get("description") or "Visual beat")
    movement = str(scene.get("movement") or "simple animated reveal")
    return (
        f"Plan a local {playbook} visual for {scene.get('id')}: {description}. "
        f"Scene movement: {movement}. Tone: {delivery.get('tone_mode') or 'educational'}."
    )


def _build_visual_assets(
    *,
    scene_plan: dict[str, Any],
    proposal_packet: dict[str, Any],
    run_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scene_plan.get("scenes") or [], start=1):
        scene_id = str(scene.get("id") or f"scene_{scene_index:02d}")
        scene_type = str(scene.get("type") or "diagram")
        required_assets = scene.get("required_assets") or [
            {
                "type": scene_type,
                "description": scene.get("description") or "Planned local visual asset",
                "source": "generate",
            }
        ]

        for asset_index, required_asset in enumerate(required_assets, start=1):
            requested_type = str(required_asset.get("type") or scene_type)
            asset_type = _visual_type(requested_type, scene_type)
            description = str(required_asset.get("description") or scene.get("description") or "Visual asset")
            assets.append(
                {
                    "id": f"vis_{scene_index:02d}_{asset_index:02d}",
                    "type": asset_type,
                    "path": _visual_path(asset_type, scene_id, description),
                    "source_tool": "local_asset_manifest_generator",
                    "scene_id": scene_id,
                    "prompt": _scene_prompt(
                        scene=scene,
                        required_asset=required_asset,
                        proposal_packet=proposal_packet,
                    ),
                    "seed": _stable_seed(run_manifest.get("id") or run_manifest.get("name") or "run", scene_id, asset_index),
                    "model": "local-deterministic-planner",
                    "cost_usd": 0.0,
                    "format": _visual_format(asset_type),
                    "quality_score": 1.0,
                    "subtype": "planned_local",
                    "generation_summary": "Planned deterministically from scene_plan.json; no media generation was performed.",
                }
            )
    return assets


def _build_narration_assets(
    *,
    scene_plan: dict[str, Any],
    script: dict[str, Any],
) -> list[dict[str, Any]]:
    sections = _script_sections_by_id(script)
    assets: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scene_plan.get("scenes") or [], start=1):
        scene_id = str(scene.get("id") or f"scene_{scene_index:02d}")
        section_id = str(scene.get("script_section_id") or "")
        section = sections.get(section_id, {})
        label = str(section.get("label") or section_id or scene_id)
        duration = _duration(scene.get("start_seconds"), scene.get("end_seconds"))
        assets.append(
            {
                "id": f"narr_{scene_index:02d}",
                "type": "narration",
                "path": f"assets/audio/narration/{scene_id}-{_slugify(label, fallback='section')}.json",
                "source_tool": "local_asset_manifest_generator",
                "scene_id": scene_id,
                "prompt": str(section.get("text") or scene.get("description") or "Narration beat"),
                "model": "local-deterministic-planner",
                "cost_usd": 0.0,
                "duration_seconds": duration,
                "format": "json",
                "quality_score": 1.0,
                "subtype": "planned_local",
                "generation_summary": "Narration placeholder planned from script.json; no audio generation was performed.",
            }
        )
    return assets


def _build_music_asset(
    *,
    proposal_packet: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    production_plan = proposal_packet.get("production_plan") or {}
    music_source = production_plan.get("music_source") or {}
    scenes = scene_plan.get("scenes") or []
    total_duration = 0.0
    if scenes:
        starts = [float(scene.get("start_seconds") or 0) for scene in scenes]
        ends = [float(scene.get("end_seconds") or 0) for scene in scenes]
        total_duration = max(ends) - min(starts)
    total_duration = max(round(total_duration, 2), 0.0)

    provider = str(music_source.get("provider") or "local")
    mood = str(music_source.get("mood_direction") or "low-key background")
    return {
        "id": "music_01",
        "type": "music",
        "path": "assets/audio/music/background-music-plan.json",
        "source_tool": "local_asset_manifest_generator",
        "scene_id": str((scenes[0] if scenes else {}).get("id") or "scene_01"),
        "prompt": f"Plan {mood} music from proposal_packet.production_plan.music_source.",
        "model": "local-deterministic-planner",
        "cost_usd": 0.0,
        "duration_seconds": total_duration,
        "format": "json",
        "quality_score": 1.0,
        "subtype": "planned_local",
        "generation_summary": f"Music source recorded as {provider}; no music generation was performed.",
        "provider": provider,
    }


def build_asset_manifest(
    *,
    scene_plan: dict[str, Any],
    script: dict[str, Any],
    proposal_packet: dict[str, Any],
    stage_request: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic local asset manifest from canonical inputs."""

    visual_assets = _build_visual_assets(
        scene_plan=scene_plan,
        proposal_packet=proposal_packet,
        run_manifest=run_manifest,
    )
    narration_assets = _build_narration_assets(scene_plan=scene_plan, script=script)
    subtitle_asset = {
        "id": "subtitles_01",
        "type": "subtitle",
        "path": "assets/subtitles/subtitles.srt",
        "source_tool": "local_asset_manifest_generator",
        "scene_id": str(((scene_plan.get("scenes") or [{}])[0]).get("id") or "scene_01"),
        "model": "local-deterministic-planner",
        "cost_usd": 0.0,
        "format": "srt",
        "quality_score": 1.0,
        "subtype": "planned_local",
        "generation_summary": "Subtitle file planned from script sections; no transcription or speech generation was performed.",
    }
    assets = [*visual_assets, *narration_assets, subtitle_asset]

    production_plan = proposal_packet.get("production_plan") or {}
    if production_plan.get("music_source") is not None:
        assets.append(_build_music_asset(proposal_packet=proposal_packet, scene_plan=scene_plan))

    topic = str(run_manifest.get("topic") or script.get("title") or "Untitled topic")
    platform = str(run_manifest.get("platform") or stage_request.get("platform") or "instagram")

    return {
        "version": "1.0",
        "assets": assets,
        "total_cost_usd": round(sum(float(asset.get("cost_usd") or 0.0) for asset in assets), 2),
        "metadata": {
            "generated_by": "creator-studio/studio/asset_manifest_generator.py",
            "generation_mode": "deterministic_local",
            "topic": topic,
            "platform": platform,
            "pipeline": run_manifest.get("pipeline") or stage_request.get("pipeline"),
            "stage_request_status": stage_request.get("status"),
            "total_assets": len(assets),
            "source_artifacts": [
                "scene_plan/scene_plan.json",
                "script/script.json",
                "proposal/proposal_packet.json",
                "assets/stage_request.json",
                "run.json",
            ],
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
        stage_request=stage_request,
        run_manifest=run_manifest,
    )

    output_path = project_dir / "assets" / "asset_manifest.json"
    _write_json(output_path, manifest)
    return output_path
