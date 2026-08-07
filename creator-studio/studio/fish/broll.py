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
from dataclasses import dataclass
from pathlib import Path

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"

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
    "trans": "trans rights rally support",
}
DEFAULT_SEARCH_TERM = "pride rainbow flag community"

# These subjects are especially damaging when they appear under unrelated
# adult news. They remain available when the headline is actually about them.
_SENSITIVE_VISUAL_TERMS = {
    "baby", "babies", "boy", "child", "children", "daughter", "family",
    "father", "girl", "infant", "kid", "kids", "mother", "parent", "parents",
    "son",
}


@dataclass(frozen=True)
class VisualBrief:
    """Acceptance criteria for one stock-footage request."""

    query: str
    required_terms: frozenset[str]
    forbidden_terms: frozenset[str]


@dataclass(frozen=True)
class BrollCandidate:
    """A stock-video result with enough context to validate before download."""

    download_url: str
    source_url: str
    descriptor: str


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
    (("protest", "protests", "march", "marches", "rally", "rallies",
      "demonstration", "demonstrations", "activist", "activists", "boycott"),
     "protest march crowd"),
    (("police", "arrest", "officer", "sheriff", "raid"), "police officer street"),
    (("church", "religious", "pastor", "faith", "christian", "catholic", "bible"),
     "church interior architecture"),
    (("film", "movie", "actor", "actress", "cinema", "hollywood", "director", "series"),
     "cinema film production"),
    (("music", "singer", "album", "song", "concert", "tour", "rapper", "band"),
     "concert stage lights"),
    (("sport", "sports", "athlete", "olympic", "olympics", "player", "league",
      "team", "swim", "swimmer", "swimming", "track", "championship",
      "championships", "tournament"), "stadium athlete sport"),
    (("drag", "ballroom", "nightclub", "bar", "nightlife"), "nightclub stage lights"),
    (("award", "honored", "prize", "wins", "winner", "gala"), "award trophy stage"),
    (("housing", "homeless", "shelter", "eviction", "rent"), "city apartment housing"),
    (("military", "veteran", "soldier", "army", "troops", "navy"), "military soldier flag"),
    (("book", "author", "novel", "writer", "memoir"), "books reading writing"),
    (("company", "brand", "corporate", "business", "ceo", "workplace", "employer"),
     "office business workplace"),
    (("parade", "pride festival", "pride month"), "pride parade crowd"),
)


def _keyword_hit(keyword: str, low: str) -> bool:
    """Whole-word (or whole-phrase) match, tolerant of a trailing plural 's'.

    Naive substring matching was wrong for short keywords: "bar" matched
    "Turkey BARred a cruise" and sent a cruise story to a nightclub. Word
    boundaries fix that while still catching "bars", "voters", "courts".
    """
    return re.search(rf"\b{re.escape(keyword)}s?\b", low) is not None


def topic_query(title: str) -> str:
    """Map a headline to a stock-footage concept. Empty string if no match."""
    low = title.lower()
    for keywords, visual in TOPIC_VISUALS:
        if any(_keyword_hit(kw, low) for kw in keywords):
            return visual
    return ""


def build_visual_brief(title: str, query: str) -> VisualBrief:
    """Build strict stock-footage acceptance criteria for a story.

    Stock APIs can return surprising fuzzy matches. The result metadata must
    overlap the curated visual concept, and sensitive family/child terms are
    rejected unless the story itself asks for them.
    """

    title_words = set(re.findall(r"[a-z]+", title.lower()))
    required = {
        word for word in re.findall(r"[a-z]+", query.lower())
        if len(word) > 3 and word not in _STOPWORDS
    }
    forbidden = {
        word for word in _SENSITIVE_VISUAL_TERMS
        if word not in title_words
    }
    return VisualBrief(
        query=query,
        required_terms=frozenset(required),
        forbidden_terms=frozenset(forbidden),
    )


def candidate_matches_brief(candidate: BrollCandidate, brief: VisualBrief) -> bool:
    """True when stock metadata supports the requested visual concept."""

    words = set(re.findall(r"[a-z]+", candidate.descriptor.lower()))
    if not words or words & brief.forbidden_terms:
        return False
    return bool(words & brief.required_terms)


