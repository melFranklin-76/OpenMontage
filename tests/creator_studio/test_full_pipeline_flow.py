"""End-to-end dry-run integration test for Creator Studio.

Drives one project through the entire animated-explainer pipeline using
fixture artifacts only.  No rendering, no network, no provider tools are
called.  Every stage is exercised in order:

  Research → Proposal → Script → Scene Plan → Assets → Edit → Compose → Publish

After the final Publish completion, the test asserts:
  * run.json  is in a fully-complete state
  * All checkpoint files exist and carry the expected status
  * All stage_request.json files exist
  * All canonical artifact files were placed (and are therefore readable)
  * completed_stages contains all eight stages in order
  * next_stage is None  (Publish is the final stage)
"""

import json
from pathlib import Path

from studio.engine import Engine

# Shared helpers — conftest.py puts itself on sys.path at collection time.
from conftest import (
    FIXTURES,
    explainer_pipeline as _pipeline,
    passed_plan as _passed_plan,
    make_project,
    copy_fixture as _copy_fixture,
)

TOPIC = "Vector databases explained"
PERSONA = "Mel"
PLATFORM = "instagram"


# ---------------------------------------------------------------------------
# Full pipeline dry-run test
# ---------------------------------------------------------------------------

def test_full_pipeline_dry_run_reaches_publish_complete(tmp_path: Path) -> None:
    """Drive an entire project through all eight pipeline stages using fixture artifacts."""

    engine = Engine()
    pipeline = _pipeline()
    project_dir = make_project(tmp_path, project_id="dry_run")

    # ------------------------------------------------------------------
    # Stage 1: Research handoff  →  complete
    # ------------------------------------------------------------------
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic=TOPIC,
        pipeline=pipeline,
        persona=PERSONA,
        platform=PLATFORM,
    )
    _copy_fixture("research_brief.json", project_dir / "research" / "research_brief.json")
    engine.complete_research(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 2: Proposal handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_proposal(project_dir, pipeline=pipeline)
    _copy_fixture("proposal_packet.json", project_dir / "proposal" / "proposal_packet.json")
    engine.complete_proposal(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 3: Script handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_script(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("script.json", project_dir / "script" / "script.json")
    engine.complete_script(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 4: Scene Plan handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_scene_plan(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("scene_plan.json", project_dir / "scene_plan" / "scene_plan.json")
    engine.complete_scene_plan(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 5: Assets handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_assets(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("asset_manifest.json", project_dir / "assets" / "asset_manifest.json")
    engine.complete_assets(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 6: Edit handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_edit(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("edit_decisions.json", project_dir / "edit" / "edit_decisions.json")
    engine.complete_edit(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 7: Compose handoff  →  complete
    # ------------------------------------------------------------------
    engine.run_compose(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("render_report.json", project_dir / "compose" / "render_report.json")
    engine.complete_compose(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Stage 8: Publish handoff  →  complete  (final stage)
    # ------------------------------------------------------------------
    engine.run_publish(project_dir, pipeline=pipeline, topic=TOPIC, persona=PERSONA, platform=PLATFORM)
    _copy_fixture("publish_log.json", project_dir / "publish" / "publish_log.json")
    result = engine.complete_publish(project_dir, pipeline=pipeline)

    # ------------------------------------------------------------------
    # Assertions: final Engine result
    # ------------------------------------------------------------------
    assert result["status"] == "publish_complete"
    assert result["next_stage"] is None, "Publish is the final stage; next_stage must be None"

    # ------------------------------------------------------------------
    # Assertions: run.json final state
    # ------------------------------------------------------------------
    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "publish_complete"
    assert run["current_stage"] == "publish"
    assert run["completed_stages"] == [
        "research", "proposal", "script", "scene_plan",
        "assets", "edit", "compose", "publish",
    ]
    assert run.get("next_stage") is None

    # ------------------------------------------------------------------
    # Assertions: all checkpoint files exist and are completed
    # ------------------------------------------------------------------
    for stage in ("research", "proposal", "script", "scene_plan",
                  "assets", "edit", "compose", "publish"):
        ckpt_path = project_dir / f"checkpoint_{stage}.json"
        assert ckpt_path.exists(), f"Missing checkpoint: checkpoint_{stage}.json"
        ckpt = json.loads(ckpt_path.read_text())
        assert ckpt["status"] == "completed", (
            f"checkpoint_{stage}.json has status {ckpt['status']!r}, expected 'completed'"
        )

    # ------------------------------------------------------------------
    # Assertions: all stage_request.json files exist
    # ------------------------------------------------------------------
    for stage in ("research", "proposal", "script", "scene_plan",
                  "assets", "edit", "compose", "publish"):
        sr_path = project_dir / stage / "stage_request.json"
        assert sr_path.exists(), f"Missing stage request: {stage}/stage_request.json"
        sr = json.loads(sr_path.read_text())
        assert sr["stage"] == stage

    # ------------------------------------------------------------------
    # Assertions: all canonical artifact files exist
    # ------------------------------------------------------------------
    canonical_artifacts = {
        "research":   "research/research_brief.json",
        "proposal":   "proposal/proposal_packet.json",
        "script":     "script/script.json",
        "scene_plan": "scene_plan/scene_plan.json",
        "assets":     "assets/asset_manifest.json",
        "edit":       "edit/edit_decisions.json",
        "compose":    "compose/render_report.json",
        "publish":    "publish/publish_log.json",
    }
    for stage, rel_path in canonical_artifacts.items():
        artifact_path = project_dir / rel_path
        assert artifact_path.exists(), f"Missing canonical artifact: {rel_path}"
        data = json.loads(artifact_path.read_text())
        assert data.get("version") == "1.0", (
            f"{rel_path}: expected version '1.0', got {data.get('version')!r}"
        )

    # ------------------------------------------------------------------
    # Assertions: completed_stages is complete (no missing stage)
    # ------------------------------------------------------------------
    expected_stages = [
        "research", "proposal", "script", "scene_plan",
        "assets", "edit", "compose", "publish",
    ]
    assert run["completed_stages"] == expected_stages, (
        f"completed_stages mismatch.\n"
        f"  Expected: {expected_stages}\n"
        f"  Got:      {run['completed_stages']}"
    )
    assert len(run["completed_stages"]) == len(expected_stages), (
        "completed_stages length mismatch — possible duplicate or missing stage"
    )
