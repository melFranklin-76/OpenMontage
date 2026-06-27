from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import jsonschema
import pytest

from tools.base_tool import ToolStatus

from studio.engine import Engine, PreflightResult
from studio.project import initialize_run_manifest
from studio.pipeline import PipelineStage, PipelineDefinition, load_manifest
import studio.engine as engine_module

FIXTURES = Path(__file__).parent / "fixtures"


@dataclass
class FakeTool:
    """Tiny fake used to isolate preflight logic from real tool discovery."""

    status: ToolStatus
    fallback_tools: tuple[str, ...] = ()
    fallback: str | None = None

    def get_status(self) -> ToolStatus:
        return self.status


def _explainer_pipeline() -> PipelineDefinition:
    """Load the real animated-explainer manifest so stage lookups work correctly."""

    return load_manifest("animated-explainer")


def _passed_plan() -> PreflightResult:
    return PreflightResult(
        status="passed",
        pipeline="animated-explainer",
        project_id="demo",
        required_tools=(),
        available_tools=(),
        missing_tools=(),
        optional_warnings=(),
        render_engines=("Remotion",),
        recommendation="Remotion",
        execution_plan=("Research", "Proposal"),
        estimated_stages=2,
        ready_to_execute=True,
        fallback_tools={},
        composition_runtimes={"remotion": True},
        warnings=(),
        capability_summary=(),
        completed_stages=(),
        next_stage="research",
        latest_checkpoint_stage=None,
    )


def _make_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    initialize_run_manifest(project_dir, "demo", "Mel", "animated-explainer", "instagram")
    return project_dir


def _research_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where the research stage is already completed."""

    project_dir = _make_project(tmp_path)
    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    (project_dir / "research").mkdir()
    (project_dir / "research" / "research_brief.json").write_text(
        json.dumps(brief), encoding="utf-8"
    )
    Engine().complete_research(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _proposal_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research AND proposal stages are both completed."""

    project_dir = _research_complete_project(tmp_path)
    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal").mkdir(parents=True)
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )
    Engine().complete_proposal(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _script_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research, proposal, AND script stages are all completed."""

    project_dir = _proposal_complete_project(tmp_path)
    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script").mkdir(parents=True)
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )
    Engine().complete_script(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _scene_plan_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research, proposal, script, AND scene_plan are all completed."""

    project_dir = _script_complete_project(tmp_path)
    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan").mkdir(parents=True)
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )
    Engine().complete_scene_plan(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _assets_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research..scene_plan AND assets are all completed."""

    project_dir = _scene_plan_complete_project(tmp_path)
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets").mkdir(parents=True)
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )
    Engine().complete_assets(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _edit_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research..assets AND edit are all completed."""

    project_dir = _assets_complete_project(tmp_path)
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit").mkdir(parents=True)
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )
    Engine().complete_edit(project_dir, pipeline=_explainer_pipeline())
    return project_dir


def _compose_complete_project(tmp_path: Path) -> Path:
    """Return a project dir where research..edit AND compose are all completed."""

    project_dir = _edit_complete_project(tmp_path)
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose").mkdir(parents=True)
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )
    Engine().complete_compose(project_dir, pipeline=_explainer_pipeline())
    return project_dir


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def test_preflight_returns_passed_result_when_required_tools_exist(
    tmp_path: Path, monkeypatch
) -> None:
    tools = {
        "transcriber": FakeTool(ToolStatus.AVAILABLE),
        "video_compose": FakeTool(ToolStatus.AVAILABLE),
    }
    engine = Engine()
    pipeline = PipelineDefinition(
        name="talking-head",
        manifest_path=tmp_path / "talking-head.yaml",
        category="talking_head",
        stability="beta",
        stages=(
            PipelineStage(
                name="script",
                skill="x",
                required_tools=("transcriber",),
                optional_tools=(),
                tools_available=("transcriber",),
                checkpoint_required=True,
                human_approval_default=True,
            ),
        ),
        stage_order=("script",),
        required_tools=("transcriber",),
        optional_tools=(),
        manifest={},
    )

    monkeypatch.setattr(engine_module.registry, "discover", lambda: None)
    monkeypatch.setattr(
        engine_module.registry,
        "provider_menu_summary",
        lambda: {
            "composition_runtimes": {"ffmpeg": True, "remotion": True, "hyperframes": False},
            "capabilities": [{"capability": "video_generation", "configured": 3, "total": 5}],
            "runtime_warnings": [],
            "setup_offers": [],
        },
    )
    monkeypatch.setattr(engine_module.registry, "get", lambda name: tools.get(name))
    monkeypatch.setattr(engine_module, "get_completed_stages", lambda *args: [])
    monkeypatch.setattr(engine_module, "get_next_stage", lambda *args: "script")
    monkeypatch.setattr(engine_module, "get_latest_checkpoint", lambda *args: None)

    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    initialize_run_manifest(project_dir, "demo", "Mel", "talking-head", "instagram")
    result = engine.preflight(persona={"name": "Mel"}, pipeline=pipeline, project_dir=project_dir)
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result.status == "passed"
    assert result.pipeline == "talking-head"
    assert result.project_id == "demo"
    assert result.missing_tools == ()
    assert result.available_tools == ("transcriber",)
    assert result.render_engines == ("FFmpeg", "Remotion")
    assert result.recommendation == "Remotion"
    assert result.execution_plan == ("Script",)
    assert result.estimated_stages == 1
    assert result.ready_to_execute is True
    assert run_manifest["preflight"] == "passed"
    assert run_manifest["status"] == "awaiting_approval"
    assert run_manifest["ready_to_execute"] is True


