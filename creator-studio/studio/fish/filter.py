"""Editorial filter for What's the LGBT, Fish?"""

from __future__ import annotations

from dataclasses import dataclass


ACCEPT_TERMS = (
    "gay",
    "lesbian",
    "bisexual",
    "bi ",
    "black trans",
    "black transgender",
    "transgender woman",
    "transgender man",
    "trans woman",
    "trans man",
)

REJECT_TERMS = (
    "pronoun debate",
    "what are pronouns",
    "cisgender explainer",
    "cis vs",
    "lgbtqia meaning",
)

LEGACY_ICONS = (
    "stonewall",
    "marsha p. johnson",
    "marsha p johnson",
    "sylvia rivera",
    "victoria cruz",
    "miss major",
    "bayard rustin",
    "barbara gittings",
    "frank kameny",
)


@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    matched_terms: list[str]
    rejected_terms: list[str]
    lane: str | None


def _is_legacy_story(text: str) -> bool:
    haystack = text.lower()
    return any(icon in haystack for icon in LEGACY_ICONS)


def classify_lane(text: str, title: str = "") -> str | None:
    haystack = text.lower()

    if _is_legacy_story(title.lower()):
        return "legacy"
    if "black trans" in haystack or "black transgender" in haystack:
        return "Black trans"
    if "lesbian" in haystack:
        return "lesbian"
    if "bisexual" in haystack or "bi " in haystack:
        return "bisexual"
    if "gay" in haystack:
        return "gay"
    if "transgender" in haystack or "trans woman" in haystack or "trans man" in haystack:
        return "transgender-review"

    return None


def evaluate_story(title: str, summary: str = "") -> FilterResult:
    text = f"{title} {summary}".lower()

    rejected = [term for term in REJECT_TERMS if term in text]
    matched = [term for term in ACCEPT_TERMS if term in text]
    title_lower = title.lower()
    lane = classify_lane(text, title)

    if lane == "legacy":
        accepted = not rejected
        if not matched:
            matched = [icon for icon in LEGACY_ICONS if icon in title_lower]
    else:
        accepted = bool(matched) and not rejected and lane != "transgender-review"

    return FilterResult(
        accepted=accepted,
        matched_terms=matched,
        rejected_terms=rejected,
        lane=lane,
    )
