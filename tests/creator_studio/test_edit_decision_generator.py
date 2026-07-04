from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_ROOT = REPO_ROOT / "creator-studio"
sys.path.insert(0, str(STUDIO_ROOT))

from studio.edit_decision_generator import generate_edit_decisions


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_generate_edit_decisions_writes_local_schema_shaped_artifact(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"

    _write_json(
        project_dir / "run.json",
        {
            "name": "vector-databases",
            "topic": "vector databases",
            "pipeline": "animated-explainer",
            "platform": "instagram",
            "render_runtime": "remotion",
        },
    )

    _write_json(
        project_dir / "proposal" / "proposal_packet.json",
        {
            "render_runtime": "remotion",
            "renderer_family": "explainer-data",
        },
    )

    _write_json(
        project_dir / "script" / "script.json",
        {
            "sections": [
                {
                    "id": "section_01",
                    "scene_id": "scene_01",
                    "start_seconds": 0,
                    "end_seconds": 4,
                    "title": "Open",
                },
                {
                    "id": "section_02",
                    "scene_id": "scene_02",
                    "start_seconds": 4,
                    "end_seconds": 9,
                    "title": "Explain",
                },
            ]
        },
    )

    _write_json(
        project_dir / "scene_plan" / "scene_plan.json",
        {
            "scenes": [
                {"id": "scene_01", "title": "Open"},
                {"id": "scene_02", "title": "Explain"},
            ]
        },
    )

    _write_json(
        project_dir / "assets" / "asset_manifest.json",
        {
            "assets": [
                {
                    "id": "img_01",
                    "type": "image",
                    "path": "assets/images/img_01.svg",
                },
                {
                    "id": "subtitle_01",
                    "type": "subtitle",
                    "path": "assets/subtitles/subtitle_01.srt",
                },
            ]
        },
    )

    output_path = generate_edit_decisions(project_dir)

    assert output_path == project_dir / "edit" / "edit_decisions.json"
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["version"] == "1.0"
    assert payload["render_runtime"] == "remotion"
    assert payload["renderer_family"] == "explainer-data"
    assert len(payload["cuts"]) == 2

    assert payload["cuts"][0]["id"] == "cut_01"
    assert payload["cuts"][0]["source"] == "img_01"
    assert payload["cuts"][0]["in_seconds"] == 0
    assert payload["cuts"][0]["out_seconds"] == 4

    assert payload["cuts"][1]["id"] == "cut_02"
    assert payload["cuts"][1]["source"] == "img_01"
    assert payload["cuts"][1]["in_seconds"] == 4
    assert payload["cuts"][1]["out_seconds"] == 9

    assert payload["subtitles"]["enabled"] is True
    assert payload["subtitles"]["source"] == "subtitle_01"
    assert payload["metadata"]["total_cuts"] == 2
    assert payload["metadata"]["source"] == "local_edit_decision_generator"