def test_preflight_returns_blocked_when_required_tool_has_no_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    tools = {"transcriber": FakeTool(ToolStatus.UNAVAILABLE)}
    engine = Engine()
    pipeline = PipelineDefinition(
        name="talking-head",
        manifest_path=tmp_path / "talking-head.yaml",
        category="talking_head",
        stability="beta",
        stages=(
            PipelineStage(
                name="script",
                skill="x",
                required_tools=("transcriber",),
                optional_tools=(),
                tools_available=("transcriber",),
                checkpoint_required=True,
                human_approval_default=True,
            ),
        ),
        stage_order=("script",),
        required_tools=("transcriber",),
        optional_tools=(),
        manifest={},
    )

    monkeypatch.setattr(engine_module.registry, "discover", lambda: None)
    monkeypatch.setattr(
        engine_module.registry,
        "provider_menu_summary",
        lambda: {
            "composition_runtimes": {"ffmpeg": True},
            "capabilities": [],
            "runtime_warnings": [],
            "setup_offers": [],
        },
    )
    monkeypatch.setattr(engine_module.registry, "get", lambda name: tools.get(name))
    monkeypatch.setattr(engine_module, "get_completed_stages", lambda *args: [])
    monkeypatch.setattr(engine_module, "get_next_stage", lambda *args: "script")
    monkeypatch.setattr(engine_module, "get_latest_checkpoint", lambda *args: None)

    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    initialize_run_manifest(project_dir, "demo", "Mel", "talking-head", "instagram")
    result = engine.preflight(persona={"name": "Mel"}, pipeline=pipeline, project_dir=project_dir)

    assert result.status == "blocked"
    assert result.missing_tools == ("transcriber",)
    assert result.fallback_tools == {}


# ---------------------------------------------------------------------------
# Research stage
# ---------------------------------------------------------------------------

