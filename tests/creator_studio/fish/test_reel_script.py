import json

from studio.fish import reel_script
from studio.fish.reel_script import TARGET_DURATION_SECONDS, build_reel_script


HANDOFF = {
    "show": "What's the LGBT, Fish?",
    "handoff_date": "2026-07-06",
    "digest_date": "2026-07-06",
    "digest_rank": 1,
    "topic": "Black trans organizer leads Milwaukee safety initiative",
    "lane": "trans",
    "relevance_score": 1.0,
    "story": {
        "title": "Black trans organizer leads Milwaukee safety initiative",
        "source": "TransGriot",
        "url": "https://example.com/1",
        "published_at": "2026-07-06T08:00:00-05:00",
        "summary": "Community safety and health resources.",
    },
}


def test_build_reel_script_structure() -> None:
    script = build_reel_script(HANDOFF)

    assert script["show"] == "What's the LGBT, Fish?"
    assert script["format"] == "reel"
    assert script["lane"] == "trans"
    assert [s["id"] for s in script["sections"]] == [
        "hook",
        "story",
        "why_it_matters",
        "cta",
    ]


def test_sections_fit_target_duration() -> None:
    script = build_reel_script(HANDOFF)
    total = sum(s["duration_seconds"] for s in script["sections"])
    assert total == TARGET_DURATION_SECONDS


def test_narration_grounded_in_story() -> None:
    script = build_reel_script(HANDOFF)
    hook = script["sections"][0]["narration"]
    story = script["sections"][1]["narration"]
    cta = script["sections"][3]["narration"]

    assert HANDOFF["story"]["title"] in hook
    assert story == HANDOFF["story"]["summary"]
    assert "TransGriot" in cta
    assert script["source_attribution"]["url"] == "https://example.com/1"


def test_lane_hashtags_and_caption() -> None:
    script = build_reel_script(HANDOFF)
    assert "#trans" in script["hashtags"]
    # The show still selects these stories, but no longer labels them
    # "Black trans" in public-facing copy.
    assert "#blacktrans" not in script["hashtags"]
    assert "#whatsthelgbtfish" in script["hashtags"]
    assert HANDOFF["topic"] in script["caption"]


def test_unknown_lane_falls_back_to_base_hashtags() -> None:
    handoff = dict(HANDOFF, lane="")
    script = build_reel_script(handoff)
    assert script["hashtags"] == reel_script.BASE_HASHTAGS


def test_long_summary_is_truncated() -> None:
    long_summary = " ".join(["word"] * 80)
    handoff = dict(HANDOFF, story=dict(HANDOFF["story"], summary=long_summary))
    script = build_reel_script(handoff)
    narration = script["sections"][1]["narration"]
    assert len(narration.split()) == 40
    assert narration.endswith("...")


def test_main_writes_script_from_handoff_file(monkeypatch, tmp_path) -> None:
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps(HANDOFF))
    output_path = tmp_path / "script.json"

    monkeypatch.setattr(
        "sys.argv",
        ["reel_script", "--handoff", str(handoff_path), "--output", str(output_path)],
    )

    assert reel_script.main() == 0

    data = json.loads(output_path.read_text())
    assert data["topic"] == HANDOFF["topic"]
    assert data["digest_rank"] == 1
    assert len(data["sections"]) == 4
