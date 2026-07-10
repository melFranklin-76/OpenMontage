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

@dataclass(frozen=True)
class FilterResult:
    accepted: bool
    matched_terms: list[str]
    rejected_terms: list[str]
    lane: str | None


def classify_lane(text: str) -> str | None:
    haystack = text.lower()

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
    lane = classify_lane(text)

    accepted = bool(matched) and not rejected and lane != "transgender-review"

    return FilterResult(
        accepted=accepted,
        matched_terms=matched,
        rejected_terms=rejected,
        lane=lane,
    )
