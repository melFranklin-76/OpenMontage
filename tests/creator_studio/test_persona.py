from __future__ import annotations

from pathlib import Path

import pytest

from studio.persona import load_persona


def test_load_persona_returns_validated_dict(tmp_path: Path) -> None:
    persona_path = tmp_path / "mel.yaml"
    persona_path.write_text(
        "\n".join(
            [
                "name: Mel",
                "voice: warm",
                "platforms:",
                "  - instagram",
                "default_pipeline: talking-head",
                "default_platform: instagram",
                "branding:",
                "  handle: '@mel'",
                "  style: clean-professional",
            ]
        ),
        encoding="utf-8",
    )

    persona = load_persona(persona_path)

    assert persona["name"] == "Mel"
    assert persona["platforms"] == ["instagram"]
    assert persona["default_platform"] == "instagram"


def test_load_persona_requires_default_platform_in_platforms(tmp_path: Path) -> None:
    persona_path = tmp_path / "broken.yaml"
    persona_path.write_text(
        "\n".join(
            [
                "name: Mel",
                "voice: warm",
                "platforms:",
                "  - youtube",
                "default_pipeline: talking-head",
                "default_platform: instagram",
                "branding:",
                "  handle: '@mel'",
                "  style: clean-professional",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="default_platform"):
        load_persona(persona_path)

