"""Project creation helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


METADATA_VERSION = 1
RUN_MANIFEST_VERSION = 1
STUDIO_VERSION = "0.1.0"
PROJECT_ID_PATTERN = re.compile(r"^(?P<prefix>\d{4}-\d{2}-\d{2})_(?P<index>\d{3})$")


def create_project(
    name: str | None,
    persona: dict[str, Any],
    pipeline: str | None,
    platform: str,
    projects_dir: Path,
) -> Path:
    """Create a project directory and initialize versioned metadata."""

    projects_dir.mkdir(parents=True, exist_ok=True)
    # Use local time for human-facing project ids so the folder name matches
    # the creator's working day, especially around midnight UTC.
    created_at = datetime.now().astimezone()
    project_id = _build_project_id(name=name, projects_dir=projects_dir, created_at=created_at)

    project_dir = projects_dir / project_id
    project_dir.mkdir(parents=True, exist_ok=False)

    metadata = {
        "version": METADATA_VERSION,
        "project_id": project_id,
        "pipeline": pipeline,
        "persona": persona["name"],
        "platform": platform,
        "created": created_at.isoformat(),
        "status": "planning",
    }

    metadata_path = project_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    initialize_run_manifest(
        project_dir=project_dir,
        project_id=project_id,
        persona=persona["name"],
        pipeline=pipeline,
        platform=platform,
    )
    return project_dir


def initialize_run_manifest(
    project_dir: Path,
    project_id: str,
    persona: str,
    pipeline: str | None,
    platform: str,
) -> Path:
    """Create the canonical run state file for resumable studio execution."""

    run_manifest = {
        "version": RUN_MANIFEST_VERSION,
        "studio_version": STUDIO_VERSION,
        "project_id": project_id,
        "persona": persona.lower(),
        "pipeline": pipeline,
        "platform": platform,
        "preflight": None,
        "approved": False,
        "started": None,
        "completed": None,
        "status": "planning",
        "current_stage": None,
        "completed_stages": [],
        "next_stage": None,
        "execution_plan": [],
        "estimated_stages": 0,
        "ready_to_execute": False,
    }
    path = project_dir / "run.json"
    path.write_text(json.dumps(run_manifest, indent=2), encoding="utf-8")
    return path


def update_run_manifest(project_dir: Path, **updates: Any) -> Path:
    """Persist run state transitions without forcing callers to manage JSON."""

    path = project_dir / "run.json"
    current = json.loads(path.read_text(encoding="utf-8"))
    current.update(updates)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return path


def _build_project_id(name: str | None, projects_dir: Path, created_at: datetime) -> str:
    """Generate a stable project id.

    A generated daily counter keeps inbox runs ordered and easy to scan.
    When the user provides a name, the slug becomes the project id.
    """

    if name and name.strip():
        return _slugify(name)

    prefix = created_at.strftime("%Y-%m-%d")
    max_index = 0

    for path in projects_dir.iterdir():
        if not path.is_dir():
            continue
        match = PROJECT_ID_PATTERN.match(path.name)
        if match and match.group("prefix") == prefix:
            max_index = max(max_index, int(match.group("index")))

    return f"{prefix}_{max_index + 1:03d}"


def _slugify(value: str) -> str:
    """Create a filesystem-safe slug without hiding the original intent."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Project name must include letters or numbers.")
    return slug

