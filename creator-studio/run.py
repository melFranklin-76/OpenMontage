#!/usr/bin/env python3
"""Creator Studio entry point - Milestone 3C (Proposal stage integration)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import INBOX_DIR, LOGS_DIR, PERSONAS_DIR, PROJECTS_DIR
from studio import (
    Engine,
    create_project,
    get_logger,
    load_manifest,
    load_persona,
    scan_inbox,
    select_pipeline,
)
from studio.console import (
    print_assets_complete,
    print_assets_handoff,
    print_compose_complete,
    print_compose_handoff,
    print_edit_complete,
    print_edit_handoff,
    print_proposal_complete,
    print_proposal_handoff,
    print_publish_complete,
    print_publish_handoff,
    print_research_already_complete,
    print_research_complete,
    print_research_handoff,
    print_scene_plan_complete,
    print_scene_plan_handoff,
    print_script_complete,
    print_script_handoff,
    render_execution_plan,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Creator Studio")
    parser.add_argument("--persona", default=str(PERSONAS_DIR / "mel.yaml"))
    parser.add_argument("--platform")
    parser.add_argument("--pipeline")
    parser.add_argument("--name")
    parser.add_argument("--topic")
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--complete-research", dest="complete_research", action="store_true")
    parser.add_argument("--run-proposal", dest="run_proposal", action="store_true")
    parser.add_argument("--complete-proposal", dest="complete_proposal", action="store_true")
    parser.add_argument("--run-script", dest="run_script", action="store_true")
    parser.add_argument("--complete-script", dest="complete_script", action="store_true")
    parser.add_argument("--run-scene-plan", dest="run_scene_plan", action="store_true")
    parser.add_argument("--complete-scene-plan", dest="complete_scene_plan", action="store_true")
    parser.add_argument("--run-assets", dest="run_assets", action="store_true")
    parser.add_argument("--complete-assets", dest="complete_assets", action="store_true")
    parser.add_argument("--run-edit", dest="run_edit", action="store_true")
    parser.add_argument("--complete-edit", dest="complete_edit", action="store_true")
    parser.add_argument("--run-compose", dest="run_compose", action="store_true")
    parser.add_argument("--complete-compose", dest="complete_compose", action="store_true")
    parser.add_argument("--run-publish", dest="run_publish", action="store_true")
    parser.add_argument("--complete-publish", dest="complete_publish", action="store_true")
    return parser.parse_args()


def _latest_project() -> Path:
    """Resolve the most recently touched project that has a run manifest."""

    projects = [p for p in PROJECTS_DIR.iterdir() if (p / "run.json").exists()]
    if not projects:
        raise FileNotFoundError("No project found. Run with --approve first.")
    return max(projects, key=lambda p: p.stat().st_mtime)


def _resolve():
    """Load project dir, pipeline, and logger for stage completion commands."""

    project_dir = _latest_project()
    manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    pipeline = load_manifest(manifest["pipeline"])
    logger = get_logger(project_id=project_dir.name, logs_dir=LOGS_DIR)
    return project_dir, pipeline, logger


def _complete_research() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_research(project_dir, pipeline=pipeline)
    print_research_complete(logger, result)
    return 0


def _run_proposal() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_proposal(project_dir, pipeline=pipeline)
    print_proposal_handoff(logger, result)
    return 0


def _complete_proposal() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_proposal(project_dir, pipeline=pipeline)
    print_proposal_complete(logger, result)
    return 0


def _run_script() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_script(project_dir, pipeline=pipeline)
    print_script_handoff(logger, result)
    return 0


def _complete_script() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_script(project_dir, pipeline=pipeline)
    print_script_complete(logger, result)
    return 0


def _run_scene_plan() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_scene_plan(project_dir, pipeline=pipeline)
    print_scene_plan_handoff(logger, result)
    return 0


def _complete_scene_plan() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_scene_plan(project_dir, pipeline=pipeline)
    print_scene_plan_complete(logger, result)
    return 0


def _run_assets() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_assets(project_dir, pipeline=pipeline)
    print_assets_handoff(logger, result)
    return 0


def _complete_assets() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_assets(project_dir, pipeline=pipeline)
    print_assets_complete(logger, result)
    return 0


def _run_edit() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_edit(project_dir, pipeline=pipeline)
    print_edit_handoff(logger, result)
    return 0


def _complete_edit() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_edit(project_dir, pipeline=pipeline)
    print_edit_complete(logger, result)
    return 0


def _run_compose() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_compose(project_dir, pipeline=pipeline)
    print_compose_handoff(logger, result)
    return 0


def _complete_compose() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_compose(project_dir, pipeline=pipeline)
    print_compose_complete(logger, result)
    return 0


def _run_publish() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().run_publish(project_dir, pipeline=pipeline)
    print_publish_handoff(logger, result)
    return 0


def _complete_publish() -> int:
    project_dir, pipeline, logger = _resolve()
    result = Engine().complete_publish(project_dir, pipeline=pipeline)
    print_publish_complete(logger, result)
    return 0


def main() -> int:
    args = parse_args()

    if args.complete_publish:
        return _complete_publish()
    if args.run_publish:
        return _run_publish()
    if args.complete_compose:
        return _complete_compose()
    if args.run_compose:
        return _run_compose()
    if args.complete_edit:
        return _complete_edit()
    if args.run_edit:
        return _run_edit()
    if args.complete_assets:
        return _complete_assets()
    if args.run_assets:
        return _run_assets()
    if args.complete_scene_plan:
        return _complete_scene_plan()
    if args.run_scene_plan:
        return _run_scene_plan()
    if args.complete_script:
        return _complete_script()
    if args.run_script:
        return _run_script()
    if args.complete_proposal:
        return _complete_proposal()
    if args.run_proposal:
        return _run_proposal()
    if args.complete_research:
        return _complete_research()

    persona = load_persona(Path(args.persona))
    scan = scan_inbox(INBOX_DIR)
    platform = args.platform or persona["default_platform"]
    pipeline = select_pipeline(scan=scan, persona=persona, override=args.pipeline)
    project_dir = create_project(
        name=args.name,
        persona=persona,
        pipeline=pipeline.name,
        platform=platform,
        projects_dir=PROJECTS_DIR,
    )
    engine = Engine()
    plan = engine.preflight(persona=persona, pipeline=pipeline, project_dir=project_dir)
    logger = get_logger(project_id=project_dir.name, logs_dir=LOGS_DIR)
    render_execution_plan(logger, persona, scan, platform, pipeline, plan)

    if args.approve:
        topic = args.topic or args.name or project_dir.name
        result = engine.run(
            plan=plan,
            project_dir=project_dir,
            topic=topic,
            pipeline=pipeline,
            persona=persona["name"],
            platform=platform,
        )
        if result.get("status") == "research_already_complete":
            print_research_already_complete(logger, result)
        else:
            print_research_handoff(logger, result)
    else:
        logger.info("Waiting for approval...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
