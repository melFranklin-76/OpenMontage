"""Placeholder RSS intake module for What's the LGBT, Fish?

Next step: replace sample input with real RSS fetching.
"""

from __future__ import annotations

from .sources import list_sources


def get_configured_sources() -> list[dict[str, str]]:
    return list_sources()
