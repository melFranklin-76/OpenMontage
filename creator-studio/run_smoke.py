#!/usr/bin/env python3
"""Creator Studio fixture-only live smoke - Milestone 3N (Developer UX).

Turns the manual "seed fixture, run CLI, repeat" verification into a single
repeatable developer check. It drives the *real* CLI (run.py) end-to-end:

    Research -> Proposal -> Script -> Scene Plan -> Assets -> Edit -> Compose -> Publish

For each stage it copies the canonical fixture artifact into the stage
workspace, then invokes the matching `--complete-<stage>` (and `--run-<stage>`
handoff) command, exactly as a developer would by hand.

Local-only and fixture-only by design: it never renders, never publishes,
never calls a provider/social API, and adds no OAuth/scheduler/analytics. It
only orchestrates the existing CLI and the committed test fixtures.

Usage:
    python creator-studio/run_smoke.py --pipeline animated-explainer --name vector-databases
    python creator-studio/run_smoke.py --keep   # leave the project on disk to inspect
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# config lives alongside this script; tests/ fixtures live at the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import INBOX_DIR, PROJECTS_DIR, REPO_ROOT, STUDIO_ROOT

RUN_PY = STUDIO_ROOT / "run.py"
FIXTURES_DIR = REPO_ROOT / "tests" / "creator_studio" / "fixtures"
DEMO_MEDIA = INBOX_DIR / "demo.mp4"

# Ordered pipeline. Each tuple is (stage, fixture_filename). The stage name is
# both the CLI flag suffix (dashes) and the workspace subdir (underscores), so
# we derive the dashed flag form when invoking the CLI.
RESEARCH = ("research", "research_brief.json")
POST_RESEARCH_STAGES: tuple[tuple[str, str], ...] = (
    ("proposal", "proposal_packet.json"),
    ("script", "script.json"),
    ("scene_plan", "scene_plan.json"),
    ("assets", "asset_manifest.json"),
    ("edit", "edit_decisions.json"),
    ("compose", "render_report.json"),
    ("publish", "publish_log.json"),
)
ALL_STAGES: tuple[str, ...] = (RESEARCH[0],) + tuple(s for s, _ in POST_RESEARCH_STAGES)


class SmokeError(RuntimeError):
    """Raised when a CLI step fails or a final-state assertion does not hold."""


def _slugify(value: str) -> str:
    """Mirror studio.project._slugify so we can locate the created project dir."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Project name must include letters or numbers.")
    return slug


def _flag(stage: str) -> str:
    """Convert an underscore stage name to its dashed CLI suffix (scene_plan -> scene-plan)."""

    return stage.replace("_", "-")


def _run_cli(*flags: str) -> None:
    """Invoke run.py as a subprocess so we exercise the real CLI dispatch."""

    cmd = [sys.executable, str(RUN_PY), *flags]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    label = " ".join(flags)
    if proc.returncode != 0:
        # Surface the captured output only on failure to keep the happy path quiet.
        raise SmokeError(
            f"CLI step failed: {label}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    print(f"  ok: {label}")


def _seed(project_dir: Path, stage: str, fixture: str) -> None:
    """Copy a fixture artifact into a stage workspace, simulating agent output."""

    src = FIXTURES_DIR / fixture
    if not src.exists():
        raise SmokeError(f"Missing fixture: {src}")
    dest_dir = project_dir / stage
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest_dir / fixture)
    print(f"  seeded: {stage}/{fixture}")


def _resolve_latest_project() -> Path:
    """Resolve the most recently touched project (matches run.py's resolver)."""

    projects = [p for p in PROJECTS_DIR.iterdir() if (p / "run.json").exists()]
    if not projects:
        raise SmokeError("No project found after --approve.")
    return max(projects, key=lambda p: p.stat().st_mtime)


