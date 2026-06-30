"""Deterministic local Script artifact generator for Creator Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _selected_concept(proposal_packet: dict[str, Any]) -> dict[str, Any]:
    selected = proposal_packet.get("selected_concept") or {}
    selected_id = selected.get("concept_id")
    concepts = proposal_packet.get("concept_options") or []

    for concept in concepts:
        if concept.get("id") == selected_id:
            return dict(concept)

    if concepts:
        return dict(concepts[0])

    return {
        "title": "Clear Explainer",
        "hook": "Here is the simplest way to understand this.",
        "key_points": [
            "Start with the core problem.",
            "Show the workflow clearly.",
            "End with the practical takeaway.",
        ],
        "core_message": "The viewer should understand the workflow clearly.",
        "cta": "Follow for the next breakdown.",
        "tone": "clear, direct, educational",
    }


def _first_data_source(research_brief: dict[str, Any]) -> str:
    data_points = research_brief.get("data_points") or []
    if data_points:
        first = data_points[0]
        return str(first.get("source_url") or first.get("claim") or "research_brief.data_points[0]")

    sources = research_brief.get("sources") or []
    if sources:
        first = sources[0]
        return str(first.get("url") or first.get("title") or "research_brief.sources[0]")

    return "research_brief"


def build_script(
    *,
    research_brief: dict[str, Any],
    proposal_packet: dict[str, Any],
    run_manifest: dict[str, Any],
    stage_request: dict[str, Any],
) -> dict[str, Any]:
    topic = str(research_brief.get("topic") or run_manifest.get("topic") or "Untitled topic")
    platform = str(run_manifest.get("platform") or stage_request.get("platform") or "instagram")
    pipeline = str(run_manifest.get("pipeline") or stage_request.get("pipeline") or "animated-explainer")

    concept = _selected_concept(proposal_packet)
    title = str(concept.get("title") or f"Explaining {topic}")
    hook = str(concept.get("hook") or f"Here is the simplest way to understand {topic}.")
    key_points = list(concept.get("key_points") or [])
    while len(key_points) < 3:
        key_points.append("Show the idea with a simple visual example.")

    core_message = str(
        concept.get("core_message")
        or f"{topic} is easiest to understand as a clear step-by-step workflow."
    )
    cta = str(concept.get("cta") or "Follow for the next breakdown.")
    tone = str(concept.get("tone") or "clear, direct, educational")
    source_ref = _first_data_source(research_brief)

    return {
        "version": "1.0",
        "title": title,
        "total_duration_seconds": 60,
        "sections": [
            {
                "id": "intro",
                "label": "Hook",
                "text": hook,
                "start_seconds": 0,
                "end_seconds": 8,
                "speaker_directions": f"Open with a {tone} delivery. Keep the first sentence tight.",
                "enhancement_cues": [
                    {
                        "type": "overlay",
                        "description": "Large title card with the core hook.",
                        "timestamp_seconds": 2,
                    }
                ],
                "source_ref": source_ref,
            },
            {
                "id": "setup",
                "label": "Problem Setup",
                "text": f"Most people hear about {topic}, but the hard part is seeing the workflow. {key_points[0]}",
                "start_seconds": 8,
                "end_seconds": 22,
                "speaker_directions": "Slow down slightly and define the problem in plain language.",
                "enhancement_cues": [
                    {
                        "type": "diagram",
                        "description": "Simple left-to-right workflow diagram.",
                        "timestamp_seconds": 12,
                    }
                ],
                "source_ref": source_ref,
            },
            {
                "id": "core",
                "label": "Core Explanation",
                "text": f"{key_points[1]} Then {key_points[2]} That is the difference between a vague AI answer and one grounded in useful context.",
                "start_seconds": 22,
                "end_seconds": 45,
                "speaker_directions": "Use practical, beginner-friendly phrasing.",
                "enhancement_cues": [
                    {
                        "type": "animation",
                        "description": "Animate context moving into the model before the answer appears.",
                        "timestamp_seconds": 28,
                    },
                    {
                        "type": "stat_card",
                        "description": "Show the strongest research-backed claim as a card.",
                        "timestamp_seconds": 36,
                    },
                ],
                "source_ref": source_ref,
            },
            {
                "id": "outro",
                "label": "Takeaway and CTA",
                "text": f"The takeaway: {core_message} {cta}",
                "start_seconds": 45,
                "end_seconds": 60,
                "speaker_directions": "End cleanly with the practical takeaway.",
                "enhancement_cues": [
                    {
                        "type": "overlay",
                        "description": "Final takeaway text with call to action.",
                        "timestamp_seconds": 52,
                    }
                ],
                "source_ref": source_ref,
            },
        ],
        "metadata": {
            "generated_by": "creator-studio/studio/script_generator.py",
            "generation_mode": "deterministic_local",
            "topic": topic,
            "platform": platform,
            "pipeline": pipeline,
            "stage_request_status": stage_request.get("status"),
            "selected_concept_id": (proposal_packet.get("selected_concept") or {}).get("concept_id"),
        },
    }


def generate_script(project_dir: Path) -> Path:
    run_manifest = _read_json(project_dir / "run.json")
    stage_request = _read_json(project_dir / "script" / "stage_request.json")
    research_brief = _read_json(project_dir / "research" / "research_brief.json")
    proposal_packet = _read_json(project_dir / "proposal" / "proposal_packet.json")

    script = build_script(
        research_brief=research_brief,
        proposal_packet=proposal_packet,
        run_manifest=run_manifest,
        stage_request=stage_request,
    )

    output_path = project_dir / "script" / "script.json"
    _write_json(output_path, script)
    return output_path
