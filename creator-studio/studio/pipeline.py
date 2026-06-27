"""Pipeline selection and manifest loading for Creator Studio."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.pipeline_loader import PIPELINE_DEFS_DIR, get_stage_order, load_pipeline as _load_pipeline


@dataclass(frozen=True)
class PipelineStage:
    """Typed view of a manifest stage used by the studio front end."""

    name: str
    skill: str | None
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    tools_available: tuple[str, ...]
    checkpoint_required: bool
    human_approval_default: bool
    produces: tuple[str, ...] = ()
    required_artifacts_in: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """Return a human-readable stage label for CLI output."""

        return self.name.replace("_", " ").title()

    @property
    def skill_path(self) -> str | None:
        """Fully qualified path to the stage director skill, or None if absent."""

        return f"skills/{self.skill}.md" if self.skill else None

    @property
    def canonical_artifact(self) -> str | None:
        """First artifact this stage produces — the contract artifact for the next stage."""

        return self.produces[0] if self.produces else None


@dataclass(frozen=True)
class PipelineDefinition:
    """Typed pipeline manifest wrapper."""

    name: str
    manifest_path: Path
    category: str
    stability: str
    stages: tuple[PipelineStage, ...]
    stage_order: tuple[str, ...]
    required_tools: tuple[str, ...]
    optional_tools: tuple[str, ...]
    manifest: dict[str, Any]

    def stage(self, name: str) -> PipelineStage:
        """Return the named stage or raise a clear error if it does not exist."""

        for s in self.stages:
            if s.name == name:
                return s
        available = ", ".join(s.name for s in self.stages) or "(none)"
        raise KeyError(
            f"Stage '{name}' not found in pipeline '{self.name}'. "
            f"Available stages: {available}"
        )


def select_pipeline(
    scan: dict[str, Any],
    persona: dict[str, Any],
    override: str | None = None,
) -> PipelineDefinition:
    """Choose a pipeline from inbox contents or an explicit override."""

    pipeline_name = override or _infer_pipeline_name(scan, persona)
    return load_manifest(pipeline_name)


def load_manifest(pipeline_name: str) -> PipelineDefinition:
    """Load and validate a manifest, then wrap it in a typed object."""

    manifest = _load_pipeline(pipeline_name)
    manifest_path = PIPELINE_DEFS_DIR / f"{pipeline_name}.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Pipeline manifest not found: {manifest_path}")

    stages = tuple(_build_stage(stage) for stage in manifest["stages"])
    required_tools = _unique_tool_names(stage.required_tools for stage in stages)
    optional_tools = _unique_tool_names(stage.optional_tools for stage in stages)

    return PipelineDefinition(
        name=manifest["name"],
        manifest_path=manifest_path,
        category=manifest.get("category", ""),
        stability=manifest.get("stability", "unknown"),
        stages=stages,
        stage_order=tuple(get_stage_order(manifest)),
        required_tools=required_tools,
        optional_tools=optional_tools,
        manifest=manifest,
    )


def _infer_pipeline_name(scan: dict[str, Any], persona: dict[str, Any]) -> str:
    """Map simple inbox media patterns to the best starter pipeline."""

    if scan["videos"]:
        return "talking-head"
    if scan["images"] and not scan["videos"]:
        return "animated-explainer"
    return persona["default_pipeline"]


def _build_stage(stage: dict[str, Any]) -> PipelineStage:
    """Convert a raw manifest stage into a typed stage object."""

    return PipelineStage(
        name=stage["name"],
        skill=stage.get("skill"),
        required_tools=tuple(stage.get("required_tools", [])),
        optional_tools=tuple(stage.get("optional_tools", [])),
        tools_available=tuple(stage.get("tools_available", [])),
        checkpoint_required=bool(stage.get("checkpoint_required", False)),
        human_approval_default=bool(stage.get("human_approval_default", False)),
        produces=tuple(stage.get("produces", [])),
        required_artifacts_in=tuple(stage.get("required_artifacts_in", [])),
    )


def _unique_tool_names(tool_groups: Any) -> tuple[str, ...]:
    """Preserve first-seen ordering while removing duplicates."""

    ordered: list[str] = []
    seen: set[str] = set()
    for group in tool_groups:
        for tool_name in group:
            if tool_name not in seen:
                ordered.append(tool_name)
                seen.add(tool_name)
    return tuple(ordered)
