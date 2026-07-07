from studio.fish.filter import classify_lane, evaluate_story


def test_accepts_gay_story() -> None:
    result = evaluate_story("Gay artist announces new community project")
    assert result.accepted
    assert result.lane == "gay"


def test_accepts_lesbian_story() -> None:
    result = evaluate_story("Lesbian filmmaker wins major award")
    assert result.accepted
    assert result.lane == "lesbian"


def test_accepts_bisexual_story() -> None:
    result = evaluate_story("Bisexual advocate launches health campaign")
    assert result.accepted
    assert result.lane == "bisexual"


def test_accepts_black_trans_story() -> None:
    result = evaluate_story("Black trans organizer leads safety initiative")
    assert result.accepted
    assert result.lane == "Black trans"


def test_accepts_legacy_stonewall_story() -> None:
    result = evaluate_story(
        "Victoria Cruz, Stonewall hero and trans activist, dies at 79"
    )
    assert result.accepted
    assert result.lane == "legacy"


def test_legacy_takes_priority_over_other_lanes() -> None:
    result = evaluate_story(
        "Marsha P. Johnson honored as gay rights pioneer"
    )
    assert result.accepted
    assert result.lane == "legacy"


def test_legacy_accepts_even_without_core_lane_terms() -> None:
    result = evaluate_story(
        "Sylvia Rivera's legacy lives on in community organizing"
    )
    assert result.accepted
    assert result.lane == "legacy"


def test_general_trans_story_stays_rejected() -> None:
    result = evaluate_story("Trans woman wins local award")
    assert not result.accepted
    assert result.lane == "transgender-review"


def test_legacy_keyword_in_summary_only_does_not_match_legacy_lane() -> None:
    result = evaluate_story(
        "Advocate NL 7/6/26",
        summary="Stonewall anniversary celebrations continue across NYC",
    )
    assert result.lane != "legacy"


def test_classify_lane_legacy_requires_title() -> None:
    assert classify_lane("stonewall anniversary recap", title="Advocate NL 7/6/26") is None
    assert classify_lane("stonewall anniversary recap", title="Stonewall at 57") == "legacy"


def test_rejects_pronoun_debate() -> None:
    result = evaluate_story("What are pronouns and why debate continues")
    assert not result.accepted
