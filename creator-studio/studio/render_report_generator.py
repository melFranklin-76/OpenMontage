"""Deterministic local render-report generation for Creator Studio smoke runs.

This generator is local-only. It does not render video. It reads existing
Creator Studio artifacts and writes a schema-shaped compose/render_report.json
that describes expected render outputs.
"""

from __future__ import annotations

import json
import re
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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "local_preview"


def _duration_seconds(edit_decisions: dict[str, Any], script: dict[str, Any]) -> float:
    cuts = edit_decisions.get("cuts")
    if isinstance(cuts, list) and cuts:
        end_times = [
            float(cut["out_seconds"])
            for cut in cuts
            if isinstance(cut, dict)
            and isinstance(cut.get("out_seconds"), (int, float))
            and cut.get("out_seconds", 0) >= 0
        ]
        if end_times:
            return round(max(end_times), 2)

    value = script.get("duration_seconds")
    if isinstance(value, (int, float)) and value > 0:
        return round(float(value), 2)

    return 60.0


def _render_runtime(run_json: dict[str, Any], edit_decisions: dict[str, Any]) -> str:
    for source in (edit_decisions, run_json):
        value = source.get("render_runtime")
        if isinstance(value, str) and value.strip():
            return value
    return "remotion"


def _render_grammar(proposal_packet: dict[str, Any], edit_decisions: dict[str, Any]) -> str:
    for source in (edit_decisions, proposal_packet):
        value = source.get("renderer_family") or source.get("render_grammar")
        if isinstance(value, str) and value.strip():
            return value
    return "explainer-data"


def _platform(run_json: dict[str, Any], edit_decisions: dict[str, Any]) -> str:
    metadata = edit_decisions.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("platform")
        if isinstance(value, str) and value.strip() and value != "local":
            return value

    value = run_json.get("platform")
    if isinstance(value, str) and value.strip():
        return value

    return "instagram"


def _topic_slug(run_json: dict[str, Any]) -> str:
    for key in ("topic", "name", "project_name"):
        value = run_json.get(key)
        if isinstance(value, str) and value.strip():
            return _slugify(value)
    return "local_preview"


def _slideshow_risk_score(edit_decisions: dict[str, Any]) -> dict[str, Any]:
    value = edit_decisions.get("slideshow_risk_score")
    if isinstance(value, dict):
        return {
            "average": value.get("average", 0.25),
            "verdict": value.get("verdict", "acceptable"),
        }
    return {
        "average": 0.25,
        "verdict": "acceptable",
    }


def generate_render_report(project_dir: Path) -> Path:
    """Generate compose/render_report.json from local Creator Studio artifacts."""

    run_json = _read_json(project_dir / "run.json")
    script = _read_json(project_dir / "script" / "script.json")
    proposal_packet = _read_json(project_dir / "proposal" / "proposal_packet.json")
    edit_decisions = _read_json(project_dir / "edit" / "edit_decisions.json")

    duration = _duration_seconds(edit_decisions, script)
    topic_slug = _topic_slug(run_json)
    platform = _platform(run_json, edit_decisions)
    render_runtime = _render_runtime(run_json, edit_decisions)
    render_grammar = _render_grammar(proposal_packet, edit_decisions)

    payload: dict[str, Any] = {
        "version": "1.0",
        "outputs": [
            {
                "path": f"compose/output/{topic_slug}_{platform}.mp4",
                "format": "mp4",
                "codec": "h264",
                "audio_codec": "aac",
                "resolution": "1080x1920",
                "fps": 30,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "platform_target": platform,
            },
            {
                "path": f"compose/output/{topic_slug}_horizontal.mp4",
                "format": "mp4",
                "codec": "h264",
                "audio_codec": "aac",
                "resolution": "1920x1080",
                "fps": 30,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "platform_target": "youtube",
            },
        ],
        "render_time_seconds": 0,
        "render_grammar": render_grammar,
        "warnings": [
            "Local smoke render report only; no video file was rendered."
        ],
        "verification_notes": [
            "Render report generated from local script, edit decisions, and proposal metadata.",
            "Output paths are deterministic placeholders for downstream compose/publish handoff.",
        ],
        "slideshow_risk_score": _slideshow_risk_score(edit_decisions),
        "decision_log_ref": "edit/decisions.log",
        "metadata": {
            "topic": run_json.get("topic") or run_json.get("name") or "local-preview",
            "platform": platform,
            "render_runtime": render_runtime,
            "source": "local_render_report_generator",
        },
    }

    return _write_json(project_dir / "compose" / "render_report.json", payload)


__all__ = ["generate_render_report"]
