"""Build daily story candidate JSON for What's the LGBT, Fish?"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .filter import evaluate_story
from .ranker import score_story


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
        "scope": ["gay", "lesbian", "bisexual", "Black trans"],
        "items": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    items = json.loads(input_path.read_text())
    digest = build_daily_candidates(items)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(digest, indent=2) + "\n")

    print(f"Wrote {len(digest['items'])} candidates to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