def test_run_blocked_plan_preserves_milestone_3a_behavior(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    plan = _passed_plan()
    blocked = PreflightResult(**{**plan.__dict__, "status": "blocked", "ready_to_execute": False})

    result = engine.run(
        plan=blocked,
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "blocked"
    assert result["execution_started"] is False
    assert not (project_dir / "research").exists()
    assert run_manifest["approved"] is False
    assert run_manifest["status"] == "blocked"


def test_run_prepares_research_handoff(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)

    result = engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="Vector databases",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )

    research_dir = project_dir / "research"
    request = json.loads((research_dir / "stage_request.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((project_dir / "checkpoint_research.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "research_pending"
    assert research_dir.is_dir()
    assert request["stage"] == "research"
    assert request["topic"] == "Vector databases"
    assert request["director_skill_path"] == "skills/pipelines/explainer/research-director.md"
    assert request["schema_path"] == "schemas/artifacts/research_brief.schema.json"
    assert request["output_path"] == "research/research_brief.json"
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "research"
    assert run_manifest["status"] == "research_in_progress"
    assert run_manifest["current_stage"] == "research"
    assert run_manifest["next_stage"] == "research"


def test_complete_research_validates_and_finalizes(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="Vector databases",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    (project_dir / "research" / "research_brief.json").write_text(
        json.dumps(brief), encoding="utf-8"
    )

    result = engine.complete_research(project_dir, pipeline=_explainer_pipeline())

    research_dir = project_dir / "research"
    checkpoint = json.loads((project_dir / "checkpoint_research.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "research_complete"
    assert result["next_stage"] == "proposal"
    assert (research_dir / "citations.json").exists()
    assert (research_dir / "audience_questions.json").exists()
    assert (research_dir / "trend_notes.md").exists()
    assert (research_dir / "visual_references.json").exists()
    assert "research/citations.json" in result["artifacts_written"]
    assert checkpoint["status"] == "completed"
    assert checkpoint["artifacts"]["research_brief"]["topic"] == brief["topic"]
    assert run_manifest["status"] == "research_complete"
    assert run_manifest["completed_stages"] == ["research"]
    assert run_manifest["next_stage"] == "proposal"


def test_complete_research_is_idempotent(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    (project_dir / "research").mkdir()
    (project_dir / "research" / "research_brief.json").write_text(
        json.dumps(brief), encoding="utf-8"
    )
    engine.complete_research(project_dir, pipeline=_explainer_pipeline())

    # Delete a derived artifact; a second call must NOT regenerate it (no rerun).
    (project_dir / "research" / "citations.json").unlink()
    result = engine.complete_research(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "research_already_complete"
    assert result["next_stage"] == "proposal"
    assert not (project_dir / "research" / "citations.json").exists()


def test_run_resume_skips_when_research_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    (project_dir / "research").mkdir()
    (project_dir / "research" / "research_brief.json").write_text(
        json.dumps(brief), encoding="utf-8"
    )
    engine.complete_research(project_dir, pipeline=_explainer_pipeline())

    result = engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="Vector databases",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )

    assert result["status"] == "research_already_complete"
    assert result["next_stage"] == "proposal"


def test_complete_research_rejects_invalid_brief(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    (project_dir / "research").mkdir()
    (project_dir / "research" / "research_brief.json").write_text(
        json.dumps({"version": "1.0", "topic": "incomplete"}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_research(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Milestone 3B.5: manifest-derived stage_request.json fields
# ---------------------------------------------------------------------------

def test_run_uses_manifest_derived_director_skill_path(tmp_path: Path) -> None:
    """director_skill_path in stage_request.json must come from pipeline.stage().skill_path."""

    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    request = json.loads((project_dir / "research" / "stage_request.json").read_text())

    assert request["director_skill_path"] == "skills/pipelines/explainer/research-director.md"


def test_run_uses_manifest_derived_schema_path(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    request = json.loads((project_dir / "research" / "stage_request.json").read_text())

    assert request["schema_path"] == "schemas/artifacts/research_brief.schema.json"


def test_run_uses_manifest_derived_output_path(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    request = json.loads((project_dir / "research" / "stage_request.json").read_text())

    assert request["output_path"] == "research/research_brief.json"


def test_stage_request_includes_requires_approval(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    request = json.loads((project_dir / "research" / "stage_request.json").read_text())

    # research stage has human_approval_default=False in the manifest
    assert "requires_approval" in request
    assert request["requires_approval"] is False


def test_stage_request_includes_checkpoint_required(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _make_project(tmp_path)
    engine.run(
        plan=_passed_plan(),
        project_dir=project_dir,
        topic="t",
        pipeline=_explainer_pipeline(),
        persona="Mel",
        platform="instagram",
    )
    request = json.loads((project_dir / "research" / "stage_request.json").read_text())

    # research stage has checkpoint_required=False in the manifest
    assert "checkpoint_required" in request
    assert request["checkpoint_required"] is False


# ---------------------------------------------------------------------------
# Milestone 3B.5: projections
# ---------------------------------------------------------------------------

def test_unknown_artifact_projector_returns_empty_list(tmp_path: Path) -> None:
    from studio.projections import project_sub_artifacts

    out_dir = tmp_path / "unknown_stage"
    out_dir.mkdir()
    result = project_sub_artifacts("nonexistent_artifact", {"any": "data"}, out_dir)

    assert result == []


def test_research_brief_projector_writes_derived_artifacts(tmp_path: Path) -> None:
    """Projector must produce the same files as the original _derive_sub_artifacts."""

    from studio.projections import project_sub_artifacts

    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    out_dir = tmp_path / "research"
    out_dir.mkdir()

    written = project_sub_artifacts("research_brief", brief, out_dir)

    assert (out_dir / "citations.json").exists()
    assert (out_dir / "audience_questions.json").exists()
    assert (out_dir / "trend_notes.md").exists()
    assert (out_dir / "visual_references.json").exists()
    assert "research/citations.json" in written
    assert "research/audience_questions.json" in written
    assert "research/trend_notes.md" in written
    assert "research/visual_references.json" in written


def test_research_brief_projector_skips_optional_sections_when_absent(tmp_path: Path) -> None:
    from studio.projections import project_sub_artifacts

    brief = json.loads((FIXTURES / "research_brief.json").read_text(encoding="utf-8"))
    brief.pop("trending", None)
    brief.pop("visual_references", None)
    out_dir = tmp_path / "research"
    out_dir.mkdir()

    written = project_sub_artifacts("research_brief", brief, out_dir)

    assert (out_dir / "citations.json").exists()
    assert (out_dir / "audience_questions.json").exists()
    assert not (out_dir / "trend_notes.md").exists()
    assert not (out_dir / "visual_references.json").exists()
    assert "research/trend_notes.md" not in written
    assert "research/visual_references.json" not in written


# ---------------------------------------------------------------------------
# Milestone 3C: Proposal stage
# ---------------------------------------------------------------------------

def test_run_proposal_requires_research_complete(tmp_path: Path) -> None:
    """Proposal handoff must raise when research is not yet complete."""

    engine = Engine()
    project_dir = _make_project(tmp_path)

    with pytest.raises(RuntimeError, match="Research stage must be completed"):
        engine.run_proposal(project_dir, pipeline=_explainer_pipeline())


def test_run_proposal_prepares_handoff(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    result = engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    proposal_dir = project_dir / "proposal"
    request = json.loads((proposal_dir / "stage_request.json").read_text(encoding="utf-8"))
    checkpoint = json.loads(
        (project_dir / "checkpoint_proposal.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "proposal_pending"
    assert proposal_dir.is_dir()
    assert request["stage"] == "proposal"
    # Manifest-derived paths — no hardcoded constants.
    assert request["director_skill_path"] == "skills/pipelines/explainer/proposal-director.md"
    assert request["schema_path"] == "schemas/artifacts/proposal_packet.schema.json"
    assert request["output_path"] == "proposal/proposal_packet.json"
    # Manifest-driven approval and checkpoint policy.
    assert request["requires_approval"] is True    # proposal: human_approval_default=True
    assert request["checkpoint_required"] is True  # proposal: checkpoint_required=True
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "proposal"
    assert run_manifest["status"] == "proposal_in_progress"
    assert run_manifest["current_stage"] == "proposal"
    assert run_manifest["next_stage"] == "proposal"


def test_run_proposal_result_includes_compat_keys(tmp_path: Path) -> None:
    """result must contain proposal_packet_path so console.print_proposal_handoff works."""

    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    result = engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    assert result["proposal_packet_path"] == "proposal/proposal_packet.json"
    assert result["director_skill_path"] == "skills/pipelines/explainer/proposal-director.md"
    assert result["schema_path"] == "schemas/artifacts/proposal_packet.schema.json"


def test_run_proposal_creates_proposal_dir(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "proposal").is_dir()
    assert (project_dir / "proposal" / "stage_request.json").exists()


def test_run_proposal_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_proposal.json").read_text(encoding="utf-8")
    )
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "proposal"


def test_run_proposal_updates_run_json_to_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["status"] == "proposal_in_progress"
    assert run_manifest["current_stage"] == "proposal"


def test_complete_proposal_validates_and_finalizes(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)
    engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )

    result = engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_proposal.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "proposal_complete"
    assert result["next_stage"] == "script"
    assert checkpoint["status"] == "completed"
    assert checkpoint["artifacts"]["proposal_packet"]["version"] == "1.0"
    assert run_manifest["status"] == "proposal_complete"
    assert "proposal" in run_manifest["completed_stages"]
    assert run_manifest["next_stage"] == "script"


def test_complete_proposal_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    """next_stage must come from the manifest, not a hardcoded string."""

    engine = Engine()
    project_dir = _research_complete_project(tmp_path)
    engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )

    result = engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    # The animated-explainer pipeline places script after proposal.
    assert result["next_stage"] == "script"


def test_complete_proposal_is_idempotent(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal").mkdir(parents=True)
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )
    engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    # Second call must return already_complete without rewriting.
    result = engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "proposal_already_complete"
    assert result["next_stage"] == "script"


def test_run_proposal_resume_skips_when_proposal_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal").mkdir(parents=True)
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )
    engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_proposal(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "proposal_already_complete"
    assert result["next_stage"] == "script"


def test_complete_proposal_rejects_invalid_packet(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)
    (project_dir / "proposal").mkdir()
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps({"version": "1.0", "incomplete": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())


def test_complete_proposal_updates_run_json_completed_stages(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    packet = json.loads((FIXTURES / "proposal_packet.json").read_text(encoding="utf-8"))
    (project_dir / "proposal").mkdir(parents=True)
    (project_dir / "proposal" / "proposal_packet.json").write_text(
        json.dumps(packet), encoding="utf-8"
    )

    engine.complete_proposal(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["completed_stages"] == ["research", "proposal"]
    assert run_manifest["current_stage"] == "proposal"


# ---------------------------------------------------------------------------
# Milestone 3D: Script stage
# ---------------------------------------------------------------------------

def test_run_script_requires_proposal_complete(tmp_path: Path) -> None:
    """Script handoff must raise when proposal is not yet complete."""

    engine = Engine()
    project_dir = _research_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Proposal stage must be completed"):
        engine.run_script(project_dir, pipeline=_explainer_pipeline())


def test_run_script_prepares_handoff(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    result = engine.run_script(project_dir, pipeline=_explainer_pipeline())

    script_dir = project_dir / "script"
    request = json.loads((script_dir / "stage_request.json").read_text(encoding="utf-8"))
    checkpoint = json.loads(
        (project_dir / "checkpoint_script.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "script_pending"
    assert script_dir.is_dir()
    assert request["stage"] == "script"
    # Manifest-derived paths — no hardcoded constants.
    assert request["director_skill_path"] == "skills/pipelines/explainer/script-director.md"
    assert request["schema_path"] == "schemas/artifacts/script.schema.json"
    assert request["output_path"] == "script/script.json"
    # Manifest-driven approval and checkpoint policy.
    assert request["requires_approval"] is True    # script: human_approval_default=True
    assert request["checkpoint_required"] is True  # script: checkpoint_required=True
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "script"
    assert run_manifest["status"] == "script_in_progress"
    assert run_manifest["current_stage"] == "script"
    assert run_manifest["next_stage"] == "script"


def test_run_script_result_includes_compat_keys(tmp_path: Path) -> None:
    """result must contain script_path so console.print_script_handoff works."""

    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    result = engine.run_script(project_dir, pipeline=_explainer_pipeline())

    assert result["script_path"] == "script/script.json"
    assert result["director_skill_path"] == "skills/pipelines/explainer/script-director.md"
    assert result["schema_path"] == "schemas/artifacts/script.schema.json"


def test_run_script_creates_script_dir(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "script").is_dir()
    assert (project_dir / "script" / "stage_request.json").exists()


def test_run_script_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_script.json").read_text(encoding="utf-8")
    )
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "script"


def test_run_script_updates_run_json_to_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["status"] == "script_in_progress"
    assert run_manifest["current_stage"] == "script"


def test_complete_script_validates_and_finalizes(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)
    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )

    result = engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_script.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "script_complete"
    assert result["next_stage"] == "scene_plan"
    assert checkpoint["status"] == "completed"
    assert checkpoint["artifacts"]["script"]["title"] == script["title"]
    assert run_manifest["status"] == "script_complete"
    assert "script" in run_manifest["completed_stages"]
    assert run_manifest["next_stage"] == "scene_plan"


def test_complete_script_completed_stages_includes_all_three(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)
    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )
    engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["completed_stages"] == ["research", "proposal", "script"]


def test_complete_script_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    """next_stage must come from the manifest, not a hardcoded string."""

    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)
    engine.run_script(project_dir, pipeline=_explainer_pipeline())

    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )
    result = engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    # The animated-explainer pipeline places scene_plan after script.
    assert result["next_stage"] == "scene_plan"


def test_complete_script_is_idempotent(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script").mkdir(parents=True)
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )
    engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    # Second call must return already_complete without rewriting.
    result = engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "script_already_complete"
    assert result["next_stage"] == "scene_plan"


def test_run_script_resume_skips_when_script_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    script = json.loads((FIXTURES / "script.json").read_text(encoding="utf-8"))
    (project_dir / "script").mkdir(parents=True)
    (project_dir / "script" / "script.json").write_text(
        json.dumps(script), encoding="utf-8"
    )
    engine.complete_script(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_script(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "script_already_complete"
    assert result["next_stage"] == "scene_plan"


def test_complete_script_rejects_invalid_script(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)
    (project_dir / "script").mkdir()
    (project_dir / "script" / "script.json").write_text(
        json.dumps({"version": "1.0", "incomplete": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_script(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Milestone 3E: Scene Plan stage
# ---------------------------------------------------------------------------

def test_run_scene_plan_requires_script_complete(tmp_path: Path) -> None:
    """Scene Plan handoff must raise when script is not yet complete."""

    engine = Engine()
    project_dir = _proposal_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Script stage must be completed"):
        engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())


def test_run_scene_plan_prepares_handoff(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    result = engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    scene_plan_dir = project_dir / "scene_plan"
    request = json.loads((scene_plan_dir / "stage_request.json").read_text(encoding="utf-8"))
    checkpoint = json.loads(
        (project_dir / "checkpoint_scene_plan.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "scene_plan_pending"
    assert scene_plan_dir.is_dir()
    assert request["stage"] == "scene_plan"
    # Manifest-derived paths — no hardcoded constants.
    assert request["director_skill_path"] == "skills/pipelines/explainer/scene-director.md"
    assert request["schema_path"] == "schemas/artifacts/scene_plan.schema.json"
    assert request["output_path"] == "scene_plan/scene_plan.json"
    # Manifest-driven approval and checkpoint policy.
    assert request["requires_approval"] is True
    assert request["checkpoint_required"] is True
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "scene_plan"
    assert run_manifest["status"] == "scene_plan_in_progress"
    assert run_manifest["current_stage"] == "scene_plan"
    assert run_manifest["next_stage"] == "scene_plan"


def test_run_scene_plan_result_includes_compat_keys(tmp_path: Path) -> None:
    """result must contain scene_plan_path so console.print_scene_plan_handoff works."""

    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    result = engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    assert result["scene_plan_path"] == "scene_plan/scene_plan.json"
    assert result["director_skill_path"] == "skills/pipelines/explainer/scene-director.md"
    assert result["schema_path"] == "schemas/artifacts/scene_plan.schema.json"


def test_run_scene_plan_creates_scene_plan_dir(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "scene_plan").is_dir()
    assert (project_dir / "scene_plan" / "stage_request.json").exists()


def test_run_scene_plan_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_scene_plan.json").read_text(encoding="utf-8")
    )
    assert checkpoint["status"] == "in_progress"
    assert checkpoint["stage"] == "scene_plan"


def test_run_scene_plan_updates_run_json_to_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["status"] == "scene_plan_in_progress"
    assert run_manifest["current_stage"] == "scene_plan"


def test_complete_scene_plan_validates_and_finalizes(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)
    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )

    result = engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    checkpoint = json.loads(
        (project_dir / "checkpoint_scene_plan.json").read_text(encoding="utf-8")
    )
    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))

    assert result["status"] == "scene_plan_complete"
    assert result["next_stage"] == "assets"
    assert checkpoint["status"] == "completed"
    assert checkpoint["artifacts"]["scene_plan"]["version"] == "1.0"
    assert run_manifest["status"] == "scene_plan_complete"
    assert "scene_plan" in run_manifest["completed_stages"]
    assert run_manifest["next_stage"] == "assets"


def test_complete_scene_plan_completed_stages_includes_all_four(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)
    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )
    engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    run_manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    assert run_manifest["completed_stages"] == ["research", "proposal", "script", "scene_plan"]


def test_complete_scene_plan_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    """next_stage must come from the manifest, not a hardcoded string."""

    engine = Engine()
    project_dir = _script_complete_project(tmp_path)
    engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )
    result = engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    # The animated-explainer pipeline places assets after scene_plan.
    assert result["next_stage"] == "assets"


def test_complete_scene_plan_is_idempotent(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan").mkdir(parents=True)
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )
    engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    result = engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "scene_plan_already_complete"
    assert result["next_stage"] == "assets"


def test_run_scene_plan_resume_skips_when_scene_plan_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    scene_plan = json.loads((FIXTURES / "scene_plan.json").read_text(encoding="utf-8"))
    (project_dir / "scene_plan").mkdir(parents=True)
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps(scene_plan), encoding="utf-8"
    )
    engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_scene_plan(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "scene_plan_already_complete"
    assert result["next_stage"] == "assets"


def test_complete_scene_plan_rejects_invalid_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)
    (project_dir / "scene_plan").mkdir()
    (project_dir / "scene_plan" / "scene_plan.json").write_text(
        json.dumps({"version": "1.0", "incomplete": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_scene_plan(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Assets stage tests
# ---------------------------------------------------------------------------

def test_run_assets_requires_scene_plan_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _script_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Scene Plan stage must be completed"):
        engine.run_assets(project_dir, pipeline=_explainer_pipeline())


def test_run_assets_creates_workspace(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "assets").is_dir()


def test_run_assets_writes_stage_request(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    sr = json.loads((project_dir / "assets" / "stage_request.json").read_text())
    assert sr["stage"] == "assets"
    assert "director_skill_path" in sr


def test_run_assets_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_assets.json").read_text())
    assert ckpt["status"] == "in_progress"


def test_run_assets_sets_run_json_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "assets_in_progress"


def test_run_assets_result_includes_compat_keys(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    result = engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "assets_pending"
    assert "asset_manifest_path" in result
    assert "director_skill_path" in result
    assert "schema_path" in result


def test_complete_assets_validates_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )

    result = engine.complete_assets(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "assets_complete"


def test_complete_assets_writes_completed_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )

    engine.complete_assets(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_assets.json").read_text())
    assert ckpt["status"] == "completed"


def test_complete_assets_advances_run_json(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )

    engine.complete_assets(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "assets_complete"
    assert run["current_stage"] == "assets"
    assert "assets" in run["completed_stages"]
    assert run["completed_stages"] == ["research", "proposal", "script", "scene_plan", "assets"]
    assert run["next_stage"] == "edit"


def test_complete_assets_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )

    result = engine.complete_assets(project_dir, pipeline=_explainer_pipeline())

    assert result["next_stage"] == "edit"


def test_run_assets_resume_guard(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    asset_manifest = json.loads((FIXTURES / "asset_manifest.json").read_text(encoding="utf-8"))
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps(asset_manifest), encoding="utf-8"
    )
    engine.complete_assets(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_assets(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "assets_already_complete"
    assert result["next_stage"] == "edit"


def test_complete_assets_rejects_invalid_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)
    engine.run_assets(project_dir, pipeline=_explainer_pipeline())
    (project_dir / "assets" / "asset_manifest.json").write_text(
        json.dumps({"version": "1.0", "not_assets": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_assets(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Edit stage tests
# ---------------------------------------------------------------------------

def test_run_edit_requires_assets_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _scene_plan_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Assets stage must be completed"):
        engine.run_edit(project_dir, pipeline=_explainer_pipeline())


def test_run_edit_creates_workspace(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "edit").is_dir()


def test_run_edit_writes_stage_request(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    sr = json.loads((project_dir / "edit" / "stage_request.json").read_text())
    assert sr["stage"] == "edit"
    assert "director_skill_path" in sr


def test_run_edit_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_edit.json").read_text())
    assert ckpt["status"] == "in_progress"


def test_run_edit_sets_run_json_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "edit_in_progress"


def test_run_edit_result_includes_compat_keys(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    result = engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "edit_pending"
    assert "edit_decisions_path" in result
    assert "director_skill_path" in result
    assert "schema_path" in result


def test_complete_edit_validates_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )

    result = engine.complete_edit(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "edit_complete"


def test_complete_edit_writes_completed_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )

    engine.complete_edit(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_edit.json").read_text())
    assert ckpt["status"] == "completed"


def test_complete_edit_advances_run_json(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )

    engine.complete_edit(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "edit_complete"
    assert run["current_stage"] == "edit"
    assert run["completed_stages"] == ["research", "proposal", "script", "scene_plan", "assets", "edit"]
    assert run["next_stage"] == "compose"


def test_complete_edit_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )

    result = engine.complete_edit(project_dir, pipeline=_explainer_pipeline())

    assert result["next_stage"] == "compose"


def test_run_edit_resume_guard(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    edit_decisions = json.loads((FIXTURES / "edit_decisions.json").read_text(encoding="utf-8"))
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps(edit_decisions), encoding="utf-8"
    )
    engine.complete_edit(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_edit(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "edit_already_complete"
    assert result["next_stage"] == "compose"


def test_complete_edit_rejects_invalid_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)
    engine.run_edit(project_dir, pipeline=_explainer_pipeline())
    (project_dir / "edit" / "edit_decisions.json").write_text(
        json.dumps({"version": "1.0", "no_cuts": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_edit(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Compose stage tests
# ---------------------------------------------------------------------------

def test_run_compose_requires_edit_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _assets_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Edit stage must be completed"):
        engine.run_compose(project_dir, pipeline=_explainer_pipeline())


def test_run_compose_creates_workspace(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "compose").is_dir()


def test_run_compose_writes_stage_request(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    sr = json.loads((project_dir / "compose" / "stage_request.json").read_text())
    assert sr["stage"] == "compose"
    assert "director_skill_path" in sr


def test_run_compose_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_compose.json").read_text())
    assert ckpt["status"] == "in_progress"


def test_run_compose_sets_run_json_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "compose_in_progress"


def test_run_compose_result_includes_compat_keys(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    result = engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "compose_pending"
    assert "render_report_path" in result
    assert "director_skill_path" in result
    assert "schema_path" in result


def test_complete_compose_validates_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )

    result = engine.complete_compose(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "compose_complete"


def test_complete_compose_writes_completed_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )

    engine.complete_compose(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_compose.json").read_text())
    assert ckpt["status"] == "completed"


def test_complete_compose_advances_run_json(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )

    engine.complete_compose(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "compose_complete"
    assert run["current_stage"] == "compose"
    assert run["completed_stages"] == [
        "research", "proposal", "script", "scene_plan", "assets", "edit", "compose"
    ]
    assert run["next_stage"] == "publish"


def test_complete_compose_next_stage_is_manifest_driven(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )

    result = engine.complete_compose(project_dir, pipeline=_explainer_pipeline())

    assert result["next_stage"] == "publish"


def test_run_compose_resume_guard(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    render_report = json.loads((FIXTURES / "render_report.json").read_text(encoding="utf-8"))
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps(render_report), encoding="utf-8"
    )
    engine.complete_compose(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_compose(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "compose_already_complete"
    assert result["next_stage"] == "publish"


def test_complete_compose_rejects_invalid_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)
    engine.run_compose(project_dir, pipeline=_explainer_pipeline())
    (project_dir / "compose" / "render_report.json").write_text(
        json.dumps({"version": "1.0", "missing_outputs": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_compose(project_dir, pipeline=_explainer_pipeline())


# ---------------------------------------------------------------------------
# Publish stage tests
# ---------------------------------------------------------------------------

def test_run_publish_requires_compose_complete(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _edit_complete_project(tmp_path)

    with pytest.raises(RuntimeError, match="Compose stage must be completed"):
        engine.run_publish(project_dir, pipeline=_explainer_pipeline())


def test_run_publish_creates_workspace(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)

    engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    assert (project_dir / "publish").is_dir()


def test_run_publish_writes_stage_request(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)

    engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    sr = json.loads((project_dir / "publish" / "stage_request.json").read_text())
    assert sr["stage"] == "publish"
    assert "director_skill_path" in sr


def test_run_publish_writes_in_progress_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)

    engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_publish.json").read_text())
    assert ckpt["status"] == "in_progress"


def test_run_publish_sets_run_json_in_progress(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)

    engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "publish_in_progress"


def test_run_publish_result_includes_compat_keys(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)

    result = engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "publish_pending"
    assert "publish_log_path" in result
    assert "director_skill_path" in result
    assert "schema_path" in result


def test_complete_publish_validates_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    publish_log = json.loads((FIXTURES / "publish_log.json").read_text(encoding="utf-8"))
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps(publish_log), encoding="utf-8"
    )

    result = engine.complete_publish(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "publish_complete"


def test_complete_publish_writes_completed_checkpoint(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    publish_log = json.loads((FIXTURES / "publish_log.json").read_text(encoding="utf-8"))
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps(publish_log), encoding="utf-8"
    )

    engine.complete_publish(project_dir, pipeline=_explainer_pipeline())

    ckpt = json.loads((project_dir / "checkpoint_publish.json").read_text())
    assert ckpt["status"] == "completed"


def test_complete_publish_advances_run_json(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    publish_log = json.loads((FIXTURES / "publish_log.json").read_text(encoding="utf-8"))
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps(publish_log), encoding="utf-8"
    )

    engine.complete_publish(project_dir, pipeline=_explainer_pipeline())

    run = json.loads((project_dir / "run.json").read_text())
    assert run["status"] == "publish_complete"
    assert run["current_stage"] == "publish"
    assert run["completed_stages"] == [
        "research", "proposal", "script", "scene_plan", "assets", "edit", "compose", "publish"
    ]


def test_complete_publish_next_stage_is_none_final_stage(tmp_path: Path) -> None:
    """Publish is the final pipeline stage; next_stage must be None."""

    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    publish_log = json.loads((FIXTURES / "publish_log.json").read_text(encoding="utf-8"))
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps(publish_log), encoding="utf-8"
    )

    result = engine.complete_publish(project_dir, pipeline=_explainer_pipeline())

    assert result["next_stage"] is None


def test_run_publish_resume_guard(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    publish_log = json.loads((FIXTURES / "publish_log.json").read_text(encoding="utf-8"))
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps(publish_log), encoding="utf-8"
    )
    engine.complete_publish(project_dir, pipeline=_explainer_pipeline())

    result = engine.run_publish(project_dir, pipeline=_explainer_pipeline())

    assert result["status"] == "publish_already_complete"
    assert result["next_stage"] is None


def test_complete_publish_rejects_invalid_artifact(tmp_path: Path) -> None:
    engine = Engine()
    project_dir = _compose_complete_project(tmp_path)
    engine.run_publish(project_dir, pipeline=_explainer_pipeline())
    (project_dir / "publish" / "publish_log.json").write_text(
        json.dumps({"version": "1.0", "not_entries": True}), encoding="utf-8"
    )

    with pytest.raises(jsonschema.ValidationError):
        engine.complete_publish(project_dir, pipeline=_explainer_pipeline())
