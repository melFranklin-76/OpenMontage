from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_ROOT = REPO_ROOT / "creator-studio"
sys.path.insert(0, str(STUDIO_ROOT))

from studio.asset_materializer import materialize_assets


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_materialize_assets_writes_srt_subtitle_asset(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"

    _write_json(
        project_dir / "run.json",
        {
            "name": "subtitle-smoke",
            "pipeline": "animated-explainer",
            "platform": "youtube",
            "persona": "developer",
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
                    "end_seconds": 3,
                    "narration": "This is a local subtitle materialization test.",
                },
                {
                    "id": "section_02",
                    "scene_id": "scene_01",
                    "start_seconds": 3,
                    "end_seconds": 6,
                    "narration": "The generated SRT should contain script text.",
                },
            ]
        },
    )

    _write_json(
        project_dir / "scene_plan" / "scene_plan.json",
        {
            "scenes": [
                {
                    "id": "scene_01",
                    "title": "Subtitle materialization",
                }
            ]
        },
    )

    manifest = {
        "assets": [
            {
                "id": "subtitle_01",
                "type": "subtitle",
                "path": "assets/subtitles/subtitle_01.srt",
                "source_tool": "local_subtitle_placeholder",
                "scene_id": "scene_01",
            }
        ]
    }

    _write_json(project_dir / "assets" / "asset_manifest.json", manifest)

    materialize_assets(project_dir)

    subtitle_path = project_dir / "assets" / "subtitles" / "subtitle_01.srt"
    assert subtitle_path.exists()

    subtitle_text = subtitle_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:03,000" in subtitle_text
    assert "Section 1" in subtitle_text
    assert "Section 2" in subtitle_text

    for asset in manifest["assets"]:
        assert (project_dir / asset["path"]).exists()