def _url_descriptor(source_url: str) -> str:
    """Turn a descriptive stock result URL into searchable text."""

    path = urllib.parse.urlparse(source_url).path.strip("/")
    if not path:
        return ""
    slug = path.rsplit("/", 1)[-1]
    slug = re.sub(r"-?\d+$", "", slug)
    return " ".join(re.findall(r"[A-Za-z]+", slug))


# Capitalized words that make a Capitalized-Bigram an institution, place, or
# event rather than a person — "Supreme Court", "White House", "New York",
# "Trevor Project", "Pride Month".
_NON_PERSON_WORDS = {
    "court", "house", "state", "states", "city", "county", "university",
    "college", "school", "department", "project", "foundation", "campaign",
    "center", "centre", "institute", "association", "society", "church",
    "committee", "council", "board", "senate", "congress", "parliament",
    "america", "american", "pride", "month", "day", "week", "festival",
    "awards", "award", "act", "bill", "law", "york", "angeles", "francisco",
    "carolina", "virginia", "dakota", "jersey", "mexico", "hampshire",
    "island", "texas", "florida", "georgia", "ohio", "michigan", "orleans",
    "united", "national", "international", "world", "global", "supreme",
    "white", "high", "federal", "republican", "republicans", "democrat",
    "democrats", "democratic", "netflix", "disney", "target", "walmart",
    # Venues / places: "Stonewall Inn", "Castro Theatre", "Studio 54"
    "inn", "bar", "club", "theatre", "theater", "museum", "hotel", "cafe",
    "cathedral", "stadium", "arena", "park", "library", "hospital", "center",
    "district", "village", "heights", "beach", "springs", "valley", "hills",
    "college", "academy", "hall", "tower", "plaza", "square", "street",
    # Leading determiners / question words that start a headline, so
    # "The Stonewall", "This Pride", "Why Trans" don't read as a first name.
    "the", "this", "that", "these", "those", "why", "how", "what", "when",
    "who", "his", "her", "their", "our", "your", "meet", "inside", "watch",
}

_PERSON_RE = re.compile(r"\b([A-Z][a-z]{1,15})\s+([A-Z][a-z'’-]{1,20})\b")


def title_is_title_case(title: str) -> bool:
    """True when a headline capitalizes most words (Title Case).

    In Title Case every bigram looks like a person name, so capital letters
    carry no proper-noun signal. Name-extraction heuristics (here and in
    media_resolver) must only trust sentence-case headlines.
    """
    words = [w for w in re.findall(r"[A-Za-z]+", title) if len(w) > 2]
    if not words:
        return False
    capitalized = sum(1 for w in words if w[0].isupper())
    # A proper-noun-dense sentence-case headline ("Marsha P. Johnson honored
    # at New York memorial") can be mostly capitals too — what separates real
    # Title Case is the near-total absence of lowercase content words.
    lowercase_long = sum(1 for w in words if len(w) > 3 and w[0].islower())
    return capitalized / len(words) > 0.6 and lowercase_long < 2


def mentions_public_person(title: str) -> bool:
    """True if the headline looks like it's about a named public person.

    Stock libraries carry no footage of specific people, so for these stories
    the article's own hero image — which is nearly always a photo of that very
    person — beats any generic clip we could search for. The renderers use this
    to put the hero image ahead of stock b-roll in the visual ladder.

    A false positive is a safe failure: we fall back to the article's own
    image, which is relevant to the story by construction.
    """
    if title_is_title_case(title):
        return False

    for match in _PERSON_RE.finditer(title):
        first, last = match.group(1).lower(), match.group(2).lower()
        if first in _NON_PERSON_WORDS or last in _NON_PERSON_WORDS:
            continue
        return True
    return False


def _api_key() -> str:
    return os.environ.get("PEXELS_API_KEY", "")


def _pixabay_api_key() -> str:
    return os.environ.get("PIXABAY_API_KEY", "")


