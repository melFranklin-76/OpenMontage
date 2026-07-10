"""Stock b-roll fetching for FISH renders via the Pexels Videos API.

Free tier: 200 requests/hour, no attribution required. Sign up at
https://www.pexels.com/api/ and export PEXELS_API_KEY (locally) or add it
as a GitHub Actions secret of the same name.

Fallback ladder (renderers use this order, never fail on missing footage):
    Pexels clip → story hero image w/ Ken Burns → lane color card

Query strategy is deterministic: strip stopwords from the story title,
keep the first few content words, and append a lane-flavored search term
so even a vague title lands on something visually relevant.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

# Words that carry no visual-search value
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "his", "her", "their",
    "after", "before", "over", "under", "about", "into", "out", "up", "down",
    "new", "says", "said", "gets", "get", "got", "will", "would", "could",
    "photos", "video", "watch", "report", "breaking", "exclusive", "update",
    "why", "how", "what", "who", "when", "where", "just", "still", "more",
}

# Lane-flavored terms — used ONLY as a fallback query when the story-specific
# query returns no footage (see fetch_broll_for_story). They are deliberately
# NOT mixed into the primary query: appending "gay pride rainbow crowd" to
# every search made Pexels return generic pride footage instead of clips that
# match the actual story.
LANE_SEARCH_TERMS = {
    "lesbian":     "lesbian couple pride",
    "gay":         "gay pride rainbow crowd",
    "bisexual":    "bisexual pride flag",
    "Black trans": "Black community rally support",
}
DEFAULT_SEARCH_TERM = "pride rainbow flag community"


def build_query(title: str, lane: str = "") -> str:
    """Deterministic, story-relevant search query from a story title.

    Keeps the first few content words of the headline so the footage matches
    the story itself. The ``lane`` argument is accepted for signature
    compatibility but intentionally not appended — the lane term is reserved
    for the fallback query in ``fetch_broll_for_story``.
    """
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", title.lower())
    content = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    head = " ".join(content[:5])
    return head or DEFAULT_SEARCH_TERM


def _api_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def search_broll(
    query: str,
    orientation: str = "landscape",
    min_width: int = 1280,
    timeout: int = 15,
) -> str | None:
    """Return the best matching Pexels video file URL, or None.

    orientation: "landscape" (roundup) or "portrait" (shorts).
    Picks the smallest video file that still meets min_width — full 4K
    downloads are a waste of CI bandwidth.
    """
    key = _api_key()
    if not key:
        return None

    params = urllib.parse.urlencode({
        "query": query,
        "orientation": orientation,
        "per_page": 3,
        "size": "medium",
    })
    req = urllib.request.Request(
        f"{PEXELS_SEARCH_URL}?{params}",
        headers={"Authorization": key, "User-Agent": "fish-pipeline/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(f"[broll] pexels search failed ({query!r}): {exc}", file=sys.stderr)
        return None

    for video in data.get("videos", []):
        files = video.get("video_files", [])
        candidates = [
            f for f in files
            if f.get("width", 0) >= min_width and f.get("link")
            and (f.get("file_type") or "").endswith("mp4")
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda f: f.get("width", 10**9))
        return best["link"]
    return None


def download_broll(url: str, out_path: Path, timeout: int = 60) -> Path | None:
    """Download a b-roll clip. Returns the path, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fish-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) < 50_000:      # sanity: a real clip is bigger than 50 KB
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path
    except Exception as exc:  # noqa: BLE001
        print(f"[broll] download failed: {exc}", file=sys.stderr)
        return None


def fetch_broll_for_story(
    title: str,
    lane: str,
    out_path: Path,
    orientation: str = "landscape",
) -> Path | None:
    """One-call ladder step: query → search → download. None on any miss.

    Tries the title-derived query first, then the pure lane term, so a
    hyper-specific headline still lands on generic lane footage.
    """
    if not _api_key():
        return None
    for query in (
        build_query(title, lane),
        LANE_SEARCH_TERMS.get(lane, DEFAULT_SEARCH_TERM),
    ):
        url = search_broll(query, orientation=orientation)
        if url:
            got = download_broll(url, out_path)
            if got:
                print(f"[broll] fetched clip for {query!r}", file=sys.stderr)
                return got
    return None
