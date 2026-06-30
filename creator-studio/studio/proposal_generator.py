"""Deterministic local Proposal artifact generator for Creator Studio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _first_angle(research_brief: dict[str, Any]) -> dict[str, Any]:
    angles = research_brief.get("angles_discovered") or []
    if angles:
        return dict(angles[0])
    return {
        "name": "Clear Explainer",
        "hook": "Here is the simplest way to understand this.",
        "type": "evergreen",
        "why_now": "The topic needs a clear explanation.",
        "grounded_in": [],
    }


def build_proposal_packet(
    *,
    research_brief: dict[str, Any],
    run_manifest: dict[str, Any],
    stage_request: dict[str, Any],
) -> dict[str, Any]:
    topic = str(research_brief.get("topic") or run_manifest.get("topic") or "Untitled topic")
    pipeline = str(run_manifest.get("pipeline") or stage_request.get("pipeline") or "animated-explainer")
    platform = str(run_manifest.get("platform") or stage_request.get("platform") or "instagram")
    angle = _first_angle(research_brief)

    hook = str(angle.get("hook") or f"Here is the simplest way to understand {topic}.")
    title = str(angle.get("name") or "Clear Explainer")
    grounded_in = list(angle.get("grounded_in") or [])

    concept_id = "c1"

    return {
        "version": "1.0",
        "concept_options": [
            {
                "id": concept_id,
                "title": title,
                "hook": hook,
                "narrative_structure": "myth_busting",
                "visual_approach": "Flat motion graphics showing the problem, the retrieval step, and the generated answer.",
                "suggested_playbook": "flat-motion-graphics",
                "target_audience": "Technical beginners and builders who want a clear practical explanation.",
                "target_platform": platform,
                "target_duration_seconds": 75,
                "key_points": [
                    "Retrieval happens before generation.",
                    "Vector search helps find related context.",
                    "Better context usually produces a better answer.",
                ],
                "core_message": f"{topic} is easiest to understand as a workflow: retrieve the right context, then generate the answer.",
                "cta": "Follow for the next breakdown.",
                "tone": "clear, direct, educational",
                "grounded_in": grounded_in,
                "why_this_works": "The selected concept converts the research brief into a simple visual explanation with a clear hook and practical audience fit.",
            },
            {
                "id": "c2",
                "title": "Search Before Speaking",
                "hook": "The smartest AI answer starts before the model writes a single word.",
                "narrative_structure": "data_narrative",
                "visual_approach": "Step-by-step retrieval pipeline with search, ranking, and answer generation.",
                "target_audience": "Developers evaluating retrieval workflows.",
                "target_platform": platform,
                "target_duration_seconds": 60,
                "key_points": [
                    "Search retrieves the candidate context.",
                    "Ranking chooses the strongest chunks.",
                    "Generation turns context into a response.",
                ],
                "core_message": "The retrieval step is where answer quality starts.",
                "cta": "Save this before building your next AI feature.",
                "tone": "practical, analytical",
                "grounded_in": grounded_in,
                "why_this_works": "This concept focuses on the most actionable part of the research: retrieval quality before generation.",
            },
            {
                "id": "c3",
                "title": "Vectors Are Meaning Coordinates",
                "hook": "Vector databases turn meaning into coordinates so related ideas can find each other.",
                "narrative_structure": "story",
                "visual_approach": "Animated map of meaning clusters with a question traveling to nearby context.",
                "target_audience": "Non-experts who have heard about AI search but do not understand embeddings.",
                "target_platform": platform,
                "target_duration_seconds": 60,
                "key_points": [
                    "Embeddings represent meaning numerically.",
                    "Nearby vectors usually mean related ideas.",
                    "Retrieval gives the model relevant material before it answers.",
                ],
                "core_message": "A vector database is a search system for meaning.",
                "cta": "Share this with someone learning AI.",
                "tone": "plainspoken, visual",
                "grounded_in": grounded_in,
                "why_this_works": "The analogy is easy to visualize and fits short-form explainer content.",
            },
        ],
        "selected_concept": {
            "concept_id": concept_id,
            "rationale": "This concept uses the strongest research angle, gives the clearest hook, and fits the animated explainer pipeline.",
            "modifications": [],
        },
        "production_plan": {
            "pipeline": pipeline,
            "playbook": "flat-motion-graphics",
            "stages": [
                {
                    "stage": "script",
                    "tools": [
                        {
                            "tool_name": "local_text_generator",
                            "role": "Drafts structured narration from the selected proposal concept.",
                            "provider": "local",
                            "available": True,
                            "estimated_cost_usd": 0.0,
                            "why_this_provider": "Local deterministic generation keeps 4B offline and testable.",
                        }
                    ],
                    "approach": "Write a concise explainer script using hook, three key points, and CTA.",
                    "fallback_if_unavailable": "Use the selected proposal concept directly as the script outline.",
                },
                {
                    "stage": "assets",
                    "tools": [
                        {
                            "tool_name": "local_asset_planner",
                            "role": "Plans flat-motion-graphics scenes without generating media.",
                            "provider": "local",
                            "available": True,
                            "estimated_cost_usd": 0.0,
                            "why_this_provider": "4B does not call image, video, or audio providers.",
                        }
                    ],
                    "approach": "Plan simple diagrams, stat cards, and text callouts.",
                    "fallback_if_unavailable": "Use text-only scene cards.",
                },
                {
                    "stage": "compose",
                    "tools": [
                        {
                            "tool_name": "remotion",
                            "role": "Future renderer target for assembling scenes.",
                            "provider": "local",
                            "available": True,
                            "estimated_cost_usd": 0.0,
                        }
                    ],
                    "approach": "Keep compose fixture-only until later milestones.",
                    "fallback_if_unavailable": "Keep fixture-only compose output.",
                },
            ],
            "quality_tradeoffs": [
                {
                    "tradeoff": "Local deterministic proposal generation vs external LLM ideation",
                    "recommendation": "Local deterministic proposal generation",
                    "quality_impact": "Lower creative variety, but stable tests and no provider dependency.",
                }
            ],
            "delivery_promise": {
                "promise_type": "teacher_explainer",
                "motion_required": False,
                "source_required": False,
                "tone_mode": "educational",
                "quality_floor": "presentable",
                "approved_fallback": "still_led",
            },
            "renderer_family": "explainer-teacher",
            "render_runtime": "remotion",
            "music_source": {
                "source_type": "user_library",
                "provider": "local",
                "mood_direction": "focused, low-key background",
                "estimated_cost_usd": 0.0,
            },
        },
        "cost_estimate": {
            "total_estimated_usd": 0.0,
            "line_items": [
                {
                    "tool": "local_text_generator",
                    "operation": "Proposal generation",
                    "quantity": 1,
                    "estimated_usd": 0.0,
                    "notes": "Deterministic local generation.",
                }
            ],
            "budget_verdict": "no_budget_set",
            "savings_options": [
                "Keep all proposal generation local.",
                "Defer paid provider choices to later milestones.",
            ],
        },
        "approval": {
            "status": "pending",
        },
    }


def generate_proposal_packet(project_dir: Path) -> Path:
    run_manifest = _read_json(project_dir / "run.json")
    stage_request = _read_json(project_dir / "proposal" / "stage_request.json")
    research_brief = _read_json(project_dir / "research" / "research_brief.json")

    packet = build_proposal_packet(
        research_brief=research_brief,
        run_manifest=run_manifest,
        stage_request=stage_request,
    )

    output_path = project_dir / "proposal" / "proposal_packet.json"
    _write_json(output_path, packet)
    return output_path
