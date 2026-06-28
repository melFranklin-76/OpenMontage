"""Shared test setup and helpers for Creator Studio.

This module is on sys.path (see below), so test files can import shared
utilities directly::

    from conftest import FIXTURES, make_project, passed_plan, copy_fixture

Pytest fixtures defined here are also auto-available to every test in this
directory without any explicit import.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CREATOR_STUDIO_ROOT = PROJECT_ROOT / "creator-studio"

# Keep conftest itself importable so test modules can pull in plain helpers.
_THIS_DIR = Path(__file__).resolve().parent

for _p in (str(CREATOR_STUDIO_ROOT), str(_THIS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Deferred imports — CREATOR_STUDIO_ROOT must be on sys.path first.
from studio.engine import PreflightResult          # noqa: E402
from studio.pipeline import PipelineDefinition, load_manifest  # noqa: E402
from studio.project import initialize_run_manifest  # noqa: E402

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FIXTURES: Path = _THIS_DIR / "fixtures"
"""Absolute path to the tests/creator_studio/fixtures/ directory."""

_PIPELINE_NAME = "animated-explainer"
_PERSONA = "Mel"
_PLATFORM = "instagram"


# ---------------------------------------------------------------------------
# Shared plain helper functions
# (callable from helper chains inside test files, not just test functions)
# ---------------------------------------------------------------------------

def explainer_pipeline() -> PipelineDefinition:
    """Load the real animated-explainer manifest (cached by load_manifest)."""
    return load_manifest(_PIPELINE_NAME)


def passed_plan(project_id: str = "demo") -> PreflightResult:
    """Return a fully-passing PreflightResult for the animated-explainer pipeline."""
    return PreflightResult(
        status="passed",
        pipeline=_PIPELINE_NAME,
        project_id=project_id,
        required_tools=(),
        available_tools=(),
        missing_tools=(),
        optional_warnings=(),
        render_engines=("Remotion",),
        recommendation="Remotion",
        execution_plan=("Research", "Proposal"),
        estimated_stages=2,
        ready_to_execute=True,
        fallback_tools={},
        composition_runtimes={"remotion": True},
        warnings=(),
        capability_summary=(),
        completed_stages=(),
        next_stage="research",
        latest_checkpoint_stage=None,
    )


def make_project(tmp_path: Path, project_id: str = "demo") -> Path:
    """Create and initialise a temp project directory for testing."""
    project_dir = tmp_path / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    initialize_run_manifest(project_dir, project_id, _PERSONA, _PIPELINE_NAME, _PLATFORM)
    return project_dir


def copy_fixture(name: str, destination: Path) -> None:
    """Copy a fixture JSON file to *destination*, creating parent dirs as needed."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        (FIXTURES / name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Pytest fixtures wrapping the plain helpers above
# (available for injection into test functions by pytest)
# ---------------------------------------------------------------------------

@pytest.fixture
def explainer_pipeline_fixture() -> PipelineDefinition:
    return explainer_pipeline()


@pytest.fixture
def passed_plan_fixture() -> PreflightResult:
    return passed_plan()

