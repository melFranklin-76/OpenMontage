"""Materialize deterministic local preview assets for Creator Studio.

Milestone 5A creates lightweight files for every path declared in
``assets/asset_manifest.json``. These files are previews and stubs only: no
provider APIs, rendering, real image generation, real audio generation, or real
video generation are used.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


class AssetMaterializationError(RuntimeError):
    """Raised when preview asset materialization cannot satisfy the manifest."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _scene_by_id(scene_plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(scene.get("id")): scene
        for scene in scene_plan.get("scenes") or []
        if scene.get("id") is not None
    }


def _section_by_id(script: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get("id")): section
        for section in script.get("sections") or []
        if section.get("id") is not None
    }


def _asset_path(project_dir: Path, asset: dict[str, Any]) -> Path:
    raw_path = asset.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise AssetMaterializationError(f"Asset {asset.get('id')!r} is missing a non-empty path.")
    path = Path(raw_path)
    if path.is_absolute():
        raise AssetMaterializationError(f"Asset {asset.get('id')!r} path must be relative: {raw_path}")
    return project_dir / path


def _format_srt_timestamp(seconds: object) -> str:
    try:
        value = max(float(seconds), 0.0)
    except (TypeError, ValueError):
        value = 0.0
    milliseconds = int(round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _srt_from_script(script: dict[str, Any]) -> str:
    sections = script.get("sections") or []
    blocks: list[str] = []
    for index, section in enumerate(sections, start=1):
        start = _format_srt_timestamp(section.get("start_seconds"))
        end = _format_srt_timestamp(section.get("end_seconds"))
        text = str(section.get("text") or section.get("label") or f"Section {index}").strip()
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    if not blocks:
        blocks.append("1\n00:00:00,000 --> 00:00:05,000\nPreview subtitles unavailable.")
    return "\n\n".join(blocks) + "\n"


def _scene_card_svg(
    *,
    asset: dict[str, Any],
    scene: dict[str, Any] | None,
    script_section: dict[str, Any] | None,
    run_manifest: dict[str, Any],
) -> str:
    asset_id = html.escape(str(asset.get("id") or "asset"))
    asset_type = html.escape(str(asset.get("type") or "preview"))
    scene_id = html.escape(str(asset.get("scene_id") or "scene"))
    topic = html.escape(str(run_manifest.get("topic") or run_manifest.get("project_id") or "Creator Studio"))
    scene_title = html.escape(str((scene or {}).get("narrative_role") or (script_section or {}).get("label") or "Preview scene"))
    description = html.escape(
        str(asset.get("prompt") or (scene or {}).get("description") or (script_section or {}).get("text") or "Local preview asset")[:220]
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720" viewBox="0 0 1280 720" role="img" aria-label="Creator Studio preview card">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#111827"/>
      <stop offset="1" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#bg)"/>
  <rect x="64" y="64" width="1152" height="592" rx="36" fill="#ffffff" fill-opacity="0.92"/>
  <text x="104" y="135" font-family="Inter, Arial, sans-serif" font-size="30" fill="#2563eb" font-weight="700">Creator Studio Local Preview</text>
  <text x="104" y="205" font-family="Inter, Arial, sans-serif" font-size="54" fill="#111827" font-weight="800">{scene_id}</text>
  <text x="104" y="270" font-family="Inter, Arial, sans-serif" font-size="28" fill="#374151">{scene_title}</text>
  <foreignObject x="104" y="315" width="1030" height="190">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font-family: Inter, Arial, sans-serif; font-size: 30px; line-height: 1.25; color: #111827;">
      {description}
    </div>
  </foreignObject>
  <text x="104" y="575" font-family="Inter, Arial, sans-serif" font-size="24" fill="#4b5563">Asset: {asset_id} / {asset_type}</text>
  <text x="104" y="615" font-family="Inter, Arial, sans-serif" font-size="22" fill="#6b7280">Topic: {topic}</text>
</svg>
'''


def _stub_payload(
    *,
    asset: dict[str, Any],
    scene: dict[str, Any] | None,
    script_section: dict[str, Any] | None,
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "1.0",
        "stub_type": "creator_studio_local_preview_asset",
        "asset_id": asset.get("id"),
        "asset_type": asset.get("type"),
        "scene_id": asset.get("scene_id"),
        "path": asset.get("path"),
        "source_tool": asset.get("source_tool"),
        "prompt": asset.get("prompt"),
        "duration_seconds": asset.get("duration_seconds"),
        "project_id": run_manifest.get("project_id"),
        "topic": run_manifest.get("topic"),
        "scene_description": (scene or {}).get("description"),
        "script_text": (script_section or {}).get("text"),
        "note": "Deterministic local stub only; no provider call or media generation was performed.",
    }


def _materialize_asset(
    *,
    project_dir: Path,
    asset: dict[str, Any],
    script: dict[str, Any],
    scene_plan: dict[str, Any],
    run_manifest: dict[str, Any],
) -> Path:
    output_path = _asset_path(project_dir, asset)
    scenes = _scene_by_id(scene_plan)
    sections = _section_by_id(script)
    scene = scenes.get(str(asset.get("scene_id") or ""))
    script_section = sections.get(str((scene or {}).get("script_section_id") or ""))
    asset_type = str(asset.get("type") or "").lower()
    suffix = output_path.suffix.lower()

    if asset_type == "subtitle" or suffix == ".srt":
        _write_text(output_path, _srt_from_script(script))
    elif asset_type in {"image", "diagram"} or suffix == ".svg":
        _write_text(
            output_path,
            _scene_card_svg(
                asset=asset,
                scene=scene,
                script_section=script_section,
                run_manifest=run_manifest,
            ),
        )
    elif asset_type in {"audio", "narration", "music", "sfx", "video", "animation"}:
        payload = _stub_payload(
            asset=asset,
            scene=scene,
            script_section=script_section,
            run_manifest=run_manifest,
        )
        if suffix in {".json", ""}:
            _write_text(output_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        else:
            _write_bytes(output_path, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
    else:
        payload = _stub_payload(
            asset=asset,
            scene=scene,
            script_section=script_section,
            run_manifest=run_manifest,
        )
        _write_text(output_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    return output_path


def materialize_assets(project_dir: Path) -> list[Path]:
    """Create every asset file listed in the manifest and verify existence."""

    asset_manifest = _read_json(project_dir / "assets" / "asset_manifest.json")
    script = _read_json(project_dir / "script" / "script.json")
    scene_plan = _read_json(project_dir / "scene_plan" / "scene_plan.json")
    run_manifest = _read_json(project_dir / "run.json")

    assets = asset_manifest.get("assets") or []
    materialized = [
        _materialize_asset(
            project_dir=project_dir,
            asset=asset,
            script=script,
            scene_plan=scene_plan,
            run_manifest=run_manifest,
        )
        for asset in assets
    ]

    missing = [str(_asset_path(project_dir, asset).relative_to(project_dir)) for asset in assets if not _asset_path(project_dir, asset).exists()]
    if missing:
        raise AssetMaterializationError(
            "Asset materialization failed; manifest paths missing after materialization: "
            + ", ".join(missing)
        )

    return materialized
