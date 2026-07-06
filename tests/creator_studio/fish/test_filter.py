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
    assert result.lane == "Black trans"


def test_rejects_pronoun_debate() -> None:
    result = evaluate_story("What are pronouns and why debate continues")
    assert not result.accepted
