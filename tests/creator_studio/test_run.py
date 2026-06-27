from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import run as studio_run


@dataclass(frozen=True)
class FakeStage:
    name: str

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


@dataclass(frozen=True)
class FakePlan:
    status: str
    project_id: str
    required_tools: tuple[str, ...]
    available_tools: tuple[str, ...]
    optional_warnings: tuple[str, ...]
    render_engines: tuple[str, ...]
    recommendation: str | None
    estimated_stages: int
    ready_to_execute: bool
    capability_summary: tuple[dict[str, int | str], ...]
    execution_plan: tuple[str, ...]
    missing_tools: tuple[str, ...]
    fallback_tools: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]
    composition_runtimes: dict[str, bool]
    next_stage: str | None


def test_main_prints_discovery_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    personas_dir = tmp_path / "personas"
    inbox_dir = tmp_path / "inbox"
    projects_dir = tmp_path / "projects"
    logs_dir = tmp_path / "logs"

    for path in (personas_dir, inbox_dir, projects_dir, logs_dir):
        path.mkdir(parents=True, exist_ok=True)

    persona_path = personas_dir / "mel.yaml"
    persona_path.write_text(
        "\n".join(
            [
                "name: Mel",
                "voice: warm",
                "platforms:",
                "  - instagram",
                "default_pipeline: talking-head",
                "default_platform: instagram",
                "branding:",
                "  handle: '@mel'",
                "  style: clean-professional",
            ]
        ),
        encoding="utf-8",
    )

    (inbox_dir / "video1.mp4").write_bytes(b"video")
    (inbox_dir / "video2.mp4").write_bytes(b"video")
    (inbox_dir / "photo1.jpg").write_bytes(b"image")
    (inbox_dir / "photo2.jpg").write_bytes(b"image")
    (inbox_dir / "photo3.jpg").write_bytes(b"image")
    (inbox_dir / "photo4.jpg").write_bytes(b"image")
    (inbox_dir / "voice.wav").write_bytes(b"audio")

    monkeypatch.setattr(studio_run, "PERSONAS_DIR", personas_dir)
    monkeypatch.setattr(studio_run, "INBOX_DIR", inbox_dir)
    monkeypatch.setattr(studio_run, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(studio_run, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(
        studio_run,
        "Engine",
        lambda: type(
            "FakeEngine",
            (),
            {
                "preflight": lambda self, **kwargs: FakePlan(
                    status="passed",
                    project_id="demo-project",
                    required_tools=("transcriber",),
                    available_tools=("transcriber",),
                    optional_warnings=(),
                    render_engines=("Remotion", "HyperFrames"),
                    recommendation="Remotion",
                    estimated_stages=3,
                    ready_to_execute=True,
                    capability_summary=(
                        {"capability": "video_generation", "configured": 3, "total": 5},
                        {"capability": "image_generation", "configured": 2, "total": 4},
                    ),
                    execution_plan=("Idea", "Script", "Compose"),
                    missing_tools=(),
                    fallback_tools={},
                    warnings=(),
                    composition_runtimes={"remotion": True, "hyperframes": True, "ffmpeg": True},
                    next_stage="idea",
                ),
                "run": lambda self, **kwargs: {"approved": True, "execution_started": False},
            },
        )(),
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--persona", str(persona_path)])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "MEL CREATOR STUDIO" in output
    assert "Pipeline: Talking Head" in output
    assert "Platform: Instagram" in output
    assert "2 videos" in output
    assert "4 images" in output
    assert "1 audio" in output
    assert "EXECUTION PLAN" in output
    assert "[x] Idea" in output
    assert "Capability Status: PASSED" in output
    assert "video_generation: 3 available of 5" in output
    assert "Recommendation: Remotion" in output
    assert "Waiting for approval..." in output


def _write_persona(personas_dir: Path) -> Path:
    persona_path = personas_dir / "mel.yaml"
    persona_path.write_text(
        "\n".join(
            [
                "name: Mel",
                "voice: warm",
                "platforms:",
                "  - instagram",
                "default_pipeline: talking-head",
                "default_platform: instagram",
                "branding:",
                "  handle: '@mel'",
                "  style: clean-professional",
            ]
        ),
        encoding="utf-8",
    )
    return persona_path


def _patch_dirs(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    dirs = {
        "personas": tmp_path / "personas",
        "inbox": tmp_path / "inbox",
        "projects": tmp_path / "projects",
        "logs": tmp_path / "logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(studio_run, "PERSONAS_DIR", dirs["personas"])
    monkeypatch.setattr(studio_run, "INBOX_DIR", dirs["inbox"])
    monkeypatch.setattr(studio_run, "PROJECTS_DIR", dirs["projects"])
    monkeypatch.setattr(studio_run, "LOGS_DIR", dirs["logs"])
    return dirs


def _fake_engine(run_result: dict | None = None, complete_result: dict | None = None):
    return lambda: type(
        "FakeEngine",
        (),
        {
            "preflight": lambda self, **kwargs: FakePlan(
                status="passed",
                project_id="demo-project",
                required_tools=(),
                available_tools=(),
                optional_warnings=(),
                render_engines=("Remotion",),
                recommendation="Remotion",
                estimated_stages=2,
                ready_to_execute=True,
                capability_summary=(),
                execution_plan=("Research", "Proposal"),
                missing_tools=(),
                fallback_tools={},
                warnings=(),
                composition_runtimes={"remotion": True},
                next_stage="research",
            ),
            "run": lambda self, **kwargs: run_result or {},
            "complete_research": lambda self, *args, **kwargs: complete_result or {},
        },
    )()


def test_main_approve_prints_research_handoff(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    persona_path = _write_persona(dirs["personas"])
    (dirs["inbox"] / "video1.mp4").write_bytes(b"video")

    handoff = {
        "status": "research_pending",
        "director_skill_path": "skills/pipelines/explainer/research-director.md",
        "schema_path": "schemas/artifacts/research_brief.schema.json",
        "research_brief_path": "research/research_brief.json",
    }
    monkeypatch.setattr(studio_run, "Engine", _fake_engine(run_result=handoff))
    monkeypatch.setattr(
        sys,
        "argv",
        ["run.py", "--persona", str(persona_path), "--pipeline", "animated-explainer",
         "--topic", "Vector databases", "--approve"],
    )

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Research stage prepared." in output
    assert "research/stage_request.json" in output
    assert "Read skills/pipelines/explainer/research-director.md" in output
    assert "Stopping after Research handoff by design." in output


def test_main_complete_research_prints_success(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    _write_persona(dirs["personas"])
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    success = {
        "status": "research_complete",
        "checkpoint_path": str(project_dir / "checkpoint_research.json"),
        "artifacts_written": ["research/citations.json", "research/audience_questions.json"],
        "next_stage": "proposal",
        "elapsed_seconds": 0.01,
    }
    monkeypatch.setattr(studio_run, "Engine", _fake_engine(complete_result=success))
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-research"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Research stage complete." in output
    assert "Next stage: Proposal" in output
    assert "Stopping after Research by design." in output


def test_main_complete_research_resume(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    resume = {"status": "research_already_complete", "next_stage": "proposal"}
    monkeypatch.setattr(studio_run, "Engine", _fake_engine(complete_result=resume))
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-research"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Research already completed." in output
    assert "Next stage: Proposal" in output


# ---------------------------------------------------------------------------
# Proposal CLI tests
# ---------------------------------------------------------------------------

def _fake_engine_with_proposal(
    run_result: dict | None = None,
    complete_research_result: dict | None = None,
    run_proposal_result: dict | None = None,
    complete_proposal_result: dict | None = None,
):
    return lambda: type(
        "FakeEngine",
        (),
        {
            "preflight": lambda self, **kwargs: FakePlan(
                status="passed",
                project_id="demo-project",
                required_tools=(),
                available_tools=(),
                optional_warnings=(),
                render_engines=("Remotion",),
                recommendation="Remotion",
                estimated_stages=2,
                ready_to_execute=True,
                capability_summary=(),
                execution_plan=("Research", "Proposal"),
                missing_tools=(),
                fallback_tools={},
                warnings=(),
                composition_runtimes={"remotion": True},
                next_stage="research",
            ),
            "run": lambda self, **kwargs: run_result or {},
            "complete_research": lambda self, *args, **kwargs: complete_research_result or {},
            "run_proposal": lambda self, *args, **kwargs: run_proposal_result or {},
            "complete_proposal": lambda self, *args, **kwargs: complete_proposal_result or {},
        },
    )()


def test_main_run_proposal_prints_handoff(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    handoff = {
        "status": "proposal_pending",
        "director_skill_path": "skills/pipelines/explainer/proposal-director.md",
        "schema_path": "schemas/artifacts/proposal_packet.schema.json",
        "proposal_packet_path": "proposal/proposal_packet.json",
    }
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_proposal(run_proposal_result=handoff)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--run-proposal"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Proposal stage prepared." in output
    assert "proposal/stage_request.json" in output
    assert "Read skills/pipelines/explainer/proposal-director.md" in output
    assert "Stopping after Proposal handoff by design." in output


def test_main_complete_proposal_prints_success(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    success = {
        "status": "proposal_complete",
        "checkpoint_path": str(project_dir / "checkpoint_proposal.json"),
        "next_stage": "script",
        "elapsed_seconds": 0.02,
    }
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_proposal(complete_proposal_result=success)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-proposal"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Proposal stage complete." in output
    assert "Next stage: Script" in output
    assert "Stopping after Proposal by design." in output


def test_main_complete_proposal_resume(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    resume = {"status": "proposal_already_complete", "next_stage": "script"}
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_proposal(complete_proposal_result=resume)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-proposal"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Proposal already completed." in output
    assert "Next stage: Script" in output


# ---------------------------------------------------------------------------
# Script CLI tests
# ---------------------------------------------------------------------------

def _fake_engine_with_script(
    run_script_result: dict | None = None,
    complete_script_result: dict | None = None,
):
    return lambda: type(
        "FakeEngine",
        (),
        {
            "preflight": lambda self, **kwargs: FakePlan(
                status="passed",
                project_id="demo-project",
                required_tools=(),
                available_tools=(),
                optional_warnings=(),
                render_engines=("Remotion",),
                recommendation="Remotion",
                estimated_stages=3,
                ready_to_execute=True,
                capability_summary=(),
                execution_plan=("Research", "Proposal", "Script"),
                missing_tools=(),
                fallback_tools={},
                warnings=(),
                composition_runtimes={"remotion": True},
                next_stage="research",
            ),
            "run": lambda self, **kwargs: {},
            "complete_research": lambda self, *args, **kwargs: {},
            "run_proposal": lambda self, *args, **kwargs: {},
            "complete_proposal": lambda self, *args, **kwargs: {},
            "run_script": lambda self, *args, **kwargs: run_script_result or {},
            "complete_script": lambda self, *args, **kwargs: complete_script_result or {},
        },
    )()


def test_main_run_script_prints_handoff(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    handoff = {
        "status": "script_pending",
        "director_skill_path": "skills/pipelines/explainer/script-director.md",
        "schema_path": "schemas/artifacts/script.schema.json",
        "script_path": "script/script.json",
    }
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_script(run_script_result=handoff)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--run-script"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Script stage prepared." in output
    assert "script/stage_request.json" in output
    assert "Read skills/pipelines/explainer/script-director.md" in output
    assert "Produce script/script.json" in output
    assert "Validate against schemas/artifacts/script.schema.json" in output
    assert "Stopping after Script handoff by design." in output


def test_main_complete_script_prints_success(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    success = {
        "status": "script_complete",
        "checkpoint_path": str(project_dir / "checkpoint_script.json"),
        "next_stage": "scene_plan",
        "elapsed_seconds": 0.03,
    }
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_script(complete_script_result=success)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-script"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Script stage complete." in output
    assert "Next stage: Scene Plan" in output
    assert "Stopping after Script by design." in output


def test_main_complete_script_resume(tmp_path: Path, monkeypatch, capsys) -> None:
    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    resume = {"status": "script_already_complete", "next_stage": "scene_plan"}
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_script(complete_script_result=resume)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--complete-script"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Script already completed." in output
    assert "Next stage: Scene Plan" in output


def test_complete_script_routing_takes_priority_over_run_script(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """--complete-script must be dispatched even when --run-script is also present."""

    dirs = _patch_dirs(monkeypatch, tmp_path)
    project_dir = dirs["projects"] / "demo"
    project_dir.mkdir()
    (project_dir / "run.json").write_text(
        json.dumps({"pipeline": "animated-explainer"}), encoding="utf-8"
    )

    success = {
        "status": "script_complete",
        "checkpoint_path": str(project_dir / "checkpoint_script.json"),
        "next_stage": "scene_plan",
        "elapsed_seconds": 0.01,
    }
    monkeypatch.setattr(
        studio_run, "Engine", _fake_engine_with_script(complete_script_result=success)
    )
    monkeypatch.setattr(sys, "argv", ["run.py", "--run-script", "--complete-script"])

    exit_code = studio_run.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Script stage complete." in output

