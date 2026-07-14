"""Build daily story candidate JSON for What's the LGBT, Fish?"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .filter import evaluate_story
from .intake import fetch_live_stories
from .ranker import score_story
from .social_research import fetch_social_stories


def build_daily_candidates(items: list[dict[str, str]]) -> dict:
    candidates = []

    for item in items:
        result = evaluate_story(item.get("title", ""), item.get("summary", ""))
        if not result.accepted:
            continue

        candidates.append(
            {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "published_at": item.get("published_at", ""),
                "matched_lane": result.lane,
                "matched_terms": result.matched_terms,
                "summary": item.get("summary", ""),
                "relevance_score": score_story(
                    result.lane,
                    item.get("title", ""),
                    item.get("summary", ""),
                ),
                "status": "candidate",
            }
        )

    candidates.sort(key=lambda row: row["relevance_score"], reverse=True)

    return {
        "show": "What's the LGBT, Fish?",
        "date": date.today().isoformat(),
        "scope": ["lesbian", "gay", "bisexual", "trans"],
        "items": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Path to a normalized stories JSON file")
    source.add_argument(
        "--live",
        action="store_true",
        help="Fetch stories live from the configured RSS sources",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--limit-per-source",
        type=int,
        default=20,
        help="Max stories to pull from each source in --live mode",
    )
    parser.add_argument(
        "--social",
        action="store_true",
        help="Supplement RSS stories with Reddit, HN, and web social sources",
    )
    parser.add_argument(
        "--social-only",
        action="store_true",
        help="Use only social sources, skip RSS entirely",
    )
    parser.add_argument(
        "--social-topic",
        default="LGBT LGBTQ lesbian gay bisexual transgender news",
        help="Search query for web/Twitter/HN social sources",
    )
    parser.add_argument(
        "--creator-watch",
        action="store_true",
        help="Boost stories overlapping watched creators' latest episode topics",
    )
    args = parser.parse_args()

    if args.social_only:
        items = fetch_social_stories(topic=args.social_topic)
    elif args.live:
        items = fetch_live_stories(limit_per_source=args.limit_per_source)
        if args.social:
            items = items + fetch_social_stories(topic=args.social_topic)
    else:
        items = json.loads(Path(args.input).read_text())
        if args.social:
            items = items + fetch_social_stories(topic=args.social_topic)

    digest = build_daily_candidates(items)

    if args.creator_watch:
        from .creator_watch import boost_candidates, creator_topic_signals
        digest = boost_candidates(digest, creator_topic_signals())

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(digest, indent=2) + "\n")

    print(f"Wrote {len(digest['items'])} candidates to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
