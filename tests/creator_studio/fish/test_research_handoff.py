import json

import pytest

from studio.fish import research_handoff
from studio.fish.research_handoff import build_research_handoff, select_candidate


DIGEST = {
    "show": "What's the LGBT, Fish?",
    "date": "2026-07-06",
    "items": [
        {
            "title": "Black trans organizer leads Milwaukee safety initiative",
            "source": "TransGriot",
            "url": "https://example.com/1",
            "published_at": "2026-07-06T08:00:00-05:00",
            "matched_lane": "trans",
            "matched_terms": ["black trans"],
            "summary": "Community safety and health resources.",
            "relevance_score": 1.0,
            "status": "candidate",
        },
        {
            "title": "Gay artist announces new project",
            "source": "LGBTQ Nation",
            "url": "https://example.com/2",
            "published_at": "",
            "matched_lane": "gay",
            "matched_terms": ["gay"],
            "summary": "A new project.",
            "relevance_score": 0.85,
            "status": "candidate",
        },
    ],
}


def test_select_candidate_returns_top_by_default() -> None:
    candidate = select_candidate(DIGEST)
    assert candidate["title"].startswith("Black trans organizer")


def test_select_candidate_respects_rank() -> None:
    candidate = select_candidate(DIGEST, rank=2)
    assert candidate["matched_lane"] == "gay"


def test_select_candidate_rejects_bad_rank() -> None:
    with pytest.raises(ValueError):
        select_candidate(DIGEST, rank=3)
    with pytest.raises(ValueError):
        select_candidate({"items": []})


def test_build_research_handoff_grounds_seed_in_story() -> None:
    candidate = select_candidate(DIGEST)
    handoff = build_research_handoff(candidate, DIGEST["date"])

    assert handoff["topic"] == candidate["title"]
    assert handoff["lane"] == "trans"
    assert handoff["story"]["url"] == "https://example.com/1"

    seed = handoff["research_seed"]
    assert seed["primary_source"]["url"] == "https://example.com/1"
    assert seed["data_points"][0]["claim"] == candidate["summary"]
    assert "2026-07-06" in seed["why_now"]

    studio = handoff["creator_studio"]
    assert candidate["title"] in studio["run_hint"]
    assert studio["suggested_pipeline"] == "animated-explainer"


def test_main_writes_handoff_from_digest_file(monkeypatch, tmp_path) -> None:
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(json.dumps(DIGEST))
    output_path = tmp_path / "handoff.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "research_handoff",
            "--digest",
            str(digest_path),
            "--rank",
            "2",
            "--output",
            str(output_path),
        ],
    )

    assert research_handoff.main() == 0

    data = json.loads(output_path.read_text())
    assert data["digest_rank"] == 2
    assert data["lane"] == "gay"
    assert data["digest_date"] == "2026-07-06"
