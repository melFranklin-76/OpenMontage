"""Tests for host takes — replacing stock editorial lines with the host's own."""

from __future__ import annotations

from studio.fish import host_take as ht
from studio.fish.long_roundup_script import LANE_ANALYSIS_LINES
from studio.fish.reel_script import LANE_WHY_LINES

GAY_WHY = LANE_WHY_LINES["gay"]
GAY_ANALYSIS = LANE_ANALYSIS_LINES["gay"]
TRANS_WHY = LANE_WHY_LINES["trans"]

A_REAL_TAKE = (
    "I went to that church for six years and nobody there would say this out "
    "loud, which is exactly why the vote went the way it did."
)


def _reel(lane="gay", rank=1):
    return {
        "lane": lane,
        "digest_rank": rank,
        "topic": "Gay pastor pushed out",
        "source_attribution": {"name": "Advocate", "url": "https://example.com/1"},
        "sections": [
            {"id": "hook", "narration": "What's the LGBT, Fish? Today: a story."},
            {"id": "why_it_matters", "narration": LANE_WHY_LINES[lane]},
        ],
    }


def _roundup():
    return {
        "stories": [
            {"rank": 1, "lane": "gay", "title": "Story one", "source": "Advocate",
             "url": "https://example.com/1", "summary": "A thing happened."},
            {"rank": 2, "lane": "trans", "title": "Story two", "source": "Them",
             "url": "https://example.com/2", "summary": "Another thing."},
        ],
        "sections": [
            {"id": "cold_open", "narration": "Tonight on the show."},
            {"id": "ch1_body", "story_rank": 1, "lane": "gay",
             "narration": f"Story one happened.\n\nSo why does this matter?\n"
                          f"{GAY_WHY}\n\n{GAY_ANALYSIS}\n\nThat reporting is from Advocate."},
            {"id": "ch2_body", "story_rank": 2, "lane": "trans",
             "narration": f"Story two happened.\n\n{TRANS_WHY}"},
        ],
    }


# ── detecting boilerplate ────────────────────────────────────────────────────

def test_stock_lines_are_detected_in_a_fresh_script():
    """Every story in a lane currently ends with the same paragraph."""
    canned = ht.find_canned(_roundup())
    sections = {c["section"] for c in canned}
    assert sections == {"ch1_body", "ch2_body"}
    # ch1 carries both the why line and the analysis line.
    assert len([c for c in canned if c["section"] == "ch1_body"]) == 2


def test_find_canned_reports_which_constant_it_came_from():
    canned = ht.find_canned(_reel())
    assert canned[0]["origin"] == "LANE_WHY_LINES['gay']"
    assert canned[0]["rank"] == 1


def test_clean_script_reports_nothing():
    script = {"sections": [{"id": "hook", "narration": "Entirely my own words."}]}
    assert ht.find_canned(script) == []
    assert "no stock editorial lines" in ht.describe_canned(script)


# ── applying takes ───────────────────────────────────────────────────────────

def test_reel_take_replaces_the_whole_stock_section():
    updated = ht.apply_takes(_reel(), {1: A_REAL_TAKE})
    why = updated["sections"][1]
    assert why["narration"] == A_REAL_TAKE
    assert why["take_source"] == "host"
    assert ht.find_canned(updated) == []


def test_roundup_take_replaces_stock_text_embedded_mid_paragraph():
    """The roundup splices its stock lines into the story body rather than
    giving them their own section, so substitution has to be by phrase."""
    updated = ht.apply_takes(_roundup(), {1: A_REAL_TAKE, 2: "A second real take "
                                                             "with more than fifteen "
                                                             "words in it for sure."})
    body = updated["sections"][1]["narration"]
    assert A_REAL_TAKE in body
    assert GAY_WHY not in body
    assert GAY_ANALYSIS not in body
    # Surrounding facts survive.
    assert "Story one happened." in body
    assert "That reporting is from Advocate." in body
    assert ht.find_canned(updated) == []


