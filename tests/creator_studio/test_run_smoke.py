from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SMOKE = REPO_ROOT / "creator-studio" / "run_smoke.py"
PROJECT_NAME = "pytest-smoke-command"
PROJECT_DIR = REPO_ROOT / "creator-studio" / "projects" / PROJECT_NAME
DEMO_MP4 = REPO_ROOT / "creator-studio" / "inbox" / "demo.mp4"

EXPECTED_STAGES = [
    "research",
    "proposal",
    "script",
    "scene_plan",
    "assets",
    "edit",
    "compose",
    "publish",
]


def _clean_smoke_artifacts() -> None:
    shutil.rmtree(PROJECT_DIR, ignore_errors=True)
    DEMO_MP4.unlink(missing_ok=True)


def test_run_smoke_help_lists_expected_flags() -> None:
    result = subprocess.run(
        [sys.executable, str(RUN_SMOKE), "--help"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--pipeline" in result.stdout
    assert "--name" in result.stdout
    assert "--topic" in result.stdout
    assert "--keep" in result.stdout


def test_run_smoke_reaches_publish_complete_with_keep() -> None:
    _clean_smoke_artifacts()

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(RUN_SMOKE),
                "--pipeline",
                "animated-explainer",
                "--name",
                PROJECT_NAME,
                "--topic",
                "How vector databases power retrieval augmented generation",
                "--keep",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )

        assert result.returncode == 0, result.stdout + "\n" + result.stderr

        run_json = PROJECT_DIR / "run.json"
        assert run_json.exists()

        run_state = json.loads(run_json.read_text())
        assert run_state["status"] == "publish_complete"
        assert run_state["current_stage"] == "publish"
        assert run_state["completed_stages"] == EXPECTED_STAGES
        assert run_state["next_stage"] is None

        for stage in EXPECTED_STAGES:
            assert (PROJECT_DIR / f"checkpoint_{stage}.json").exists()
            assert (PROJECT_DIR / stage / "stage_request.json").exists()

        assert "publish_complete" in result.stdout or "PASS" in result.stdout.upper()
    finally:
        _clean_smoke_artifacts()
