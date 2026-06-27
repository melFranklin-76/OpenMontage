from __future__ import annotations

import json
from pathlib import Path

from studio.project import (
    METADATA_VERSION,
    RUN_MANIFEST_VERSION,
    create_project,
    update_run_manifest,
)


def test_create_project_generates_versioned_metadata(tmp_path: Path) -> None:
    persona = {"name": "Mel"}

    project_dir = create_project(
        name=None,
        persona=persona,
        pipeline=None,
        platform="instagram",
        projects_dir=tmp_path,
    )

    metadata = json.loads((project_dir / "metadata.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert project_dir.exists()
    assert metadata["version"] == METADATA_VERSION
    assert metadata["persona"] == "Mel"
    assert metadata["platform"] == "instagram"
    assert metadata["status"] == "planning"
    assert metadata["project_id"] == project_dir.name
    assert run_manifest["version"] == RUN_MANIFEST_VERSION
    assert run_manifest["approved"] is False
    assert run_manifest["preflight"] is None
    assert run_manifest["status"] == "planning"
    assert run_manifest["current_stage"] is None
    assert run_manifest["completed_stages"] == []
    assert run_manifest["next_stage"] is None


def test_update_run_manifest_modifies_stage_fields_and_preserves_others(tmp_path: Path) -> None:
    project_dir = create_project(
        name=None,
        persona={"name": "Mel"},
        pipeline="animated-explainer",
        platform="instagram",
        projects_dir=tmp_path,
    )

    update_run_manifest(
        project_dir,
        status="research_complete",
        current_stage="research",
        completed_stages=["research"],
        next_stage="proposal",
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert run_manifest["current_stage"] == "research"
    assert run_manifest["completed_stages"] == ["research"]
    assert run_manifest["next_stage"] == "proposal"
    # Earlier fields remain intact after a partial update.
    assert run_manifest["version"] == RUN_MANIFEST_VERSION
    assert run_manifest["pipeline"] == "animated-explainer"


def test_create_project_uses_slug_when_name_is_provided(tmp_path: Path) -> None:
    persona = {"name": "Mel"}

    project_dir = create_project(
        name="AI Gym Boyfriend",
        persona=persona,
        pipeline=None,
        platform="instagram",
        projects_dir=tmp_path,
    )

    assert project_dir.name == "ai-gym-boyfriend"

