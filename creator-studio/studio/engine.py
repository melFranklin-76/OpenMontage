"""OpenMontage-facing adapter for Creator Studio."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from lib.checkpoint import (
    get_completed_stages,
    get_latest_checkpoint,
    get_next_stage,
    read_checkpoint,
    write_checkpoint,
)
from schemas.artifacts import validate_artifact
from tools.base_tool import ToolStatus
from tools.tool_registry import registry

from .pipeline import PipelineDefinition
from .project import update_run_manifest
from .projections import project_sub_artifacts


def schema_path_for(artifact: str) -> str:
    """Return the canonical schema path for any artifact name."""

    return f"schemas/artifacts/{artifact}.schema.json"


@dataclass(frozen=True)
class PreflightResult:
    """Structured preflight result that the CLI or a future UI can reuse."""

    status: Literal["passed", "degraded", "blocked"]
    pipeline: str
    project_id: str
    required_tools: tuple[str, ...]
    available_tools: tuple[str, ...]
    missing_tools: tuple[str, ...]
    optional_warnings: tuple[str, ...]
    render_engines: tuple[str, ...]
    recommendation: str | None
    execution_plan: tuple[str, ...]
    estimated_stages: int
    ready_to_execute: bool
    fallback_tools: dict[str, tuple[str, ...]]
    composition_runtimes: dict[str, bool]
    warnings: tuple[str, ...]
    capability_summary: tuple[dict[str, Any], ...]
    completed_stages: tuple[str, ...]
    next_stage: str | None
    latest_checkpoint_stage: str | None


class Engine:
    """Encapsulate all OpenMontage-aware logic behind a small public surface."""

    # ------------------------------------------------------------------
    # Public API — stable across milestones
    # ------------------------------------------------------------------

    def preflight(
        self,
        persona: dict[str, Any],
        pipeline: PipelineDefinition,
        project_dir: Path,
    ) -> PreflightResult:
        """Discover capabilities, inspect the manifest, and build an execution plan."""

        registry.discover()
        summary = registry.provider_menu_summary()

        missing_tools: list[str] = []
        fallback_tools: dict[str, tuple[str, ...]] = {}
        warnings: list[str] = []
        optional_warnings: list[str] = []
        available_tools = [
            tool_name
            for tool_name in dict.fromkeys(
                list(pipeline.required_tools)
                + list(pipeline.optional_tools)
                + [tool for stage in pipeline.stages for tool in stage.tools_available]
            )
            if self._tool_is_available(tool_name)
        ]

        for tool_name in pipeline.required_tools:
            tool = registry.get(tool_name)
            if tool and tool.get_status() == ToolStatus.AVAILABLE:
                continue

            missing_tools.append(tool_name)
            fallbacks = self._collect_available_fallbacks(tool_name)
            if fallbacks:
                fallback_tools[tool_name] = fallbacks
                warnings.append(
                    f"Required tool '{tool_name}' is unavailable; fallback available: {', '.join(fallbacks)}"
                )
            else:
                warnings.append(f"Required tool '{tool_name}' is unavailable and has no fallback.")

        missing_optional = [
            tool_name
            for tool_name in pipeline.optional_tools
            if not self._tool_is_available(tool_name)
        ]
        for tool_name in missing_optional:
            optional_warning = f"Optional tool '{tool_name}' is unavailable."
            optional_warnings.append(optional_warning)
            warnings.append(optional_warning)

        for warning in summary.get("runtime_warnings", []):
            warnings.append(warning)

        status = self._determine_status(
            missing_tools=missing_tools,
            fallback_tools=fallback_tools,
            missing_optional=missing_optional,
            runtime_warnings=summary.get("runtime_warnings", []),
        )

        composition_runtimes = {
            key: bool(value)
            for key, value in (summary.get("composition_runtimes") or {}).items()
        }
        available_render_engines = tuple(
            self._format_runtime_name(runtime)
            for runtime, enabled in composition_runtimes.items()
            if enabled
        )
        latest_checkpoint = get_latest_checkpoint(project_dir.parent, project_dir.name)
        execution_plan = tuple(stage.label for stage in pipeline.stages)
        recommendation = self._recommend_render_engine(composition_runtimes)
        ready_to_execute = status in {"passed", "degraded"}
        result = PreflightResult(
            status=status,
            pipeline=pipeline.name,
            project_id=project_dir.name,
            required_tools=pipeline.required_tools,
            available_tools=tuple(available_tools),
            missing_tools=tuple(missing_tools),
            optional_warnings=tuple(optional_warnings),
            render_engines=available_render_engines,
            recommendation=recommendation,
            execution_plan=execution_plan,
            estimated_stages=len(execution_plan),
            ready_to_execute=ready_to_execute,
            fallback_tools=fallback_tools,
            composition_runtimes=composition_runtimes,
            warnings=tuple(warnings),
            capability_summary=tuple(summary.get("capabilities", [])),
            completed_stages=tuple(
                get_completed_stages(project_dir.parent, project_dir.name, pipeline.name)
            ),
            next_stage=get_next_stage(project_dir.parent, project_dir.name, pipeline.name),
            latest_checkpoint_stage=latest_checkpoint["stage"] if latest_checkpoint else None,
        )
        update_run_manifest(
            project_dir,
            preflight=result.status,
            status="awaiting_approval" if result.ready_to_execute else "blocked",
            next_stage=result.next_stage,
            execution_plan=list(result.execution_plan),
            estimated_stages=result.estimated_stages,
            ready_to_execute=result.ready_to_execute,
            available_tools=list(result.available_tools),
            missing_tools=list(result.missing_tools),
            optional_warnings=list(result.optional_warnings),
            render_engines=list(result.render_engines),
            recommendation=result.recommendation,
        )
        return result

    def run(
        self,
        plan: PreflightResult,
        project_dir: Path,
        *,
        topic: str,
        pipeline: PipelineDefinition,
        persona: str,
        platform: str,
    ) -> dict[str, Any]:
        """Coordinate the Research stage as an agent handoff (Planning -> Research -> STOP).

        Delegates to _prepare_stage so the same logic can later drive Proposal,
        Script, and every subsequent stage without duplication. The
        ``research_brief_path`` key is added here for backward compatibility.
        """

        result = self._prepare_stage(
            plan,
            project_dir,
            stage_name="research",
            topic=topic,
            pipeline=pipeline,
            persona=persona,
            platform=platform,
        )
        # Backward-compat alias expected by run.py and existing tests.
        if result.get("status") == "research_pending":
            result["research_brief_path"] = result["output_path"]
        return result

    def complete_research(
        self,
        project_dir: Path,
        *,
        pipeline: PipelineDefinition,
    ) -> dict[str, Any]:
        """Validate the agent-produced research brief and finalize the stage.

        Delegates to _complete_stage. The public signature is preserved so that
        run.py, tests, and any external callers remain unchanged.
        """

        return self._complete_stage(project_dir, stage_name="research", pipeline=pipeline)

    # ------------------------------------------------------------------
    # Generic stage lifecycle helpers (manifest-driven)
    # ------------------------------------------------------------------

    def _prepare_stage(
        self,
        plan: PreflightResult,
        project_dir: Path,
        *,
        stage_name: str,
        topic: str,
        pipeline: PipelineDefinition,
        persona: str,
        platform: str,
    ) -> dict[str, Any]:
        """Generic stage-handoff preparation driven entirely by the pipeline manifest.

        Reads stage metadata (skill path, canonical artifact, approval policy)
        from the manifest rather than hardcoded constants. Handles the resume
        guard and blocked-preflight guard identically to the original Research
        implementation.
        """

        pipeline_dir = project_dir.parent
        project_id = project_dir.name

        # Resume guard: do not rerun if the stage already has a completed checkpoint.
        if self._stage_completed(project_dir, stage_name):
            return {
                "status": f"{stage_name}_already_complete",
                "execution_started": False,
                "pipeline": pipeline.name,
                "next_stage": get_next_stage(pipeline_dir, project_id, pipeline.name),
            }

        # Blocked guard: preserve preflight gate; never create artifacts.
        if not plan.ready_to_execute:
            update_run_manifest(project_dir, approved=False, status="blocked")
            return {
                "status": "blocked",
                "execution_started": False,
                "pipeline": pipeline.name,
                "next_stage": plan.next_stage,
            }

        stage = pipeline.stage(stage_name)
        artifact = stage.canonical_artifact
        workspace = project_dir / stage_name
        workspace.mkdir(parents=True, exist_ok=True)
        output_path = f"{stage_name}/{artifact}.json"

        stage_request: dict[str, Any] = {
            "stage": stage_name,
            "topic": topic,
            "persona": persona,
            "platform": platform,
            "pipeline": pipeline.name,
            "director_skill_path": stage.skill_path,
            "schema_path": schema_path_for(artifact),
            "output_path": output_path,
            "requires_approval": stage.human_approval_default,
            "checkpoint_required": stage.checkpoint_required,
            "instruction": (
                f"Agent must read the director skill and produce a schema-valid "
                f"{artifact} at output_path before running --complete-{stage_name}."
            ),
        }
        (workspace / "stage_request.json").write_text(
            json.dumps(stage_request, indent=2), encoding="utf-8"
        )

        checkpoint_path = write_checkpoint(
            pipeline_dir=pipeline_dir,
            project_id=project_id,
            stage=stage_name,
            status="in_progress",
            artifacts={},
            pipeline_type=pipeline.name,
        )

        update_run_manifest(
            project_dir,
            approved=True,
            started=datetime.now(timezone.utc).isoformat(),
            status=f"{stage_name}_in_progress",
            current_stage=stage_name,
            next_stage=stage_name,
        )

        return {
            "status": f"{stage_name}_pending",
            "execution_started": False,
            "pipeline": pipeline.name,
            "workspace": f"{stage_name}/",
            "stage_request_path": f"{stage_name}/stage_request.json",
            "director_skill_path": stage.skill_path,
            "schema_path": schema_path_for(artifact),
            "output_path": output_path,
            "checkpoint_path": str(checkpoint_path),
            "next_stage": stage_name,
        }

    def _complete_stage(
        self,
        project_dir: Path,
        *,
        stage_name: str,
        pipeline: PipelineDefinition,
    ) -> dict[str, Any]:
        """Generic stage-completion handler driven by the pipeline manifest.

        Loads the canonical artifact produced by the agent, validates it against
        the registered schema, runs the stage projector to derive companion files,
        writes the completed checkpoint, and advances run.json.
        """

        pipeline_dir = project_dir.parent
        project_id = project_dir.name

        # Idempotency guard.
        if self._stage_completed(project_dir, stage_name):
            return {
                "status": f"{stage_name}_already_complete",
                "pipeline": pipeline.name,
                "next_stage": get_next_stage(pipeline_dir, project_id, pipeline.name),
            }

        start = time.monotonic()
        stage = pipeline.stage(stage_name)
        artifact = stage.canonical_artifact
        workspace = project_dir / stage_name
        artifact_path = workspace / f"{artifact}.json"

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"{artifact} not found at {artifact_path}. Produce it via the "
                f"{stage_name}-director skill before running --complete-{stage_name}."
            )

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        validate_artifact(artifact, data)

        artifacts_written = project_sub_artifacts(artifact, data, workspace)

        checkpoint_path = write_checkpoint(
            pipeline_dir=pipeline_dir,
            project_id=project_id,
            stage=stage_name,
            status="completed",
            artifacts={artifact: data},
            pipeline_type=pipeline.name,
        )

        next_stage = get_next_stage(pipeline_dir, project_id, pipeline.name)
        completed_stages = get_completed_stages(pipeline_dir, project_id, pipeline.name)
        update_run_manifest(
            project_dir,
            status=f"{stage_name}_complete",
            current_stage=stage_name,
            completed_stages=completed_stages,
            next_stage=next_stage,
            completed=datetime.now(timezone.utc).isoformat(),
        )

        return {
            "status": f"{stage_name}_complete",
            "pipeline": pipeline.name,
            "checkpoint_path": str(checkpoint_path),
            "artifacts_written": artifacts_written,
            "next_stage": next_stage,
            "elapsed_seconds": round(time.monotonic() - start, 3),
        }

    # ------------------------------------------------------------------
    # Stage state helpers
    # ------------------------------------------------------------------

    def _stage_completed(self, project_dir: Path, stage_name: str) -> bool:
        """Return True when the named stage has a completed checkpoint."""

        checkpoint = read_checkpoint(project_dir.parent, project_dir.name, stage_name)
        return bool(checkpoint and checkpoint.get("status") == "completed")

    def _research_completed(self, project_dir: Path) -> bool:
        """Backward-compatible alias for _stage_completed('research')."""

        return self._stage_completed(project_dir, "research")

    # ------------------------------------------------------------------
    # Preflight helpers
    # ------------------------------------------------------------------

    def _collect_available_fallbacks(self, tool_name: str) -> tuple[str, ...]:
        """Return available fallback tool names for a missing tool."""

        tool = registry.get(tool_name)
        if tool is None:
            return ()

        fallback_names = list(tool.fallback_tools or [])
        if tool.fallback and tool.fallback not in fallback_names:
            fallback_names.append(tool.fallback)

        available = [
            name
            for name in fallback_names
            if self._tool_is_available(name)
        ]
        return tuple(available)

    @staticmethod
    def _determine_status(
        *,
        missing_tools: list[str],
        fallback_tools: dict[str, tuple[str, ...]],
        missing_optional: list[str],
        runtime_warnings: list[str],
    ) -> str:
        """Classify preflight health as passed, degraded, or blocked."""

        blocked_tools = [
            tool_name for tool_name in missing_tools if not fallback_tools.get(tool_name)
        ]
        if blocked_tools:
            return "blocked"
        if missing_tools or missing_optional or runtime_warnings:
            return "degraded"
        return "passed"

    @staticmethod
    def _recommend_render_engine(composition_runtimes: dict[str, bool]) -> str | None:
        """Choose a default render engine recommendation for plan display."""

        if composition_runtimes.get("remotion"):
            return "Remotion"
        if composition_runtimes.get("hyperframes"):
            return "HyperFrames"
        if composition_runtimes.get("ffmpeg"):
            return "FFmpeg"
        return None

    @staticmethod
    def _format_runtime_name(runtime: str) -> str:
        """Normalize runtime labels for human-facing output."""

        labels = {"ffmpeg": "FFmpeg", "hyperframes": "HyperFrames", "remotion": "Remotion"}
        return labels.get(runtime, runtime.title())

    @staticmethod
    def _tool_is_available(tool_name: str) -> bool:
        """Check whether a registry tool exists and is currently available."""

        tool = registry.get(tool_name)
        return bool(tool and tool.get_status() == ToolStatus.AVAILABLE)
