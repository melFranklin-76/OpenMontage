"""Reel script generation for What's the LGBT, Fish?

Turns a research handoff packet (from research_handoff) into a structured
short-form script draft: hook, story, why-it-matters, CTA — plus caption,
hashtags, and source attribution. Deterministic and story-grounded; the
draft is the starting point the agent refines during the script stage.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .daily_digest import build_daily_candidates
from .intake import fetch_live_stories
from .research_handoff import build_research_handoff, select_candidate

SHOW_NAME = "What's the LGBT, Fish?"
TARGET_DURATION_SECONDS = 45

BASE_HASHTAGS = ["#lgbtq", "#lgbtnews", "#queer", "#whatsthelgbtfish"]

LANE_HASHTAGS = {
    "gay": ["#gay", "#gaynews", "#pride"],
    "lesbian": ["#lesbian", "#wlw", "#sapphic"],
    "bisexual": ["#bisexual", "#bivisibility", "#bipride"],
    "Black trans": ["#blacktrans", "#blacktranslivesmatter", "#transrights"],
}

LANE_WHY_LINES = {
    "gay": (
        "Because stories like this shape what everyday life looks like for gay "
        "folks everywhere, and we deserve to hear it straight — well, you know "
        "what I mean."
    ),
    "lesbian": (
        "Because lesbian stories deserve the whole spotlight... FISH... not a "
        "footnote at the bottom of somebody else's article."
    ),
    "bisexual": (
        "Because bi stories almost never make the front page — and this one "
        "earned its spot, so we're giving it its flowers."
    ),
    "Black trans": (
        "Because Black trans stories lead this show, period — they lead the "
        "movement, and we follow the leaders here."
    ),
}


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def build_reel_script(handoff: dict) -> dict:
    """Build a Reel script draft from a research handoff packet."""
    lane = handoff.get("lane", "")
    story = handoff.get("story", {})
    title = story.get("title") or handoff.get("topic", "")
    summary = story.get("summary", "")
    source = story.get("source", "")
    url = story.get("url", "")

    story_line = _truncate_words(summary or title, 40)
    why_line = LANE_WHY_LINES.get(lane, "This story matters to our community.")

    sections = [
        {
            "id": "hook",
            "narration": f"What's the LGBT, Fish? Today: {title}.",
            "duration_seconds": 6,
            "visual_hint": "Show branding, bold headline card with story title",
        },
        {
            "id": "story",
            "narration": story_line,
            "duration_seconds": 19,
            "visual_hint": "Story imagery, key-phrase text overlays",
        },
        {
            "id": "why_it_matters",
            "narration": why_line,
            "duration_seconds": 12,
            "visual_hint": "Lane-colored emphasis card, community imagery",
        },
        {
            "id": "cta",
            "narration": (
                f"Full story from {source} — link in bio... GHOULS. "
                "Follow for the LGBT news that actually matters. Okay bye!"
            ),
            "duration_seconds": 8,
            "visual_hint": "Source attribution card, follow prompt",
        },
    ]

    hashtags = BASE_HASHTAGS + LANE_HASHTAGS.get(lane, [])

    return {
        "show": SHOW_NAME,
        "script_date": date.today().isoformat(),
        "format": "reel",
        "target_duration_seconds": TARGET_DURATION_SECONDS,
        "topic": title,
        "lane": lane,
        "sections": sections,
        "caption": f"{title} — the story and why it matters. {' '.join(hashtags)}",
        "hashtags": hashtags,
        "source_attribution": {"name": source, "url": url},
        "digest_rank": handoff.get("digest_rank"),
        "relevance_score": handoff.get("relevance_score"),
        "metadata": {
            "generated_by": "creator-studio/studio/fish/reel_script.py",
            "generation_mode": "deterministic_local",
            "handoff_date": handoff.get("handoff_date", ""),
            "digest_date": handoff.get("digest_date", ""),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--handoff", help="Path to a research handoff JSON file")
    source.add_argument(
        "--live",
        action="store_true",
        help="Run the full chain: fetch feeds, rank, take top story, write script",
    )
    parser.add_argument("--rank", type=int, default=1, help="1-indexed rank in --live mode")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.live:
        digest = build_daily_candidates(fetch_live_stories())
        candidate = select_candidate(digest, rank=args.rank)
        handoff = build_research_handoff(candidate, digest.get("date", ""), rank=args.rank)
    else:
        handoff = json.loads(Path(args.handoff).read_text())

    script = build_reel_script(handoff)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(script, indent=2) + "\n")

    total = sum(s["duration_seconds"] for s in script["sections"])
    print(f"Wrote reel script for [{script['lane']}] {script['topic']}")
    print(f"  -> {output_path} ({total}s across {len(script['sections'])} sections)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
