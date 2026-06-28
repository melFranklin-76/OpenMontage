from __future__ import annotations

import pytest

from studio.pipeline import PipelineDefinition, PipelineStage, load_manifest, select_pipeline


def test_load_manifest_returns_typed_pipeline_definition() -> None:
    pipeline = load_manifest("talking-head")

    assert isinstance(pipeline, PipelineDefinition)
    assert pipeline.name == "talking-head"
    assert "script" in pipeline.stage_order
    assert "transcriber" in pipeline.required_tools


def test_select_pipeline_prefers_talking_head_when_video_exists() -> None:
    pipeline = select_pipeline(
        scan={"videos": ["clip.mp4"], "images": [], "audio": [], "total": 1},
        persona={"default_pipeline": "talking-head"},
        override=None,
    )

    assert pipeline.name == "talking-head"


def test_select_pipeline_honors_cli_override() -> None:
    pipeline = select_pipeline(
        scan={"videos": [], "images": [], "audio": [], "total": 0},
        persona={"default_pipeline": "talking-head"},
        override="animation",
    )

    assert pipeline.name == "animation"


# ---------------------------------------------------------------------------
# Manifest-derived stage fields (Milestone 3B.5)
# ---------------------------------------------------------------------------

def test_research_stage_produces_research_brief() -> None:
    pipeline = load_manifest("animated-explainer")
    stage = pipeline.stage("research")

    assert stage.produces == ("research_brief",)


def test_research_stage_required_artifacts_in_is_empty() -> None:
    # Research is the first stage; it has no upstream artifact dependencies.
    pipeline = load_manifest("animated-explainer")
    stage = pipeline.stage("research")

    assert stage.required_artifacts_in == ()


def test_research_stage_skill_path() -> None:
    pipeline = load_manifest("animated-explainer")
    stage = pipeline.stage("research")

    assert stage.skill_path == "skills/pipelines/explainer/research-director.md"


def test_research_stage_canonical_artifact() -> None:
    pipeline = load_manifest("animated-explainer")
    stage = pipeline.stage("research")

    assert stage.canonical_artifact == "research_brief"


def test_pipeline_stage_lookup_returns_correct_stage() -> None:
    pipeline = load_manifest("animated-explainer")

    assert pipeline.stage("research").name == "research"
    assert pipeline.stage("proposal").name == "proposal"


def test_pipeline_stage_lookup_raises_for_unknown_stage() -> None:
    pipeline = load_manifest("animated-explainer")

    with pytest.raises(KeyError, match="no_such_stage"):
        pipeline.stage("no_such_stage")


def test_stage_without_skill_has_no_skill_path() -> None:
    stage = PipelineStage(
        name="dummy",
        skill=None,
        required_tools=(),
        optional_tools=(),
        tools_available=(),
        checkpoint_required=False,
        human_approval_default=False,
    )

    assert stage.skill_path is None
    assert stage.canonical_artifact is None

