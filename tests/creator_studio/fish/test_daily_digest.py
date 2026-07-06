import json

from studio.fish import daily_digest
from studio.fish.daily_digest import build_daily_candidates


def test_build_daily_candidates_filters_and_scores() -> None:
    digest = build_daily_candidates(
        [
            {
                "title": "Black trans organizer leads Milwaukee safety initiative",
                "source": "Example",
                "url": "https://example.com/1",
                "summary": "Community safety and health resources.",
            },
            {
                "title": "Generic entertainment story",
                "source": "Example",
                "url": "https://example.com/2",
                "summary": "No matching scope.",
            },
        ]
    )

    assert digest["show"] == "What's the LGBT, Fish?"
    assert len(digest["items"]) == 1
    assert digest["items"][0]["matched_lane"] == "Black trans"


def test_main_live_mode_fetches_filters_and_writes(monkeypatch, tmp_path) -> None:
    def fake_fetch(limit_per_source=20):
        return [
            {
                "title": "Gay artist announces new project",
                "source": "Live Feed",
                "url": "https://example.com/live",
                "summary": "A new project.",
            },
            {
                "title": "Unrelated tech story",
                "source": "Live Feed",
                "url": "https://example.com/tech",
                "summary": "No matching scope.",
            },
        ]

    monkeypatch.setattr(daily_digest, "fetch_live_stories", fake_fetch)
    output_path = tmp_path / "daily.json"
    monkeypatch.setattr(
        "sys.argv", ["daily_digest", "--live", "--output", str(output_path)]
    )

    assert daily_digest.main() == 0

    data = json.loads(output_path.read_text())
    assert data["show"] == "What's the LGBT, Fish?"
    assert len(data["items"]) == 1
    assert data["items"][0]["matched_lane"] == "gay"
    assert data["items"][0]["source"] == "Live Feed"
