"""Deterministic local publish-log generation for Creator Studio smoke runs.

This generator is local-only. It does not upload, publish, authenticate, or call
social APIs. It reads the local render report and writes a schema-shaped
publish/publish_log.json describing exported outputs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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


def _topic(run_json: dict[str, Any], render_report: dict[str, Any]) -> str:
    metadata = render_report.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("topic")
        if isinstance(value, str) and value.strip():
            return value

    for key in ("topic", "name", "project_name"):
        value = run_json.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return "local-preview"


def _title_from_topic(topic: str) -> str:
    cleaned = topic.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return "Creator Studio Local Export"
    return cleaned[:1].upper() + cleaned[1:]


def _description(topic: str, platform: str) -> str:
    if platform == "youtube":
        return f"Local Creator Studio export for {topic}. Generated during smoke testing; not published."
    return f"Local Creator Studio export for {topic}. Not published."


def _hashtags(topic: str) -> list[str]:
    words = [
        word.strip("#.,:;!?()[]{}").lower()
        for word in topic.replace("_", " ").replace("-", " ").split()
    ]
    words = [word for word in words if word]

    tags = ["#AI", "#OpenMontage"]
    for word in words[:2]:
        candidate = "#" + "".join(part.capitalize() for part in word.split())
        if candidate not in tags:
            tags.append(candidate)

    return tags


def _outputs(render_report: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = render_report.get("outputs")
    if isinstance(outputs, list):
        return [output for output in outputs if isinstance(output, dict)]
    return []


def _timestamp(base: datetime, index: int) -> str:
    return (base + timedelta(seconds=index)).isoformat().replace("+00:00", "Z")


def generate_publish_log(project_dir: Path) -> Path:
    """Generate publish/publish_log.json from the local render report."""

    run_json = _read_json(project_dir / "run.json")
    render_report = _read_json(project_dir / "compose" / "render_report.json")

    topic = _topic(run_json, render_report)
    title = _title_from_topic(topic)
    hashtags = _hashtags(topic)
    base_time = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)

    entries: list[dict[str, Any]] = []

    for index, output in enumerate(_outputs(render_report)):
        platform = output.get("platform_target")
        if not isinstance(platform, str) or not platform.strip():
            platform = "local"

        export_path = output.get("path")
        if not isinstance(export_path, str) or not export_path.strip():
            export_path = f"compose/output/local_export_{index + 1:02d}.mp4"

        entries.append(
            {
                "platform": platform,
                "status": "exported",
                "export_path": export_path,
                "timestamp": _timestamp(base_time, index),
                "metadata_used": {
                    "title": title,
                    "description": _description(topic, platform),
                    "hashtags": hashtags,
                },
            }
        )

    if not entries:
        entries.append(
            {
                "platform": run_json.get("platform") or "local",
                "status": "pending_review",
                "timestamp": _timestamp(base_time, 0),
                "metadata_used": {
                    "title": title,
                    "description": _description(topic, "local"),
                    "hashtags": hashtags,
                },
            }
        )

    payload: dict[str, Any] = {
        "version": "1.0",
        "entries": entries,
        "metadata": {
            "topic": topic,
            "total_entries": len(entries),
            "exported_at": _timestamp(base_time, len(entries)),
            "source": "local_publish_log_generator",
        },
    }

    return _write_json(project_dir / "publish" / "publish_log.json", payload)


__all__ = ["generate_publish_log"]
