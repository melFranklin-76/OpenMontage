#!/usr/bin/env python3
"""Creator Studio entry point - Milestone 3B (Research stage integration)."""

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
    print_research_already_complete,
    print_research_complete,
    print_research_handoff,
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
    return parser.parse_args()


def _latest_project() -> Path:
    """Resolve the most recently touched project that has a run manifest."""

    projects = [p for p in PROJECTS_DIR.iterdir() if (p / "run.json").exists()]
    if not projects:
        raise FileNotFoundError("No project found. Run with --approve first.")
    return max(projects, key=lambda p: p.stat().st_mtime)


def _complete_research() -> int:
    project_dir = _latest_project()
    manifest = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    pipeline = load_manifest(manifest["pipeline"])
    logger = get_logger(project_id=project_dir.name, logs_dir=LOGS_DIR)
    result = Engine().complete_research(project_dir, pipeline=pipeline)
    print_research_complete(logger, result)
    return 0


def main() -> int:
    args = parse_args()
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
        print_research_handoff(logger, result)
    else:
        logger.info("Waiting for approval...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
