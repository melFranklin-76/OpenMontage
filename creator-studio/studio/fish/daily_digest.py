"""Build daily story candidate JSON for What's the LGBT, Fish?"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .filter import evaluate_story
from .intake import fetch_live_stories
from .ranker import score_story
from .social_research import fetch_social_stories
from .story_memory import (
    DEFAULT_STATE_PATH as USED_STATE_PATH,
    RECORD_COUNT,
    apply_nightly_gates,
    load_state,
    record_used,
    save_state,
)


def build_daily_candidates(
    items: list[dict[str, str]],
    *,
    now: datetime | None = None,
    used_state: dict | None = None,
) -> dict:
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

    current = now or datetime.now(timezone.utc)
    gated, selection = apply_nightly_gates(
        candidates,
        now=current,
        today=current.date(),
        used_state=used_state,
    )

    return {
        "show": "What's the LGBT, Fish?",
        "date": current.date().isoformat(),
        "scope": ["lesbian", "gay", "bisexual", "trans"],
        "selection": selection,
        "items": gated,
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
        help="Let watched creators' latest episode topics steer tonight's "
             "ranking: overlapping RSS stories become the agenda",
    )
    parser.add_argument(
        "--creator-watch-state",
        default=None,
        help="Where creator-watch remembers mined topics between runs, so a "
             "channel that posts ~5x/week still counts on the nights between "
             "uploads",
    )
    parser.add_argument(
        "--used-state",
        default=None,
        help="Where last night's roundup stories are remembered so the same "
             "headlines cannot win again while they are still in the feeds "
             f"(default live path: {USED_STATE_PATH})",
    )
    parser.add_argument(
        "--record-used",
        type=int,
        default=RECORD_COUNT,
        help="How many of tonight's top stories to remember for later nights. "
             "0 skips recording (useful in tests).",
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

    used_path = Path(args.used_state) if args.used_state else None
    used_state = load_state(used_path) if used_path else {"version": 1, "stories": []}
    digest = build_daily_candidates(items, used_state=used_state)

    if args.creator_watch:
        from .creator_watch import boost_candidates, creator_topic_signals, sort_by_agenda
        state_path = (Path(args.creator_watch_state)
                      if args.creator_watch_state else None)
        digest = boost_candidates(digest, creator_topic_signals(state_path))
        digest["items"] = sort_by_agenda(digest.get("items", []))

    if used_path is not None and args.record_used > 0:
        used_state = record_used(
            used_state,
            digest.get("items", []),
            limit=args.record_used,
        )
        save_state(used_path, used_state)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(digest, indent=2) + "\n")

    selection = digest.get("selection") or {}
    print(
        f"Wrote {len(digest['items'])} candidates to {output_path}"
        f" (dropped stale={selection.get('dropped_stale', 0)}"
        f" used={selection.get('dropped_used', 0)}"
        f" duplicate={selection.get('dropped_duplicate', 0)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
