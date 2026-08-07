"""Resolve story-specific, reusable images with durable attribution metadata.

The resolver searches Wikimedia Commons and Openverse before renderers fall
back to article hero images or generic Pexels footage. Only public-domain,
CC0, CC BY, and CC BY-SA assets are accepted.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .broll import _NON_PERSON_WORDS as _BROLL_NON_PERSON_WORDS
from .broll import title_is_title_case

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
INTERNET_ARCHIVE_SEARCH_API = "https://archive.org/advancedsearch.php"
INTERNET_ARCHIVE_METADATA_API = "https://archive.org/metadata"
INTERNET_ARCHIVE_DOWNLOAD_BASE = "https://archive.org/download"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "OpenMontage-FISH/1.0 (licensed editorial media resolver)"

_APPROVED_LICENSES = {"cc0", "pdm", "public domain", "by", "by-sa"}
_CONTENT_WORDS = {
    "lesbian", "gay", "bisexual", "trans", "transgender", "queer", "lgbt",
    "lgbtq", "rights", "pride", "news", "says", "said", "new", "after",
    "about", "from", "with", "that", "this", "their", "they", "will",
    "story", "report", "exclusive", "breaking", "today",
    # Function words. These previously counted as match tokens, so a random
    # Commons image whose description contained "not" and "the" scored 0.67
    # against the junk subject "Not Feeling The" and shipped as the story
    # visual. Match relevance must rest on words that carry meaning.
    "the", "and", "for", "not", "was", "were", "are", "has", "have", "had",
    "been", "being", "his", "her", "him", "she", "our", "your", "its",
    "who", "why", "how", "what", "when", "where", "which", "while",
    "can", "could", "may", "might", "must", "shall", "should", "would",
    "did", "does", "doing", "done", "get", "gets", "got", "still", "even",
    "ever", "just", "only", "over", "under", "out", "off", "own", "all",
    "any", "some", "such", "more", "most", "other", "into", "onto", "than",
    "then", "them", "there", "here", "also", "very", "too", "again", "once",
    "against", "between", "before", "during", "feeling", "back",
}
_NON_PERSON_WORDS = {
    "Supreme", "Court", "White", "House", "New", "York", "Los", "Angeles",
    "United", "States", "Pride", "Month", "Stonewall", "Inn", "City",
    "State", "University", "Congress", "Senate", "National", "World",
} | {w.capitalize() for w in _BROLL_NON_PERSON_WORDS}
_PERSON_RE = re.compile(
    r"\b([A-Z][a-z]{1,20}(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z'’-]{1,24}){1,2})\b"
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class MediaAsset:
    """A reusable image and the metadata needed to credit it."""

    subject: str
    kind: str
    provider: str
    source_url: str
    download_url: str
    creator: str
    license: str
    license_url: str
    attribution: str
    rights_status: str
    match_score: float
    query: str

    def to_dict(self) -> dict:
        return asdict(self)


def _plain(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("value", "")
    return re.sub(r"\s+", " ", html.unescape(_TAG_RE.sub(" ", str(value or "")))).strip()


def _license_key(value: str) -> str:
    low = _plain(value).lower().replace("creative commons", "cc")
    if "noncommercial" in low or "no derivatives" in low or re.search(r"\b(?:nc|nd)\b", low):
        return "restricted"
    if "public domain" in low or "publicdomain" in low or low == "pdm":
        return "public domain"
    if "cc0" in low or "zero" in low:
        return "cc0"
    if "/by-sa/" in low:
        return "by-sa"
    if "/by/" in low:
        return "by"
    if "by-sa" in low or "attribution-sharealike" in low or "share alike" in low:
        return "by-sa"
    if re.search(r"\bcc[ -]?by\b", low) or low in {"by", "attribution"}:
        return "by"
    return low


def is_approved_license(value: str) -> bool:
    """Return True only for licenses that permit reuse and modification."""
    return _license_key(value) in _APPROVED_LICENSES


def extract_subjects(title: str) -> list[str]:
    """Extract likely people first, followed by one event/topic query."""
    subjects: list[str] = []
    # In a Title-Case headline every bigram looks like a name — that's how
    # "Not Feeling The" got extracted as a "person" and searched on Commons.
    # Only sentence-case headlines carry a real name signal.
    if not title_is_title_case(title):
        for match in _PERSON_RE.finditer(title):
            candidate = match.group(1).strip()
            words = candidate.split()
            if any(word in _NON_PERSON_WORDS for word in words):
                continue
            if any(word.lower().rstrip(".") in _CONTENT_WORDS for word in words):
                continue
            if candidate not in subjects:
                subjects.append(candidate)

    quoted = re.findall(r"[\"“]([^\"”]{4,80})[\"”]", title)
    for phrase in quoted:
        if phrase not in subjects:
            subjects.append(phrase)

    words = re.findall(r"[A-Za-z][A-Za-z'’-]+", title)
    topic = " ".join(
        word for word in words
        if word.lower() not in _CONTENT_WORDS and len(word) > 2
    )[:120].strip()
    if topic and topic not in subjects:
        subjects.append(topic)
    return subjects[:2]


def _tokens(value: str) -> set[str]:
    return {
        word.lower() for word in re.findall(r"[A-Za-z][A-Za-z'’-]+", value)
        if len(word) > 3 and word.lower() not in _CONTENT_WORDS
    }


def _match_score(subject: str, candidate_text: str) -> float:
    wanted = _tokens(subject)
    if not wanted:
        return 0.0
    found = _tokens(candidate_text)
    overlap = len(wanted & found)
    if overlap == len(wanted):
        return 1.0
    if overlap < min(2, len(wanted)):
        return 0.0
    return round(overlap / len(wanted), 3)


def _get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read())


# Commons hosts real public-domain FOOTAGE of newsmakers — C-SPAN floor
# speeches, White House pool video, government hearings. Motion of the actual
# person beats a still photo, so we search video first. Originals can be
# enormous; cap what we're willing to pull into a CI render.
_MAX_VIDEO_BYTES = 200_000_000


def _wikimedia_pass(gsrsearch: str, subject: str, timeout: int) -> list[MediaAsset]:
    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": gsrsearch,
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 1920,
        "format": "json",
        "origin": "*",
    })
    data = _get_json(f"{WIKIMEDIA_API}?{params}", timeout)
    assets: list[MediaAsset] = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = str(info.get("mime", ""))
        if mime.startswith("image/"):
            kind = "image"
        elif mime.startswith("video/") or mime == "application/ogg":
            kind = "video"
            if int(info.get("size") or 0) > _MAX_VIDEO_BYTES:
                continue
        else:
            continue
        meta = info.get("extmetadata") or {}
        license_name = _plain(meta.get("LicenseShortName"))
        if not is_approved_license(license_name):
            continue
        description = " ".join((
            _plain(page.get("title")),
            _plain(meta.get("ImageDescription")),
            _plain(meta.get("Categories")),
        ))
        score = _match_score(subject, description)
        if score < 0.7:
            continue
        creator = _plain(meta.get("Artist")) or "Unknown creator"
        source_url = _plain(meta.get("DescriptionUrl")) or info.get("descriptionurl", "")
        # A video's "thumburl" is a JPEG poster frame — the real file is "url".
        if kind == "video":
            download_url = info.get("url", "")
        else:
            download_url = info.get("thumburl") or info.get("url", "")
        license_url = _plain(meta.get("LicenseUrl"))
        if not source_url or not download_url:
            continue
        attribution = f"{creator} via Wikimedia Commons, {license_name}"
        assets.append(MediaAsset(
            subject=subject, kind=kind, provider="Wikimedia Commons",
            source_url=source_url, download_url=download_url, creator=creator,
            license=license_name, license_url=license_url,
            attribution=attribution, rights_status="approved_open",
            match_score=score, query=gsrsearch,
        ))
    return assets


def search_wikimedia(subject: str, timeout: int = 10) -> list[MediaAsset]:
    """Search Commons for the subject — real footage first, then stills."""
    assets: list[MediaAsset] = []
    seen: set[str] = set()
    for gsrsearch in (f"filetype:video {subject}", subject):
        try:
            found = _wikimedia_pass(gsrsearch, subject, timeout)
        except Exception as exc:  # noqa: BLE001
            print(f"[media_resolver] wikimedia pass failed ({gsrsearch!r}): {exc}",
                  file=sys.stderr)
            continue
        for asset in found:
            if asset.source_url not in seen:
                seen.add(asset.source_url)
                assets.append(asset)
    return sorted(
        assets,
        key=lambda a: (a.match_score, a.kind == "video"),
        reverse=True,
    )


def _archive_video_file(files: list[dict]) -> str:
    """Pick a reusable-size video file name from an Internet Archive item."""

    candidates = []
    for file in files:
        name = str(file.get("name") or "")
        if not name:
            continue
        fmt = str(file.get("format") or "").lower()
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in {"mp4", "m4v", "mov", "webm", "ogv", "ogg"}:
            continue
        if "h.264" not in fmt and ext not in {"mp4", "m4v", "mov", "webm", "ogv", "ogg"}:
            continue
        try:
            size = int(file.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size and size > _MAX_VIDEO_BYTES:
            continue
        candidates.append((size or _MAX_VIDEO_BYTES, name))
    if not candidates:
        return ""
    return min(candidates, key=lambda item: item[0])[1]


def search_internet_archive(subject: str, timeout: int = 10) -> list[MediaAsset]:
    """Search Internet Archive movies for reusable, subject-matching footage."""

    params = urllib.parse.urlencode([
        ("q", f'mediatype:movies AND ({subject})'),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "description"),
        ("fl[]", "subject"),
        ("fl[]", "creator"),
        ("fl[]", "licenseurl"),
        ("rows", "8"),
        ("output", "json"),
    ])
    data = _get_json(f"{INTERNET_ARCHIVE_SEARCH_API}?{params}", timeout)
    docs = data.get("response", {}).get("docs", [])
    assets: list[MediaAsset] = []

    for doc in docs:
        identifier = str(doc.get("identifier") or "")
        if not identifier:
            continue
        metadata = _get_json(
            f"{INTERNET_ARCHIVE_METADATA_API}/{urllib.parse.quote(identifier)}",
            timeout,
        )
        item_meta = metadata.get("metadata", {}) or {}
        files = metadata.get("files", []) or []

        license_name = _plain(
            item_meta.get("licenseurl")
            or doc.get("licenseurl")
            or item_meta.get("rights")
            or doc.get("rights")
        )
        if not is_approved_license(license_name):
            continue

        candidate_text = " ".join((
            _plain(doc.get("title") or item_meta.get("title")),
            _plain(doc.get("description") or item_meta.get("description")),
            _plain(doc.get("subject") or item_meta.get("subject")),
        ))
        score = _match_score(subject, candidate_text)
        if score < 0.7:
            continue

        file_name = _archive_video_file(files)
        if not file_name:
            continue

        creator = _plain(item_meta.get("creator") or doc.get("creator")) or "Unknown creator"
        source_url = f"https://archive.org/details/{identifier}"
        download_url = (
            f"{INTERNET_ARCHIVE_DOWNLOAD_BASE}/"
            f"{urllib.parse.quote(identifier)}/{urllib.parse.quote(file_name)}"
        )
        attribution = f"{creator} via Internet Archive, {license_name}"
        assets.append(MediaAsset(
            subject=subject, kind="video", provider="Internet Archive",
            source_url=source_url, download_url=download_url, creator=creator,
            license=license_name, license_url=license_name,
            attribution=attribution, rights_status="approved_open",
            match_score=score, query=subject,
        ))

    return sorted(assets, key=lambda asset: asset.match_score, reverse=True)


def search_openverse(subject: str, timeout: int = 10) -> list[MediaAsset]:
    params = urllib.parse.urlencode({
        "q": subject,
        "license": "by,by-sa,cc0,pdm",
        "license_type": "commercial,modification",
        "mature": "false",
        "page_size": 10,
    })
    data = _get_json(f"{OPENVERSE_API}?{params}", timeout)
    assets: list[MediaAsset] = []
    for item in data.get("results", []):
        license_name = _plain(item.get("license"))
        if not is_approved_license(license_name):
            continue
        candidate_text = " ".join((
            _plain(item.get("title")),
            _plain(item.get("tags")),
            _plain(item.get("creator")),
        ))
        score = _match_score(subject, candidate_text)
        if score < 0.7:
            continue
        source_url = item.get("foreign_landing_url") or item.get("detail_url") or ""
        download_url = item.get("url") or item.get("thumbnail") or ""
        if not source_url or not download_url:
            continue
        creator = _plain(item.get("creator")) or "Unknown creator"
        license_url = _plain(item.get("license_url"))
        attribution = _plain(item.get("attribution")) or (
            f"{creator} via Openverse, {license_name.upper()}"
        )
        assets.append(MediaAsset(
            subject=subject, kind="image", provider="Openverse",
            source_url=source_url, download_url=download_url, creator=creator,
            license=license_name.upper(), license_url=license_url,
            attribution=attribution, rights_status="approved_open",
            match_score=score, query=subject,
        ))
    return sorted(assets, key=lambda asset: asset.match_score, reverse=True)


def resolve_story_media(title: str, summary: str = "") -> MediaAsset | None:
    """Return the strongest exact reusable image, or None on any miss."""
    del summary  # Reserved for future entity extraction; titles are safer.
    for subject in extract_subjects(title):
        # A subject needs at least two meaningful tokens to be searchable —
        # a single word matches far too much of any image library.
        if len(_tokens(subject)) < 2:
            continue
        candidates: list[MediaAsset] = []
        for search in (search_wikimedia, search_internet_archive, search_openverse):
            try:
                found = search(subject)
                candidates.extend(found)
                if found and found[0].match_score == 1.0:
                    return found[0]
            except Exception as exc:  # noqa: BLE001
                print(f"[media_resolver] {search.__name__} failed for {subject!r}: {exc}",
                      file=sys.stderr)
        if candidates:
            return max(
                candidates,
                key=lambda asset: (asset.match_score, asset.kind == "video"),
            )
    return None


def download_media(asset: MediaAsset, out_path: Path, timeout: int = 120) -> Path | None:
    """Download a resolved asset after basic content and size validation."""
    try:
        req = urllib.request.Request(asset.download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
        if asset.kind == "video":
            allowed = ("video/", "application/ogg")
        else:
            allowed = ("image/",)
        if content_type and not content_type.startswith(allowed):
            return None
        if len(data) < (100_000 if asset.kind == "video" else 10_000):
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path
    except Exception as exc:  # noqa: BLE001
        print(f"[media_resolver] download failed: {exc}", file=sys.stderr)
        return None


def manifest_path_for(video_path: Path) -> Path:
    return video_path.with_suffix(".media.json")


def write_media_manifest(video_path: Path, assets: list[MediaAsset]) -> Path:
    """Write the attribution sidecar consumed by platform publishers."""
    path = manifest_path_for(video_path)
    unique: dict[str, MediaAsset] = {}
    for asset in assets:
        unique[asset.source_url] = asset
    payload = {
        "version": 1,
        "video": video_path.name,
        "assets": [asset.to_dict() for asset in unique.values()],
    }
    path.write_text(json.dumps(payload, indent=2))
    return path
