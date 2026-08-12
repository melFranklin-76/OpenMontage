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
    "trans": ["#trans", "#translivesmatter", "#transrights"],
}

# Legacy lines are retained so `host_take` can recognize and upgrade scripts
# generated before story-specific context slots were introduced.
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
    "trans": (
        "Because when trans people make the news, the coverage is usually "
        "about them and almost never with them. Not here."
    ),
}

# These angles provide useful context without pretending to be Mel's personal
# opinion. They are selected from the story itself, not its LGBTQ lane, so ten
# stories in one lane do not end with the same paragraph.
EDITORIAL_ANGLES = {
    "policy": (
        "The headline is one decision. The real test is what changes in daily "
        "life, who has to follow it, and what happens next."
    ),
    "safety": (
        "This deserves more than a statistic. Keep the people affected, the "
        "response they receive, and the help that follows at the center."
    ),
    "culture": (
        "Representation matters when it changes who gets seen, hired, funded, "
        "or remembered — not only who trends for a day."
    ),
    "community": (
        "The important part is the work behind the headline: who organized it, "
        "who benefits, and whether the support lasts after attention moves on."
    ),
    "default": (
        "The headline tells us what happened. What matters next is the practical "
        "effect on the people at the center of the story."
    ),
}

_ANGLE_TERMS = {
    "policy": {
        "ban", "bill", "court", "election", "executive order", "law", "legal",
        "policy", "ruling", "school board", "vote",
    },
    "safety": {
        "attack", "crime", "health", "hate", "hospital", "killed", "murder",
        "safety", "shooting", "violence",
    },
    "culture": {
        "actor", "artist", "award", "book", "film", "music", "show", "sports",
        "television", "theater",
    },
    "community": {
        "center", "community", "fundraiser", "grant", "initiative", "nonprofit",
        "organizer", "support", "volunteer",
    },
}


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def editorial_context(story: dict) -> tuple[str, str]:
    """Return a grounded context category and line for a story.

    This is deliberately not labeled as the host's opinion. A real host take
    can replace the generated section later through `host_take.apply_takes`.
    """
    haystack = " ".join(
        [
            story.get("title", ""),
            story.get("summary", ""),
            " ".join(story.get("matched_terms", [])),
        ]
    ).lower()
    for category in ("policy", "safety", "culture", "community"):
        if any(term in haystack for term in _ANGLE_TERMS[category]):
            return category, EDITORIAL_ANGLES[category]
    return "default", EDITORIAL_ANGLES["default"]


def build_reel_script(handoff: dict) -> dict:
    """Build a Reel script draft from a research handoff packet."""
    lane = handoff.get("lane", "")
    story = handoff.get("story", {})
    title = story.get("title") or handoff.get("topic", "")
    summary = story.get("summary", "")
    source = story.get("source", "")
    url = story.get("url", "")

    story_line = _truncate_words(summary or title, 40)
    context_category, context_line = editorial_context(story)
    spoken_title = title.rstrip(".")

    sections = [
        {
            "id": "hook",
            "narration": f"{spoken_title}. Here is what happened.",
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
            "narration": context_line,
            "duration_seconds": 12,
            "take_slot": True,
            "take_source": "deterministic_context",
            "context_category": context_category,
            "visual_hint": "Lane-colored emphasis card, community imagery",
        },
        {
            "id": "cta",
            "narration": (
                f"Reporting comes from {source}. The link is in the description. "
                "Follow for tomorrow's queer news roundup."
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
            "tone_profile": "warm_direct_story_first",
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