def _prepare_inputs(name: str) -> None:
    """Auto-clean any prior same-named project and ensure an inbox placeholder."""

    slug = _slugify(name)
    stale = PROJECTS_DIR / slug
    if stale.exists():
        print(f"Removing stale smoke project: {stale}")
        shutil.rmtree(stale)
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    if not DEMO_MEDIA.exists():
        DEMO_MEDIA.touch()
        print(f"Created inbox placeholder: {DEMO_MEDIA}")


def _assert_final_state(project_dir: Path) -> None:
    """Assert the project reached publish_complete with every stage recorded."""

    run_json = json.loads((project_dir / "run.json").read_text(encoding="utf-8"))
    problems: list[str] = []

    if run_json.get("status") != "publish_complete":
        problems.append(f"status={run_json.get('status')!r} (expected 'publish_complete')")
    if run_json.get("current_stage") != "publish":
        problems.append(f"current_stage={run_json.get('current_stage')!r} (expected 'publish')")
    if run_json.get("next_stage") is not None:
        problems.append(f"next_stage={run_json.get('next_stage')!r} (expected null)")
    if list(run_json.get("completed_stages", [])) != list(ALL_STAGES):
        problems.append(
            f"completed_stages={run_json.get('completed_stages')!r} (expected {list(ALL_STAGES)})"
        )

    for stage in ALL_STAGES:
        checkpoint = project_dir / f"checkpoint_{stage}.json"
        if not checkpoint.exists():
            problems.append(f"missing checkpoint: {checkpoint.name}")
        request = project_dir / stage / "stage_request.json"
        if not request.exists():
            problems.append(f"missing stage_request: {stage}/stage_request.json")

    if problems:
        raise SmokeError("Final-state verification failed:\n  - " + "\n  - ".join(problems))


def _cleanup(project_dir: Path) -> None:
    """Remove smoke artifacts so the working tree stays clean."""

    if project_dir.exists():
        shutil.rmtree(project_dir)
    if DEMO_MEDIA.exists():
        DEMO_MEDIA.unlink()
    print("Cleaned up smoke artifacts (project dir + inbox placeholder).")


def run_smoke(*, pipeline: str, name: str, topic: str, keep: bool) -> int:
    """Drive the full fixture-only pipeline and verify the terminal state."""

    print("=" * 38)
    print("CREATOR STUDIO FIXTURE SMOKE (local-only)")
    print("=" * 38)
    print(f"Pipeline: {pipeline}")
    print(f"Name:     {name}")

    _prepare_inputs(name)

    print("\n[approve] create project + research handoff")
    _run_cli("--approve", "--name", name, "--topic", topic, "--pipeline", pipeline)
    project_dir = _resolve_latest_project()
    print(f"Project dir: {project_dir}")

    print("\n[research] seed brief + complete")
    _seed(project_dir, RESEARCH[0], RESEARCH[1])
    _run_cli("--complete-research", "--pipeline", pipeline)

    for stage, fixture in POST_RESEARCH_STAGES:
        flag = _flag(stage)
        print(f"\n[{stage}] run handoff + seed + complete")
        _run_cli(f"--run-{flag}", "--pipeline", pipeline)
        _seed(project_dir, stage, fixture)
        _run_cli(f"--complete-{flag}", "--pipeline", pipeline)

    print("\n[verify] final run.json state")
    _assert_final_state(project_dir)
    print("  ok: publish_complete with all 8 stages, checkpoints, and stage requests")

    if keep:
        print(f"\nKept smoke project for inspection: {project_dir}")
    else:
        print()
        _cleanup(project_dir)

    print("\nSMOKE PASSED")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Creator Studio fixture-only live smoke")
    parser.add_argument("--pipeline", default="animated-explainer")
    parser.add_argument("--name", default="vector-databases")
    parser.add_argument(
        "--topic",
        default="How vector databases power retrieval augmented generation",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the smoke project on disk instead of cleaning it up.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return run_smoke(
            pipeline=args.pipeline,
            name=args.name,
            topic=args.topic,
            keep=args.keep,
        )
    except SmokeError as exc:
        print(f"\nSMOKE FAILED\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
