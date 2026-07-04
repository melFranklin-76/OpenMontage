from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_DIR = REPO_ROOT / "creator-studio"

sys.path.insert(0, str(STUDIO_DIR))
sys.path.insert(0, str(REPO_ROOT))

from studio.render_report_generator import generate_render_report


def _copy_fixture_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"

    for stage, filename in [
        ("proposal", "proposal_packet.json"),
        ("script", "script.json"),
        ("edit", "edit_decisions.json"),
    ]:
        source = REPO_ROOT / "tests" / "creator_studio" / "fixtures" / filename
        target = project_dir / stage / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    run_json = {
        "name": "Vector Databases",
        "topic": "How vector databases power retrieval augmented generation",
        "platform": "instagram",
        "render_runtime": "remotion",
    }
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "run.json").write_text(json.dumps(run_json, indent=2) + "\n", encoding="utf-8")

    return project_dir


def test_generate_render_report_writes_schema_valid_payload(tmp_path: Path) -> None:
    project_dir = _copy_fixture_project(tmp_path)

    output = generate_render_report(project_dir)

    assert output == project_dir / "compose" / "render_report.json"
    payload = json.loads(output.read_text(encoding="utf-8"))

    schema = json.loads(
        (REPO_ROOT / "schemas" / "artifacts" / "render_report.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(instance=payload, schema=schema)

    assert payload["version"] == "1.0"
    assert len(payload["outputs"]) == 2
    assert payload["outputs"][0]["platform_target"] == "instagram"
    assert payload["outputs"][0]["resolution"] == "1080x1920"
    assert payload["outputs"][1]["platform_target"] == "youtube"
    assert payload["outputs"][1]["resolution"] == "1920x1080"
    assert payload["outputs"][0]["duration_seconds"] == 60.0
    assert payload["render_grammar"] == "explainer-data"
    assert payload["metadata"]["render_runtime"] == "remotion"
    assert payload["metadata"]["source"] == "local_render_report_generator"
