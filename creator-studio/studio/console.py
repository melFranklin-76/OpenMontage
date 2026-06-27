"""Console presentation helpers for the Creator Studio CLI.

Keeping rendering here lets run.py stay a thin orchestration layer while all
OpenMontage logic lives in the engine.
"""

from __future__ import annotations

from typing import Any

from .logger import StudioLogger


def _next_label(result: dict[str, Any]) -> str:
    """Title-case the manifest-driven next stage (defaults to Proposal)."""

    return (result.get("next_stage") or "proposal").title()


def render_execution_plan(
    logger: StudioLogger,
    persona: dict[str, Any],
    scan: dict[str, Any],
    platform: str,
    pipeline: Any,
    plan: Any,
) -> None:
    """Print the banner, inbox scan, and preflight execution plan."""

    for line in (
        "==================================",
        f"{persona['name'].upper()} CREATOR STUDIO",
        "==================================",
        f"Project: {plan.project_id}",
        f"Persona: {persona['name']}",
        f"Pipeline: {pipeline.name.replace('-', ' ').title()}",
        f"Platform: {platform.title()}",
        f"Status: {plan.status.upper()}",
        "==================================",
        "Scanning inbox...",
        "Found:",
        f"{len(scan['videos'])} videos",
        f"{len(scan['images'])} images",
        f"{len(scan['audio'])} audio",
        "",
        "==================================",
        "EXECUTION PLAN",
        "==================================",
        "Stages",
    ):
        logger.info(line)
    for stage in plan.execution_plan:
        logger.info(f"[x] {stage}")
    logger.info(f"Capability Status: {plan.status.upper()}")
    if plan.missing_tools:
        logger.info(f"Missing Required Tools: {', '.join(plan.missing_tools)}")
    for cap in plan.capability_summary:
        logger.info(f"{cap['capability']}: {cap['configured']} available of {cap['total']}")
    logger.info(f"Render Engines: {', '.join(plan.render_engines) or 'None'}")
    logger.info(f"Recommendation: {plan.recommendation or 'None'}")
    for warning in plan.warnings:
        logger.info(f"Warning: {warning}")


def print_research_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --approve handoff block (or blocked / resume variants)."""

    status = result.get("status")
    if status == "research_already_complete":
        logger.info("Research already completed.")
        logger.info(f"Next stage: {_next_label(result)}")
        return
    if status != "research_pending":
        logger.info("Execution remains blocked. Resolve preflight issues before stage work.")
        return
    for line in (
        "Research stage prepared.",
        "",
        "Workspace:",
        "  research/",
        "",
        "Stage request:",
        "  research/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['research_brief_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Research handoff by design.",
        "Run again with --complete-research after the research brief exists.",
    ):
        logger.info(line)


def print_research_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-research success block (or resume variant)."""

    if result.get("status") == "research_already_complete":
        logger.info("Research already completed.")
        logger.info(f"Next stage: {_next_label(result)}")
        return
    logger.info("Research stage complete.")
    logger.info("Artifacts written.")
    for artifact in result.get("artifacts_written", []):
        logger.info(f"  {artifact}")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Research by design.")
