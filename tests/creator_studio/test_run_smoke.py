from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_smoke


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SMOKE = REPO_ROOT / "creator-studio" / "run_smoke.py"
PROJECT_NAME = "pytest-smoke-command"
EXPECTED_STAGES = list(run_smoke.ALL_STAGES)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def smoke_fs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Redirect run_smoke paths into a temp Creator Studio workspace."""

    studio_root = tmp_path / "creator-studio"
    projects_dir = studio_root / "projects"
    inbox_dir = studio_root / "inbox"
    logs_dir = studio_root / "logs"
    demo_media = inbox_dir / "demo.mp4"
    fixtures_dir = tmp_path / "fixtures"
    run_py = studio_root / "run.py"

    for path in (projects_dir, inbox_dir, logs_dir, fixtures_dir):
        path.mkdir(parents=True, exist_ok=True)
    run_py.write_text("# stub run.py path for smoke tests\n", encoding="utf-8")

    monkeypatch.setattr(run_smoke, "STUDIO_ROOT", studio_root)
    monkeypatch.setattr(run_smoke, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(run_smoke, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(run_smoke, "DEMO_MEDIA", demo_media)
    monkeypatch.setattr(run_smoke, "FIXTURES_DIR", fixtures_dir)
    monkeypatch.setattr(run_smoke, "RUN_PY", run_py)

    return SimpleNamespace(
        studio_root=studio_root,
        projects_dir=projects_dir,
        inbox_dir=inbox_dir,
        logs_dir=logs_dir,
        demo_media=demo_media,
        fixtures_dir=fixtures_dir,
        run_py=run_py,
        project_dir=projects_dir / PROJECT_NAME,
    )


def _install_generator_stubs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace local generators with file-writing stubs, preventing side effects."""

    calls: list[str] = []

    def generator(stage: str, fixture: str):
        def _write(project_dir: Path) -> Path:
            calls.append(stage)
            path = project_dir / stage / fixture
            _write_json(path, {"stage": stage})
            return path

        return _write

    monkeypatch.setattr(
        run_smoke,
        "generate_research_brief",
        generator("research", "research_brief.json"),
    )
    monkeypatch.setattr(
        run_smoke,
        "generate_proposal_packet",
        generator("proposal", "proposal_packet.json"),
    )
    monkeypatch.setattr(run_smoke, "generate_script", generator("script", "script.json"))
    monkeypatch.setattr(
        run_smoke,
        "generate_scene_plan",
        generator("scene_plan", "scene_plan.json"),
    )
    monkeypatch.setattr(
        run_smoke,
        "generate_asset_manifest",
        generator("assets", "asset_manifest.json"),
    )
    monkeypatch.setattr(
        run_smoke,
        "generate_edit_decisions",
        generator("edit", "edit_decisions.json"),
    )
    monkeypatch.setattr(
        run_smoke,
        "generate_render_report",
        generator("compose", "render_report.json"),
    )
    monkeypatch.setattr(
        run_smoke,
        "generate_publish_log",
        generator("publish", "publish_log.json"),
    )

    def materialize_assets(project_dir: Path) -> list[Path]:
        calls.append("materialize_assets")
        asset = project_dir / "assets" / "preview.txt"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_text("preview\n", encoding="utf-8")
        return [asset]

    monkeypatch.setattr(run_smoke, "materialize_assets", materialize_assets)
    return calls


def _install_cli_stub(
    monkeypatch: pytest.MonkeyPatch,
    fs: SimpleNamespace,
    *,
    fail_on: str | None = None,
) -> list[tuple[str, ...]]:
    """Simulate run.py stage state transitions without invoking the real CLI."""

    calls: list[tuple[str, ...]] = []
    completed: list[str] = []

    def update_state(stage: str, status: str, next_stage: str | None) -> None:
        _write_json(
            fs.project_dir / "run.json",
            {
                "status": status,
                "current_stage": stage,
                "completed_stages": completed,
                "next_stage": next_stage,
            },
        )

    def run_cli(*flags: str) -> None:
        calls.append(flags)
        label = " ".join(flags)
        if fail_on and fail_on in flags:
            raise run_smoke.SmokeError(f"CLI step failed: {label}")

        if "--approve" in flags:
            fs.project_dir.mkdir(parents=True, exist_ok=True)
            (fs.project_dir / "research").mkdir(parents=True, exist_ok=True)
            _write_json(fs.project_dir / "research" / "stage_request.json", {"stage": "research"})
            update_state("research", "research_in_progress", "research")
            return

        stage_flag = next(flag for flag in flags if flag.startswith("--run-") or flag.startswith("--complete-"))
        is_complete = stage_flag.startswith("--complete-")
        stage = stage_flag.removeprefix("--run-").removeprefix("--complete-").replace("-", "_")

        if is_complete:
            if stage not in completed:
                completed.append(stage)
            next_stage = None
            status = f"{stage}_complete"
            if stage != "publish":
                current_index = EXPECTED_STAGES.index(stage)
                next_stage = EXPECTED_STAGES[current_index + 1]
            _write_json(fs.project_dir / f"checkpoint_{stage}.json", {"stage": stage})
            update_state(stage, status, next_stage)
            return

        stage_dir = fs.project_dir / stage
        stage_dir.mkdir(parents=True, exist_ok=True)
        _write_json(stage_dir / "stage_request.json", {"stage": stage})
        update_state(stage, f"{stage}_in_progress", stage)

    monkeypatch.setattr(run_smoke, "_run_cli", run_cli)
    return calls


