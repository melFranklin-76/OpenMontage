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

