"""Sub-artifact projection for Creator Studio stage outputs.

When a stage produces a canonical artifact (e.g. research_brief), this module
derives useful companion files from the validated data without fabricating
anything that isn't present in the source. Each projector is keyed to the
artifact name it handles; unknown artifacts return an empty list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Research brief projector
# ---------------------------------------------------------------------------

def _project_research_brief(brief: dict[str, Any], out_dir: Path) -> list[str]:
    """Derive companion files from a validated research_brief.

    Only projects keys that actually exist in the brief; never fabricates
    optional sections that the agent omitted.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    prefix = out_dir.name  # e.g. "research"

    def _dump(filename: str, data: Any) -> None:
        (out_dir / filename).write_text(json.dumps(data, indent=2), encoding="utf-8")
        written.append(f"{prefix}/{filename}")

    _dump("citations.json", brief["sources"])
    _dump("audience_questions.json", brief["audience_insights"]["common_questions"])

    trending = brief.get("trending")
    if trending:
        (out_dir / "trend_notes.md").write_text(
            _render_trend_notes(trending), encoding="utf-8"
        )
        written.append(f"{prefix}/trend_notes.md")

    visual_references = brief.get("visual_references")
    if visual_references:
        _dump("visual_references.json", visual_references)

    return written


def _render_trend_notes(trending: dict[str, Any]) -> str:
    """Render a Markdown summary of the trending block (real data only)."""

    lines: list[str] = ["# Trend Notes", ""]
    for item in trending.get("recent_developments") or []:
        if "## Recent Developments" not in lines:
            lines.append("## Recent Developments")
        headline = item.get("headline", "")
        date = item.get("date", "")
        suffix = f" ({date})" if date else ""
        relevance = item.get("relevance", "")
        entry = f"- {headline}{suffix} — {relevance}".rstrip(" —")
        if item.get("url"):
            entry += f" [{item['url']}]"
        lines.append(entry)

    discussions = trending.get("active_discussions") or []
    if discussions:
        lines.extend(["", "## Active Discussions"])
        for item in discussions:
            platform = item.get("platform", "")
            topic_or_url = item.get("topic_or_url", "")
            sentiment = item.get("sentiment", "")
            lines.append(f"- {platform}: {topic_or_url} — {sentiment}".rstrip(" —"))

    window = trending.get("timeliness_window")
    if window:
        lines.extend(["", f"Timeliness window: {window}"])

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Projector registry
# ---------------------------------------------------------------------------

_ProjectorFn = Callable[[dict[str, Any], Path], list[str]]

PROJECTORS: dict[str, _ProjectorFn] = {
    "research_brief": _project_research_brief,
}


def project_sub_artifacts(
    artifact_name: str,
    data: dict[str, Any],
    out_dir: Path,
) -> list[str]:
    """Invoke the registered projector for *artifact_name*, if one exists.

    Returns the list of paths written (relative to the project root).
    Returns an empty list for unknown artifact names — never raises.
    """

    projector = PROJECTORS.get(artifact_name)
    if projector is None:
        return []
    return projector(data, out_dir)
