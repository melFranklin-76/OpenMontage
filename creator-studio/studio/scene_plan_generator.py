"""Deterministic local Scene Plan artifact generator for Creator Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _style_playbook(proposal_packet: dict[str, Any]) -> str:
    production_plan = proposal_packet.get("production_plan") or {}
    return str(production_plan.get("playbook") or "flat-motion-graphics")


def _scene_type_for(index: int, section: dict[str, Any]) -> str:
    label = str(section.get("label") or "").lower()
    if index == 0 or "intro" in label or section.get("id") == "intro":
        return "text_card"
    if "outro" in label or "call" in label or section.get("id") == "outro":
        return "text_card"
    return "animation"


def _narrative_role_for(index: int, total: int, section: dict[str, Any]) -> str:
    label = str(section.get("label") or "").lower()
    section_id = str(section.get("id") or "").lower()
    if index == 0 or "intro" in label or section_id == "intro":
        return "establish_context"
    if index == total - 1 or "outro" in label or "call" in label or section_id == "outro":
        return "call_to_action"
    return "deliver_payload"


def _required_assets(scene_type: str, section: dict[str, Any]) -> list[dict[str, str]]:
    text = str(section.get("text") or "Script section")
    if scene_type == "text_card":
        return [
            {
                "type": "text_overlay",
                "description": f"Animated text card for: {text[:90]}",
                "source": "generate",
            }
        ]

    return [
        {
            "type": "animation",
            "description": f"Flat-motion visual explaining: {text[:90]}",
            "source": "generate",
        }
    ]


def build_scene_plan(
    *,
    script: dict[str, Any],
    proposal_packet: dict[str, Any],
    run_manifest: dict[str, Any],
    stage_request: dict[str, Any],
) -> dict[str, Any]:
    topic = str(run_manifest.get("topic") or script.get("title") or "Untitled topic")
    platform = str(run_manifest.get("platform") or "instagram")
    sections = list(script.get("sections") or [])

    if not sections:
        sections = [
            {
                "id": "scene",
                "label": "Scene",
                "text": topic,
                "start_seconds": 0,
                "end_seconds": float(script.get("total_duration_seconds") or 60),
            }
        ]

    scenes: list[dict[str, Any]] = []
    total = len(sections)

    for index, section in enumerate(sections):
        scene_number = index + 1
        scene_type = _scene_type_for(index, section)
        start = float(section.get("start_seconds") or 0)
        end = float(section.get("end_seconds") or max(start + 5, 1))
        section_id = str(section.get("id") or f"section_{scene_number:02d}")
        section_text = str(section.get("text") or "Visualize this script beat.")

        scene: dict[str, Any] = {
            "id": f"scene_{scene_number:02d}",
            "type": scene_type,
            "description": section_text,
            "start_seconds": start,
            "end_seconds": end,
            "script_section_id": section_id,
            "framing": "center",
            "movement": "simple animated reveal",
            "transition_in": "cut",
            "transition_out": "cut",
            "overlay_notes": section_text[:120],
            "shot_intent": "Translate this script section into a clear visual beat.",
            "narrative_role": _narrative_role_for(index, total, section),
            "information_role": "Viewer understands the key point in this script section.",
            "hero_moment": index == max(1, total // 2),
            "texture_keywords": ["clean", "flat", "educational", "motion-graphics"],
            "required_assets": _required_assets(scene_type, section),
        }

        if scene_type == "animation":
            scene["shot_language"] = {
                "shot_size": "medium",
                "camera_movement": "dolly_in",
                "lens_mm": 35,
                "lighting_key": "high_key",
                "depth_of_field": "deep",
                "color_temperature": "neutral",
            }

        scenes.append(scene)

    return {
        "version": "1.0",
        "style_playbook": _style_playbook(proposal_packet),
        "scenes": scenes,
        "metadata": {
            "generated_by": "creator-studio/studio/scene_plan_generator.py",
            "generation_mode": "deterministic_local",
            "topic": topic,
            "platform": platform,
            "total_scenes": len(scenes),
            "stage_request_status": stage_request.get("status"),
        },
    }


def generate_scene_plan(project_dir: Path) -> Path:
    run_manifest = _read_json(project_dir / "run.json")
    stage_request = _read_json(project_dir / "scene_plan" / "stage_request.json")
    script = _read_json(project_dir / "script" / "script.json")
    proposal_packet = _read_json(project_dir / "proposal" / "proposal_packet.json")

    scene_plan = build_scene_plan(
        script=script,
        proposal_packet=proposal_packet,
        run_manifest=run_manifest,
        stage_request=stage_request,
    )

    output_path = project_dir / "scene_plan" / "scene_plan.json"
    _write_json(output_path, scene_plan)
    return output_path
