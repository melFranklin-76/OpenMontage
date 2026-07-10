"""Bridge FISH daily digest candidates into Creator Studio research.

Takes a ranked daily digest (from daily_digest) and produces a research
handoff packet for the top candidate: a grounded, story-specific seed the
agent uses when producing the research_brief for a Creator Studio run,
instead of placeholder research content.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .intake import fetch_live_stories
from .daily_digest import build_daily_candidates

SHOW_NAME = "What's the LGBT, Fish?"

LANE_ANGLES = {
    "gay": "Why this matters to gay audiences right now",
    "lesbian": "The lesbian community story behind the headline",
    "bisexual": "A bi visibility moment worth 45 seconds",
    "Black trans": "Centering Black trans voices on this story",
}


def select_candidate(digest: dict, rank: int = 1) -> dict:
    """Return the candidate at the given 1-indexed rank."""
    items = digest.get("items", [])
    if not items:
        raise ValueError("Digest has no candidates")
    if rank < 1 or rank > len(items):
        raise ValueError(f"Rank {rank} out of range (1-{len(items)})")
    return items[rank - 1]


def build_research_handoff(candidate: dict, digest_date: str, rank: int = 1) -> dict:
    """Build a grounded research seed packet from a digest candidate."""
    lane = candidate.get("matched_lane", "")
    title = candidate.get("title", "")
    summary = candidate.get("summary", "")
    url = candidate.get("url", "")
    source = candidate.get("source", "")

    return {
        "show": SHOW_NAME,
        "handoff_date": date.today().isoformat(),
        "digest_date": digest_date,
        "digest_rank": rank,
        "topic": title,
        "lane": lane,
        "relevance_score": candidate.get("relevance_score", 0.0),
        "story": {
            "title": title,
            "source": source,
            "url": url,
            "published_at": candidate.get("published_at", ""),
            "summary": summary,
        },
        "research_seed": {
            "primary_source": {"name": source, "url": url},
            "data_points": [
                {
                    "claim": summary or title,
                    "source_url": url,
                    "source_name": source,
                    "credibility": "secondary_source",
                    "usable_as": "hook",
                }
            ],
            "suggested_angle": LANE_ANGLES.get(lane, "Why this story matters"),
            "why_now": (
                f"Ranked #{rank} in the {SHOW_NAME} digest on {digest_date} "
                f"with relevance score {candidate.get('relevance_score', 0.0)}."
            ),
            "matched_terms": candidate.get("matched_terms", []),
            "timeliness_window": "48_hours",
        },
        "creator_studio": {
            "suggested_pipeline": "animated-explainer",
            "suggested_platform": "instagram",
            "suggested_persona": "mel",
            "run_hint": (
                "python creator-studio/run.py --approve "
                f"--topic {json.dumps(title)} --platform instagram "
                "--pipeline animated-explainer"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--digest", help="Path to a daily digest JSON file")
    source.add_argument(
        "--live",
        action="store_true",
        help="Fetch live stories and build the digest in one step",
    )
    parser.add_argument("--rank", type=int, default=1, help="1-indexed candidate rank")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.live:
        digest = build_daily_candidates(fetch_live_stories())
    else:
        digest = json.loads(Path(args.digest).read_text())

    candidate = select_candidate(digest, rank=args.rank)
    handoff = build_research_handoff(candidate, digest.get("date", ""), rank=args.rank)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(handoff, indent=2) + "\n")

    print(f"Wrote research handoff for [{handoff['lane']}] {handoff['topic']}")
    print(f"  -> {output_path}")
    print(f"  Run: {handoff['creator_studio']['run_hint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
