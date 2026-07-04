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

from studio.publish_log_generator import generate_publish_log


def _copy_fixture_project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "project"

    source = REPO_ROOT / "tests" / "creator_studio" / "fixtures" / "render_report.json"
    target = project_dir / "compose" / "render_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)

    run_json = {
        "name": "Vector Databases",
        "topic": "vector_databases",
        "platform": "instagram",
    }
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "run.json").write_text(json.dumps(run_json, indent=2) + "\n", encoding="utf-8")

    return project_dir


def test_generate_publish_log_writes_schema_valid_payload(tmp_path: Path) -> None:
    project_dir = _copy_fixture_project(tmp_path)

    output = generate_publish_log(project_dir)

    assert output == project_dir / "publish" / "publish_log.json"
    payload = json.loads(output.read_text(encoding="utf-8"))

    schema = json.loads(
        (REPO_ROOT / "schemas" / "artifacts" / "publish_log.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(instance=payload, schema=schema)

    assert payload["version"] == "1.0"
    assert len(payload["entries"]) == 2
    assert payload["entries"][0]["platform"] == "instagram"
    assert payload["entries"][0]["status"] == "exported"
    assert payload["entries"][0]["export_path"] == "compose/output/vector_databases_instagram.mp4"
    assert payload["entries"][1]["platform"] == "youtube"
    assert payload["entries"][1]["status"] == "exported"
    assert payload["metadata"]["topic"] == "vector_databases"
    assert payload["metadata"]["total_entries"] == 2
    assert payload["metadata"]["source"] == "local_publish_log_generator"
