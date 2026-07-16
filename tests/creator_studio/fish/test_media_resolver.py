"""Offline tests for exact, reusable FISH story media resolution."""

from __future__ import annotations

import json

from studio.fish import media_resolver as media


def test_license_allowlist_rejects_noncommercial_and_no_derivatives() -> None:
    for allowed in ("CC0", "PDM", "Public Domain", "CC BY 4.0", "CC BY-SA 4.0"):
        assert media.is_approved_license(allowed)
    for rejected in ("CC BY-NC 4.0", "CC BY-ND 4.0", "All Rights Reserved", "GFDL"):
        assert not media.is_approved_license(rejected)


def test_extract_subjects_prioritizes_named_person() -> None:
    subjects = media.extract_subjects("Marsha P. Johnson honored at New York memorial")
    assert subjects[0].startswith("Marsha")
    assert len(subjects) <= 2


def test_search_wikimedia_parses_credit_and_license(monkeypatch) -> None:
    response = {
        "query": {"pages": {"1": {
            "title": "File:Marsha P Johnson portrait.jpg",
            "imageinfo": [{
                "mime": "image/jpeg",
                "url": "https://upload.example/full.jpg",
                "thumburl": "https://upload.example/1920.jpg",
                "descriptionurl": "https://commons.example/file",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                    "Artist": {"value": "<b>Jane Photographer</b>"},
                    "ImageDescription": {"value": "Portrait of Marsha P Johnson"},
                },
            }],
        }}},
    }
    monkeypatch.setattr(media, "_get_json", lambda *_args, **_kwargs: response)

    assets = media.search_wikimedia("Marsha Johnson")

    assert len(assets) == 1
    assert assets[0].provider == "Wikimedia Commons"
    assert assets[0].creator == "Jane Photographer"
    assert assets[0].rights_status == "approved_open"
    assert assets[0].match_score == 1.0


def test_search_openverse_rejects_weak_or_restricted_matches(monkeypatch) -> None:
    monkeypatch.setattr(media, "_get_json", lambda *_args, **_kwargs: {
        "results": [
            {
                "title": "Bayard Rustin speaking",
                "creator": "Archive",
                "license": "by",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "foreign_landing_url": "https://source.example/rustin",
                "url": "https://images.example/rustin.jpg",
            },
            {
                "title": "Bayard Rustin speaking",
                "creator": "Archive",
                "license": "by-nc",
                "foreign_landing_url": "https://source.example/restricted",
                "url": "https://images.example/restricted.jpg",
            },
            {
                "title": "Unrelated pride flags",
                "creator": "Someone",
                "license": "cc0",
                "foreign_landing_url": "https://source.example/unrelated",
                "url": "https://images.example/unrelated.jpg",
            },
        ]
    })

    assets = media.search_openverse("Bayard Rustin")

    assert [asset.source_url for asset in assets] == ["https://source.example/rustin"]


def test_resolver_prefers_best_exact_candidate(monkeypatch) -> None:
    weaker = media.MediaAsset(
        "Sylvia Rivera", "image", "Wikimedia Commons", "https://one", "https://one.jpg",
        "One", "CC BY", "https://license", "One via Commons", "approved_open", 0.5,
        "Sylvia Rivera",
    )
    exact = media.MediaAsset(
        "Sylvia Rivera", "image", "Openverse", "https://two", "https://two.jpg",
        "Two", "CC0", "https://license", "Two via Openverse", "approved_open", 1.0,
        "Sylvia Rivera",
    )
    monkeypatch.setattr(media, "search_wikimedia", lambda _subject: [weaker])
    monkeypatch.setattr(media, "search_openverse", lambda _subject: [exact])

    assert media.resolve_story_media("Sylvia Rivera remembered by activists") == exact


def test_manifest_deduplicates_source_urls(tmp_path) -> None:
    asset = media.MediaAsset(
        "Miss Major", "image", "Openverse", "https://source", "https://image.jpg",
        "Photographer", "CC BY", "https://license", "Photographer, CC BY",
        "approved_open", 1.0, "Miss Major",
    )
    video = tmp_path / "fish-roundup.mp4"

    path = media.write_media_manifest(video, [asset, asset])
    payload = json.loads(path.read_text())

    assert path.name == "fish-roundup.media.json"
    assert len(payload["assets"]) == 1
    assert payload["assets"][0]["creator"] == "Photographer"


def test_extract_subjects_ignores_title_case_junk_names() -> None:
    """Title-Case headlines make every bigram look like a person.

    "Not Feeling The" was extracted as a "person", searched on Wikimedia,
    and shipped a random concert photo under a Kamala Harris story.
    """
    for title in (
        "Not Feeling The (White) Trans Community Hatred Of Kamala Harris",
        "Trans Actors Can Be In The Building And Still Get Ignored",
        "31st GLAAD Media Awards Happening July 29-30",
    ):
        for subject in media.extract_subjects(title):
            assert len(subject.split()) >= 3, (
                f"short pseudo-name {subject!r} extracted from {title!r}"
            )


def test_extract_subjects_still_finds_people_in_sentence_case() -> None:
    assert media.extract_subjects(
        "Tributes pour in for Laverne Cox after historic win"
    )[0] == "Laverne Cox"


def test_match_score_ignores_function_words() -> None:
    """'not' and 'the' must not count as evidence an image matches."""
    assert media._match_score(
        "Not Feeling The", "Singer not on the stage during the concert"
    ) == 0.0
