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


# Story subject → stock-footage concept.
#
# Pexels is a stock library: it has no news footage. A literal headline search
# ("Lesbian author banned from library board meeting") matches nothing, so we
# used to fall straight through to the lane term and get generic pride footage
# on every single story. Mapping the story's *subject* to a concrete visual
# concept that stock libraries actually carry is what makes the background
# read as belonging to the story — a library ban gets bookshelves, a court
# ruling gets a courthouse.
#
# Order matters: the first matching entry wins, so put the specific before the
# generic (book-ban before books, legislature before law).
TOPIC_VISUALS: tuple[tuple[tuple[str, ...], str], ...] = (
    # Death outranks the subject's profession: an obituary for a drag performer
    # should get a vigil, not party footage from a nightclub.
    (("dies", "died", "death", "obituary", "memorial", "funeral", "vigil", "killed",
      "murder", "mourns"), "candle vigil memorial"),
    (("book ban", "banned book", "library", "librarian"), "library bookshelves reading"),
    (("supreme court", "court", "judge", "lawsuit", "ruling", "sued", "trial", "verdict"),
     "courthouse justice gavel"),
    (("senate", "congress", "governor", "lawmaker", "legislature", "bill", "statehouse",
      "president", "white house", "policy", "law"), "government capitol building"),
    (("election", "vote", "voter", "ballot", "campaign", "poll"), "voting ballot election"),
    (("school", "student", "teacher", "classroom", "campus", "university", "college"),
     "school classroom students"),
    (("hospital", "healthcare", "health", "doctor", "clinic", "medical", "hormone",
      "surgery", "hiv", "prep"), "hospital medical doctor"),
    (("protest", "march", "rally", "demonstration", "activist", "boycott"),
     "protest march crowd"),
    (("police", "arrest", "officer", "sheriff", "raid"), "police officer street"),
    (("church", "religious", "pastor", "faith", "christian", "catholic", "bible"),
     "church interior architecture"),
    (("film", "movie", "actor", "actress", "cinema", "hollywood", "director", "series"),
     "cinema film production"),
    (("music", "singer", "album", "song", "concert", "tour", "rapper", "band"),
     "concert stage lights"),
    (("sport", "athlete", "olympic", "player", "league", "team", "swim", "track"),
     "stadium athlete sport"),
    (("drag", "ballroom", "nightclub", "bar", "nightlife"), "nightclub stage lights"),
    (("award", "honored", "prize", "wins", "winner", "gala"), "award trophy stage"),
    (("housing", "homeless", "shelter", "eviction", "rent"), "city apartment housing"),
    (("military", "veteran", "soldier", "army", "troops", "navy"), "military soldier flag"),
    (("book", "author", "novel", "writer", "memoir"), "books reading writing"),
    (("company", "brand", "corporate", "business", "ceo", "workplace", "employer"),
     "office business workplace"),
    (("parade", "pride festival", "pride month"), "pride parade crowd"),
)


def topic_query(title: str) -> str:
    """Map a headline to a stock-footage concept. Empty string if no match."""
    low = title.lower()
    for keywords, visual in TOPIC_VISUALS:
        if any(kw in low for kw in keywords):
            return visual
    return ""


def build_query(title: str, lane: str = "") -> str:
    """Deterministic, literal search query from a story title.

    Keeps the first few content words of the headline. The ``lane`` argument
    is accepted for signature compatibility but intentionally not appended —
    the lane term is reserved for the last-resort fallback in
    ``fetch_broll_for_story``.
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

    Search order, most story-relevant first:

    1. The story's *subject* mapped to a stock-footage concept — a library ban
       gets bookshelves, a court ruling gets a courthouse. Stock libraries
       carry these, so this is the query that actually lands.
    2. The literal headline words, in case the subject is something stock
       happens to cover directly.
    3. The lane term, as a last resort so we always have *something*.
    """
    if not _api_key():
        return None

    queries = [q for q in (
        topic_query(title),
        build_query(title, lane),
        LANE_SEARCH_TERMS.get(lane, DEFAULT_SEARCH_TERM),
    ) if q]

    for query in queries:
        url = search_broll(query, orientation=orientation)
        if url:
            got = download_broll(url, out_path)
            if got:
                print(f"[broll] fetched clip for {query!r}", file=sys.stderr)
                return got
    return None