def test_take_is_said_once_even_though_the_body_has_two_stock_lines():
    """A roundup body carries both the why line and the analysis line.

    Substituting into each made the host say the identical take twice in a
    row, which is worse than the boilerplate it replaced.
    """
    updated = ht.apply_takes(_roundup(), {1: A_REAL_TAKE})
    body = updated["sections"][1]["narration"]
    assert body.count(A_REAL_TAKE) == 1
    assert GAY_ANALYSIS not in body
    # Removing a paragraph must not leave a gap behind.
    assert "\n\n\n" not in body


def test_takes_only_touch_their_own_story():
    updated = ht.apply_takes(_roundup(), {1: A_REAL_TAKE})
    assert A_REAL_TAKE in updated["sections"][1]["narration"]
    # Rank 2 had no take, so its stock line must still be flagged.
    remaining = ht.find_canned(updated)
    assert [c["section"] for c in remaining] == ["ch2_body"]


def test_apply_takes_does_not_mutate_the_original():
    script = _reel()
    before = script["sections"][1]["narration"]
    ht.apply_takes(script, {1: A_REAL_TAKE})
    assert script["sections"][1]["narration"] == before


def test_applied_ranks_are_recorded_for_provenance():
    updated = ht.apply_takes(_reel(), {1: A_REAL_TAKE})
    assert updated["metadata"]["host_takes_applied"] == [1]


# ── the prompt file round-trip ───────────────────────────────────────────────

def test_prompt_file_shows_the_stock_line_the_take_will_replace(tmp_path):
    out = ht.write_take_prompts(_roundup(), tmp_path / "takes.md",
                                video_key="roundup", show_date="2026-08-03")
    text = out.read_text()
    assert "## Rank 1 — Story one" in text
    assert "## Rank 2 — Story two" in text
    assert GAY_WHY in text            # shown so the host sees what it replaces
    assert "### Your take" in text
    assert "A thing happened." in text


def test_prompt_file_works_for_a_reel_with_one_story(tmp_path):
    out = ht.write_take_prompts(_reel(), tmp_path / "takes.md",
                                video_key="short-1", show_date="2026-08-03")
    text = out.read_text()
    assert "## Rank 1 — Gay pastor pushed out" in text
    assert "### Your take" in text


def test_unfilled_prompt_file_yields_no_takes(tmp_path):
    out = ht.write_take_prompts(_roundup(), tmp_path / "takes.md",
                                video_key="roundup", show_date="2026-08-03")
    assert ht.read_takes(out) == {}


def test_filled_prompt_file_round_trips(tmp_path):
    out = ht.write_take_prompts(_roundup(), tmp_path / "takes.md",
                                video_key="roundup", show_date="2026-08-03")
    text = out.read_text().replace(ht._PLACEHOLDER, A_REAL_TAKE, 1)
    out.write_text(text)

    takes = ht.read_takes(out)
    assert list(takes) == [1]
    assert takes[1] == A_REAL_TAKE

    updated = ht.apply_takes(_roundup(), takes)
    assert A_REAL_TAKE in updated["sections"][1]["narration"]


def test_a_one_word_take_is_not_an_opinion(tmp_path):
    """Guards the obvious way to defeat the gate."""
    path = tmp_path / "takes.md"
    path.write_text("## Rank 1 — Story\n\n### Your take\n\nyep\n")
    assert ht.read_takes(path) == {}


def test_reader_ignores_the_quoted_stock_line(tmp_path):
    """The stock line is shown as a blockquote; it must not be read back in."""
    path = tmp_path / "takes.md"
    path.write_text(
        f"## Rank 1 — Story\n\n> {GAY_WHY}\n\n### Your take\n\n{A_REAL_TAKE}\n"
    )
    takes = ht.read_takes(path)
    assert takes[1] == A_REAL_TAKE
    assert GAY_WHY not in takes[1]
