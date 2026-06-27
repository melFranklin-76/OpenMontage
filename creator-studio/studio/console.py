"""Console presentation helpers for the Creator Studio CLI.

Keeping rendering here lets run.py stay a thin orchestration layer while all
OpenMontage logic lives in the engine.
"""

from __future__ import annotations

from typing import Any

from .logger import StudioLogger


def _next_label(result: dict[str, Any]) -> str:
    """Format the manifest-driven next stage for human display.

    Replaces underscores with spaces and title-cases the result.
    Falls back to 'Done' when no next stage is set.
    """

    raw = result.get("next_stage")
    if not raw:
        return "Done"
    return raw.replace("_", " ").title()


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


# ---------------------------------------------------------------------------
# Research stage console helpers
# ---------------------------------------------------------------------------

def print_research_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when research is already done (shared by both commands)."""

    logger.info("Research already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_research_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --approve handoff block (or blocked / resume variants)."""

    status = result.get("status")
    if status == "research_already_complete":
        print_research_already_complete(logger, result)
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
        print_research_already_complete(logger, result)
        return
    logger.info("Research stage complete.")
    logger.info("Artifacts written.")
    for artifact in result.get("artifacts_written", []):
        logger.info(f"  {artifact}")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Research by design.")


# ---------------------------------------------------------------------------
# Proposal stage console helpers
# ---------------------------------------------------------------------------

def print_proposal_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when proposal is already done."""

    logger.info("Proposal already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_proposal_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-proposal handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "proposal_already_complete":
        print_proposal_already_complete(logger, result)
        return
    if status != "proposal_pending":
        logger.info("Proposal cannot start: research stage is not complete.")
        return
    for line in (
        "Proposal stage prepared.",
        "",
        "Workspace:",
        "  proposal/",
        "",
        "Stage request:",
        "  proposal/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['proposal_packet_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Proposal handoff by design.",
        "Run again with --complete-proposal after the proposal packet exists.",
    ):
        logger.info(line)


def print_proposal_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-proposal success block (or resume variant)."""

    if result.get("status") == "proposal_already_complete":
        print_proposal_already_complete(logger, result)
        return
    logger.info("Proposal stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Proposal by design.")


# ---------------------------------------------------------------------------
# Script stage console helpers
# ---------------------------------------------------------------------------

def print_script_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when script is already done."""

    logger.info("Script already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_script_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-script handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "script_already_complete":
        print_script_already_complete(logger, result)
        return
    if status != "script_pending":
        logger.info("Script cannot start: proposal stage is not complete.")
        return
    for line in (
        "Script stage prepared.",
        "",
        "Workspace:",
        "  script/",
        "",
        "Stage request:",
        "  script/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['script_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Script handoff by design.",
        "Run again with --complete-script after the script artifact exists.",
    ):
        logger.info(line)


def print_script_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-script success block (or resume variant)."""

    if result.get("status") == "script_already_complete":
        print_script_already_complete(logger, result)
        return
    logger.info("Script stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Script by design.")


# ---------------------------------------------------------------------------
# Scene Plan stage console helpers
# ---------------------------------------------------------------------------

def print_scene_plan_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when scene plan is already done."""

    logger.info("Scene Plan already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_scene_plan_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-scene-plan handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "scene_plan_already_complete":
        print_scene_plan_already_complete(logger, result)
        return
    if status != "scene_plan_pending":
        logger.info("Scene Plan cannot start: script stage is not complete.")
        return
    for line in (
        "Scene Plan stage prepared.",
        "",
        "Workspace:",
        "  scene_plan/",
        "",
        "Stage request:",
        "  scene_plan/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['scene_plan_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Scene Plan handoff by design.",
        "Run again with --complete-scene-plan after the scene plan artifact exists.",
    ):
        logger.info(line)


def print_scene_plan_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-scene-plan success block (or resume variant)."""

    if result.get("status") == "scene_plan_already_complete":
        print_scene_plan_already_complete(logger, result)
        return
    logger.info("Scene Plan stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Scene Plan by design.")


# ---------------------------------------------------------------------------
# Assets stage console helpers
# ---------------------------------------------------------------------------

def print_assets_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when assets is already done."""

    logger.info("Assets already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_assets_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-assets handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "assets_already_complete":
        print_assets_already_complete(logger, result)
        return
    if status != "assets_pending":
        logger.info("Assets cannot start: scene plan stage is not complete.")
        return
    for line in (
        "Assets stage prepared.",
        "",
        "Workspace:",
        "  assets/",
        "",
        "Stage request:",
        "  assets/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['asset_manifest_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Assets handoff by design.",
        "Run again with --complete-assets after the asset manifest exists.",
    ):
        logger.info(line)


def print_assets_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-assets success block (or resume variant)."""

    if result.get("status") == "assets_already_complete":
        print_assets_already_complete(logger, result)
        return
    logger.info("Assets stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Assets by design.")


# ---------------------------------------------------------------------------
# Edit stage console helpers
# ---------------------------------------------------------------------------

def print_edit_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when edit is already done."""

    logger.info("Edit already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_edit_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-edit handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "edit_already_complete":
        print_edit_already_complete(logger, result)
        return
    if status != "edit_pending":
        logger.info("Edit cannot start: assets stage is not complete.")
        return
    for line in (
        "Edit stage prepared.",
        "",
        "Workspace:",
        "  edit/",
        "",
        "Stage request:",
        "  edit/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['edit_decisions_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Edit handoff by design.",
        "Run again with --complete-edit after the edit artifact exists.",
    ):
        logger.info(line)


def print_edit_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-edit success block (or resume variant)."""

    if result.get("status") == "edit_already_complete":
        print_edit_already_complete(logger, result)
        return
    logger.info("Edit stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Edit by design.")


# ---------------------------------------------------------------------------
# Compose stage console helpers
# ---------------------------------------------------------------------------

def print_compose_already_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the resume block when compose is already done."""

    logger.info("Compose already completed.")
    logger.info(f"Next stage: {_next_label(result)}")


def print_compose_handoff(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --run-compose handoff block (or already-completed variant)."""

    status = result.get("status")
    if status == "compose_already_complete":
        print_compose_already_complete(logger, result)
        return
    if status != "compose_pending":
        logger.info("Compose cannot start: edit stage is not complete.")
        return
    for line in (
        "Compose stage prepared.",
        "",
        "Workspace:",
        "  compose/",
        "",
        "Stage request:",
        "  compose/stage_request.json",
        "",
        "Agent handoff:",
        f"  Read {result['director_skill_path']}",
        f"  Produce {result['render_report_path']}",
        f"  Validate against {result['schema_path']}",
        "",
        "Stopping after Compose handoff by design.",
        "Run again with --complete-compose after the compose artifact exists.",
    ):
        logger.info(line)


def print_compose_complete(logger: StudioLogger, result: dict[str, Any]) -> None:
    """Print the --complete-compose success block (or resume variant)."""

    if result.get("status") == "compose_already_complete":
        print_compose_already_complete(logger, result)
        return
    logger.info("Compose stage complete.")
    logger.info(f"Checkpoint saved: {result['checkpoint_path']}")
    logger.info(f"Elapsed: {result['elapsed_seconds']}s")
    logger.info(f"Next stage: {_next_label(result)}")
    logger.info("Stopping after Compose by design.")