def test_parse_args_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_smoke.py"])

    args = run_smoke.parse_args()

    assert args == Namespace(
        pipeline="animated-explainer",
        name="vector-databases",
        topic="How vector databases power retrieval augmented generation",
        keep=False,
        force_clean=True,
    )


def test_parse_args_custom_values_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_smoke.py",
            "--pipeline",
            "animated-explainer",
            "--name",
            "custom-smoke-project",
            "--topic",
            "custom topic",
            "--keep-project",
            "--force-clean",
        ],
    )

    args = run_smoke.parse_args()

    assert args.pipeline == "animated-explainer"
    assert args.name == "custom-smoke-project"
    assert args.topic == "custom topic"
    assert args.keep is True
    assert args.force_clean is True


def test_parse_args_no_force_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_smoke.py", "--no-force-clean"])

    args = run_smoke.parse_args()

    assert args.force_clean is False


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
    assert "--keep-project" in result.stdout
    assert "--force-clean" in result.stdout
    assert "--no-force-clean" in result.stdout


def test_prepare_inputs_force_clean_removes_existing_project(
    smoke_fs: SimpleNamespace,
) -> None:
    stale_file = smoke_fs.project_dir / "old.txt"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale\n", encoding="utf-8")

    run_smoke._prepare_inputs(PROJECT_NAME, force_clean=True)

    assert not stale_file.exists()
    assert smoke_fs.project_dir.parent.exists()
    assert smoke_fs.demo_media.exists()


def test_prepare_inputs_without_force_clean_refuses_existing_project(
    smoke_fs: SimpleNamespace,
) -> None:
    smoke_fs.project_dir.mkdir(parents=True)

    with pytest.raises(run_smoke.SmokeError, match="already exists"):
        run_smoke._prepare_inputs(PROJECT_NAME, force_clean=False)


def test_run_smoke_success_path_cleans_up_by_default(
    smoke_fs: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generator_calls = _install_generator_stubs(monkeypatch)
    cli_calls = _install_cli_stub(monkeypatch, smoke_fs)

    result = run_smoke.run_smoke(
        pipeline="animated-explainer",
        name=PROJECT_NAME,
        topic="custom topic",
        keep=False,
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "SMOKE PASSED" in output
    assert "publish_complete" in output
    assert not smoke_fs.project_dir.exists()
    assert not smoke_fs.demo_media.exists()
    assert ("--approve", "--name", PROJECT_NAME, "--topic", "custom topic", "--pipeline", "animated-explainer") in cli_calls
    assert generator_calls == [
        "research",
        "proposal",
        "script",
        "scene_plan",
        "assets",
        "materialize_assets",
        "edit",
        "compose",
        "publish",
    ]


def test_run_smoke_keep_project_preserves_verified_output(
    smoke_fs: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_generator_stubs(monkeypatch)
    _install_cli_stub(monkeypatch, smoke_fs)

    result = run_smoke.run_smoke(
        pipeline="animated-explainer",
        name=PROJECT_NAME,
        topic="custom topic",
        keep=True,
    )

    assert result == 0
    assert smoke_fs.project_dir.exists()
    assert smoke_fs.demo_media.exists()

    run_state = _read_json(smoke_fs.project_dir / "run.json")
    assert run_state["status"] == "publish_complete"
    assert run_state["current_stage"] == "publish"
    assert run_state["completed_stages"] == EXPECTED_STAGES
    assert run_state["next_stage"] is None

    for stage in EXPECTED_STAGES:
        assert (smoke_fs.project_dir / f"checkpoint_{stage}.json").exists()
        assert (smoke_fs.project_dir / stage / "stage_request.json").exists()


def test_run_smoke_force_clean_replaces_stale_project(
    smoke_fs: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_file = smoke_fs.project_dir / "old.txt"
    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("stale\n", encoding="utf-8")
    _install_generator_stubs(monkeypatch)
    _install_cli_stub(monkeypatch, smoke_fs)

    run_smoke.run_smoke(
        pipeline="animated-explainer",
        name=PROJECT_NAME,
        topic="custom topic",
        keep=True,
        force_clean=True,
    )

    assert not stale_file.exists()
    assert (smoke_fs.project_dir / "run.json").exists()


def test_run_smoke_without_force_clean_fails_before_overwrite(
    smoke_fs: SimpleNamespace,
) -> None:
    smoke_fs.project_dir.mkdir(parents=True)

    with pytest.raises(run_smoke.SmokeError, match="Re-run with --force-clean"):
        run_smoke.run_smoke(
            pipeline="animated-explainer",
            name=PROJECT_NAME,
            topic="custom topic",
            keep=True,
            force_clean=False,
        )


def test_run_smoke_failure_path_reports_useful_message(
    smoke_fs: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_generator_stubs(monkeypatch)
    _install_cli_stub(monkeypatch, smoke_fs, fail_on="--complete-research")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_smoke.py",
            "--pipeline",
            "animated-explainer",
            "--name",
            PROJECT_NAME,
            "--topic",
            "custom topic",
        ],
    )

    result = run_smoke.main()

    captured = capsys.readouterr()
    assert result == 1
    assert "SMOKE FAILED" in captured.err
    assert "CLI step failed: --complete-research" in captured.err
