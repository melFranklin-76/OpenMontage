"""Story ranking for What's the LGBT, Fish?"""

from __future__ import annotations


LANE_WEIGHTS = {
    "legacy": 1.0,
    "Black trans": 1.0,
    "lesbian": 0.9,
    "gay": 0.85,
    "bisexual": 0.85,
}


def score_story(lane: str | None, title: str, summary: str = "") -> float:
    base = LANE_WEIGHTS.get(lane or "", 0.0)
    text = f"{title} {summary}".lower()

    boost_terms = (
        "breaking",
        "today",
        "court",
        "law",
        "health",
        "safety",
        "culture",
        "artist",
        "film",
        "music",
        "history",
        "milwaukee",
        "black",
    )

    boost = sum(0.02 for term in boost_terms if term in text)
    return round(min(base + boost, 1.0), 3)
