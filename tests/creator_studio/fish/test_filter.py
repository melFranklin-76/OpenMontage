from studio.fish.filter import evaluate_story


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
    assert result.lane == "trans"


def test_legacy_lane_no_longer_exists() -> None:
    """The legacy lane was removed; only the four core lanes remain.

    A story about a movement icon is now classified by its core lane terms —
    e.g. a "gay rights pioneer" headline lands in the gay lane, not "legacy".
    """
    result = evaluate_story("Marsha P. Johnson honored as gay rights pioneer")
    assert result.accepted
    assert result.lane == "gay"


def test_icon_only_story_without_core_terms_is_not_accepted() -> None:
    """Without a core lane term, an icon-only story no longer auto-accepts.

    There is no legacy lane to catch it, so it needs a lesbian/gay/bi/Black
    trans signal like any other story.
    """
    result = evaluate_story("Sylvia Rivera's legacy lives on in community organizing")
    assert result.lane is None
    assert not result.accepted


def test_no_lane_is_ever_legacy() -> None:
    for title in (
        "Victoria Cruz, Stonewall hero, dies at 79",
        "Stonewall anniversary celebrations continue across NYC",
    ):
        assert evaluate_story(title).lane != "legacy"


def test_general_trans_story_stays_rejected() -> None:
    result = evaluate_story("Trans woman wins local award")
    assert not result.accepted
    assert result.lane == "transgender-review"


def test_rejects_pronoun_debate() -> None:
    result = evaluate_story("What are pronouns and why debate continues")
    assert not result.accepted
