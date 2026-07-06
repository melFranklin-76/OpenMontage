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
