from __future__ import annotations

import json
from pathlib import Path

from studio.asset_materializer import materialize_assets


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_materialize_assets_writes_subtitle_srt_from_script_sections(tmp_path: Path) -> None:
    project_dir = tmp_path / "subtitle-materialization"

    _write_json(
        project_dir / "run.json",
        {
            "project_id": "subtitle-materialization",
            "topic": "Subtitle materialization",
        },
    )
    _write_json(
        project_dir / "script" / "script.json",
        {
            "version": "1.0",
            "title": "Subtitle materialization",
            "sections": [
                {
                    "id": "intro",
                    "label": "Intro",
                    "text": "Subtitle materialization turns script timing into a local SRT file.",
                    "start_seconds": 0,
                    "end_seconds": 3,
                },
                {
                    "id": "outro",
                    "label": "Outro",
                    "text": "Every manifest path should exist after materialization.",
                    "start_seconds": 3,
                    "end_seconds": 6.5,
                },
            ],
        },
    )
    _write_json(
        project_dir / "scene_plan" / "scene_plan.json",
        {
            "version": "1.0",
            "scenes": [
                {
                    "id": "scene_01",
                    "script_section_id": "intro",
                    "description": "Intro scene",
                    "start_seconds": 0,
                    "end_seconds": 3,
                }
            ],
        },
    )
    _write_json(
        project_dir / "assets" / "asset_manifest.json",
        {
            "version": "1.0",
            "assets": [
                {
                    "id": "subtitle_01",
                    "type": "subtitle",
                    "path": "assets/subtitles/subtitle_01.srt",
                    "source_tool": "local_subtitle_placeholder",
                    "scene_id": "scene_01",
                }
            ],
        },
    )

    materialized = materialize_assets(project_dir)

    subtitle_path = project_dir / "assets" / "subtitles" / "subtitle_01.srt"
    manifest = json.loads((project_dir / "assets" / "asset_manifest.json").read_text(encoding="utf-8"))

    assert subtitle_path in materialized
    assert subtitle_path.exists()
    subtitle_text = subtitle_path.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:03,000" in subtitle_text
    assert "Subtitle materialization turns script timing into a local SRT file." in subtitle_text
    assert all((project_dir / asset["path"]).exists() for asset in manifest["assets"])