def search_broll(
    query: str,
    orientation: str = "landscape",
    min_width: int = 1280,
    timeout: int = 15,
    brief: VisualBrief | None = None,
) -> str | None:
    """Return the first validated Pexels video file URL, or None.

    orientation: "landscape" (roundup) or "portrait" (shorts).
    Picks the smallest video file that still meets min_width — full 4K
    downloads are a waste of CI bandwidth. When a brief is supplied,
    descriptive result metadata must support the visual concept.
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
        source_url = str(video.get("url") or "")
        descriptor = " ".join((
            _url_descriptor(source_url),
            str(video.get("alt") or ""),
            str(video.get("description") or ""),
        )).strip()
        files = video.get("video_files", [])
        candidates = [
            f for f in files
            if f.get("width", 0) >= min_width and f.get("link")
            and (f.get("file_type") or "").endswith("mp4")
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda f: f.get("width", 10**9))
        candidate = BrollCandidate(
            download_url=best["link"],
            source_url=source_url,
            descriptor=descriptor,
        )
        if brief is not None and not candidate_matches_brief(candidate, brief):
            print(
                f"[broll] rejected Pexels metadata mismatch for {query!r}: "
                f"{descriptor or 'opaque result'}",
                file=sys.stderr,
            )
            continue
        return candidate.download_url
    return None


def _pixabay_orientation(value: str) -> str:
    return "vertical" if value == "portrait" else "horizontal"


def _best_pixabay_video_url(videos: dict, min_width: int) -> str:
    """Pick the smallest usable Pixabay rendition at or above min_width."""

    candidates = []
    for rendition in videos.values():
        url = rendition.get("url")
        width = int(rendition.get("width") or 0)
        if url and width >= min_width:
            candidates.append((width, url))
    if not candidates:
        return ""
    return min(candidates, key=lambda item: item[0])[1]


def search_pixabay_broll(
    query: str,
    orientation: str = "landscape",
    min_width: int = 1280,
    timeout: int = 15,
    brief: VisualBrief | None = None,
) -> str | None:
    """Return the first validated Pixabay video URL, or None."""

    key = _pixabay_api_key()
    if not key:
        return None

    params = urllib.parse.urlencode({
        "key": key,
        "q": query,
        "video_type": "film",
        "orientation": _pixabay_orientation(orientation),
        "per_page": 5,
        "safesearch": "true",
    })
    try:
        data = json.loads(
            urllib.request.urlopen(f"{PIXABAY_SEARCH_URL}?{params}", timeout=timeout).read()
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[broll] pixabay search failed ({query!r}): {exc}", file=sys.stderr)
        return None

    for hit in data.get("hits", []):
        download_url = _best_pixabay_video_url(hit.get("videos", {}), min_width)
        if not download_url:
            continue
        source_url = str(hit.get("pageURL") or "")
        descriptor = " ".join((
            _url_descriptor(source_url),
            str(hit.get("tags") or ""),
        )).strip()
        candidate = BrollCandidate(
            download_url=download_url,
            source_url=source_url,
            descriptor=descriptor,
        )
        if brief is not None and not candidate_matches_brief(candidate, brief):
            print(
                f"[broll] rejected Pixabay metadata mismatch for {query!r}: "
                f"{descriptor or 'opaque result'}",
                file=sys.stderr,
            )
            continue
        return candidate.download_url
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
    mode: str = "any",
) -> Path | None:
    """Fetch a stock clip for a story. None on any miss.

    Raw headline words are NEVER sent to Pexels. That was the root of the
    worst mismatches: Pexels fuzzy-matches any single word, so a headline
    like "…the end of the Mother Road" returned footage of a mother playing
    with her kids under a gay-bar story. Only curated concept queries go out:

    - mode="specific": the story's subject mapped through TOPIC_VISUALS
      (library ban → bookshelves, court ruling → courthouse). Nothing else —
      renderers use this so they can prefer the article's own hero image over
      a generic clip when the subject doesn't map.
    - mode="lane": the lane term / show default only. The true last resort.
    - mode="any": specific, then lane, in one call (for callers that have no
      hero-image rung between them).
    """
    if not (_api_key() or _pixabay_api_key()):
        return None

    queries: list[str] = []
    if mode in ("specific", "any"):
        queries.append(topic_query(title))
    if mode in ("lane", "any"):
        queries.append(LANE_SEARCH_TERMS.get(lane, DEFAULT_SEARCH_TERM))
    queries = [q for q in queries if q]

    for query in queries:
        brief = build_visual_brief(title, query)
        for provider, search in (
            ("Pexels", search_broll),
            ("Pixabay", search_pixabay_broll),
        ):
            url = search(query, orientation=orientation, brief=brief)
            if url:
                got = download_broll(url, out_path)
                if got:
                    print(
                        f"[broll] fetched {provider} clip for {query!r}",
                        file=sys.stderr,
                    )
                    return got
    return None
