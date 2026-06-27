from __future__ import annotations

from studio.pipeline import PipelineDefinition, load_manifest, select_pipeline


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

