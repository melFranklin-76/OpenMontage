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

# Paths recorded in the research handoff so the agent knows which director skill
# to follow and which schema the produced brief must satisfy. OpenMontage has no
# programmatic stage runner; the agent is the control plane.
DIRECTOR_SKILL_PATH = "skills/pipelines/explainer/research-director.md"
RESEARCH_SCHEMA_PATH = "schemas/artifacts/research_brief.schema.json"
RESEARCH_BRIEF_OUTPUT = "research/research_brief.json"


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

        OpenMontage has no Python stage runner, so this prepares the workspace,
        records an ``in_progress`` checkpoint, and hands control to the agent who
        follows the research-director skill. It never synthesizes research itself.
        """

        pipeline_dir = project_dir.parent
        project_id = project_dir.name

        # Resume guard: never rerun setup once research is complete.
        if self._research_completed(project_dir):
            return {
                "status": "research_already_complete",
                "execution_started": False,
                "pipeline": pipeline.name,
                "next_stage": get_next_stage(pipeline_dir, project_id, pipeline.name),
            }

        # Blocked guard: preserve Milestone 3A behavior; create no artifacts.
        if not plan.ready_to_execute:
            update_run_manifest(project_dir, approved=False, status="blocked")
            return {
                "status": "blocked",
                "execution_started": False,
                "pipeline": pipeline.name,
                "next_stage": plan.next_stage,
            }

        research_dir = project_dir / "research"
        research_dir.mkdir(parents=True, exist_ok=True)
        stage_request = {
            "stage": "research",
            "topic": topic,
            "persona": persona,
            "platform": platform,
            "pipeline": pipeline.name,
            "director_skill_path": DIRECTOR_SKILL_PATH,
            "schema_path": RESEARCH_SCHEMA_PATH,
            "output_path": RESEARCH_BRIEF_OUTPUT,
            "instruction": (
                "Agent must read the director skill and produce a schema-valid "
                "research_brief at output_path before running --complete-research."
            ),
        }
        request_path = research_dir / "stage_request.json"
        request_path.write_text(json.dumps(stage_request, indent=2), encoding="utf-8")

        checkpoint_path = write_checkpoint(
            pipeline_dir=pipeline_dir,
            project_id=project_id,
            stage="research",
            status="in_progress",
            artifacts={},
            pipeline_type=pipeline.name,
        )

        update_run_manifest(
            project_dir,
            approved=True,
            started=datetime.now(timezone.utc).isoformat(),
            status="research_in_progress",
            current_stage="research",
            next_stage="research",
        )
        return {
            "status": "research_pending",
            "execution_started": False,
            "pipeline": pipeline.name,
            "workspace": "research/",
            "stage_request_path": "research/stage_request.json",
            "director_skill_path": DIRECTOR_SKILL_PATH,
            "schema_path": RESEARCH_SCHEMA_PATH,
            "research_brief_path": RESEARCH_BRIEF_OUTPUT,
            "checkpoint_path": str(checkpoint_path),
            "next_stage": "research",
        }

    def complete_research(
        self,
        project_dir: Path,
        *,
        pipeline: PipelineDefinition,
    ) -> dict[str, Any]:
        """Validate the agent-produced research brief and finalize the stage.

        Reads ``research/research_brief.json`` (produced by the agent via the
        director skill), validates it against the schema, derives sub-artifacts
        from the validated brief only, writes the first real ``completed``
        checkpoint, and advances ``run.json`` to the manifest-driven next stage.
        """

        pipeline_dir = project_dir.parent
        project_id = project_dir.name

        # Duplicate prevention: do not re-ingest or rewrite once completed.
        if self._research_completed(project_dir):
            return {
                "status": "research_already_complete",
                "pipeline": pipeline.name,
                "next_stage": get_next_stage(pipeline_dir, project_id, pipeline.name),
            }

        start = time.monotonic()
        brief_path = project_dir / "research" / "research_brief.json"
        if not brief_path.exists():
            raise FileNotFoundError(
                f"Research brief not found at {brief_path}. Produce it via the "
                "research-director skill before running --complete-research."
            )

        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        # Raises jsonschema.ValidationError if the agent's brief is not valid.
        validate_artifact("research_brief", brief)

        artifacts_written = self._derive_sub_artifacts(brief, project_dir / "research")

        checkpoint_path = write_checkpoint(
            pipeline_dir=pipeline_dir,
            project_id=project_id,
            stage="research",
            status="completed",
            artifacts={"research_brief": brief},
            pipeline_type=pipeline.name,
        )

        next_stage = get_next_stage(pipeline_dir, project_id, pipeline.name)
        completed_stages = get_completed_stages(pipeline_dir, project_id, pipeline.name)
        update_run_manifest(
            project_dir,
            status="research_complete",
            current_stage="research",
            completed_stages=completed_stages,
            next_stage=next_stage,
            completed=datetime.now(timezone.utc).isoformat(),
        )
        return {
            "status": "research_complete",
            "pipeline": pipeline.name,
            "checkpoint_path": str(checkpoint_path),
            "artifacts_written": artifacts_written,
            "next_stage": next_stage,
            "elapsed_seconds": round(time.monotonic() - start, 3),
        }

    def _research_completed(self, project_dir: Path) -> bool:
        """Return True when a completed research checkpoint already exists."""

        checkpoint = read_checkpoint(project_dir.parent, project_dir.name, "research")
        return bool(checkpoint and checkpoint.get("status") == "completed")

    @staticmethod
    def _derive_sub_artifacts(brief: dict[str, Any], research_dir: Path) -> list[str]:
        """Project sub-artifacts from the validated brief only (never fabricate)."""

        research_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        def _dump(name: str, data: Any) -> None:
            (research_dir / name).write_text(json.dumps(data, indent=2), encoding="utf-8")
            written.append(f"research/{name}")

        _dump("citations.json", brief["sources"])
        _dump("audience_questions.json", brief["audience_insights"]["common_questions"])

        trending = brief.get("trending")
        if trending:
            (research_dir / "trend_notes.md").write_text(
                _render_trend_notes(trending), encoding="utf-8"
            )
            written.append("research/trend_notes.md")

        visual_references = brief.get("visual_references")
        if visual_references:
            _dump("visual_references.json", visual_references)

        return written

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


def _render_trend_notes(trending: dict[str, Any]) -> str:
    """Render trend_notes.md from the brief's trending block (real data only)."""

    lines = ["# Trend Notes", ""]
    for item in trending.get("recent_developments") or []:
        if "## Recent Developments" not in lines:
            lines.append("## Recent Developments")
        headline = item.get("headline", "")
        date = item.get("date", "")
        suffix = f" ({date})" if date else ""
        relevance = item.get("relevance", "")
        entry = f"- {headline}{suffix} — {relevance}".rstrip(" —")
        if item.get("url"):
            entry += f" [{item['url']}]"
        lines.append(entry)
    discussions = trending.get("active_discussions") or []
    if discussions:
        lines.extend(["", "## Active Discussions"])
        for item in discussions:
            platform = item.get("platform", "")
            topic_or_url = item.get("topic_or_url", "")
            sentiment = item.get("sentiment", "")
            lines.append(f"- {platform}: {topic_or_url} — {sentiment}".rstrip(" —"))
    window = trending.get("timeliness_window")
    if window:
        lines.extend(["", f"Timeliness window: {window}"])
    return "\n".join(lines).rstrip() + "\n"

