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

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "OpenMontage-FISH/1.0 (licensed editorial media resolver)"

_APPROVED_LICENSES = {"cc0", "pdm", "public domain", "by", "by-sa"}
_CONTENT_WORDS = {
    "lesbian", "gay", "bisexual", "trans", "transgender", "queer", "lgbt",
    "lgbtq", "rights", "pride", "news", "says", "said", "new", "after",
    "about", "from", "with", "that", "this", "their", "they", "will",
    "story", "report", "exclusive", "breaking", "today",
}
_NON_PERSON_WORDS = {
    "Supreme", "Court", "White", "House", "New", "York", "Los", "Angeles",
    "United", "States", "Pride", "Month", "Stonewall", "Inn", "City",
    "State", "University", "Congress", "Senate", "National", "World",
}
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
    for match in _PERSON_RE.finditer(title):
        candidate = match.group(1).strip()
        words = candidate.split()
        if any(word in _NON_PERSON_WORDS for word in words):
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
        if len(word) > 2 and word.lower() not in _CONTENT_WORDS
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


def search_wikimedia(subject: str, timeout: int = 10) -> list[MediaAsset]:
    params = urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": subject,
        "gsrnamespace": 6,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 1920,
        "format": "json",
        "origin": "*",
    })
    data = _get_json(f"{WIKIMEDIA_API}?{params}", timeout)
    assets: list[MediaAsset] = []
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        if not str(info.get("mime", "")).startswith("image/"):
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
        if score < 0.5:
            continue
        creator = _plain(meta.get("Artist")) or "Unknown creator"
        source_url = _plain(meta.get("DescriptionUrl")) or info.get("descriptionurl", "")
        download_url = info.get("thumburl") or info.get("url", "")
        license_url = _plain(meta.get("LicenseUrl"))
        if not source_url or not download_url:
            continue
        attribution = f"{creator} via Wikimedia Commons, {license_name}"
        assets.append(MediaAsset(
            subject=subject, kind="image", provider="Wikimedia Commons",
            source_url=source_url, download_url=download_url, creator=creator,
            license=license_name, license_url=license_url,
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
        if score < 0.5:
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
        candidates: list[MediaAsset] = []
        for search in (search_wikimedia, search_openverse):
            try:
                found = search(subject)
                candidates.extend(found)
                if found and found[0].match_score == 1.0:
                    return found[0]
            except Exception as exc:  # noqa: BLE001
                print(f"[media_resolver] {search.__name__} failed for {subject!r}: {exc}",
                      file=sys.stderr)
        if candidates:
            return max(candidates, key=lambda asset: asset.match_score)
    return None


def download_media(asset: MediaAsset, out_path: Path, timeout: int = 30) -> Path | None:
    """Download a resolved image after basic content and size validation."""
    try:
        req = urllib.request.Request(asset.download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
        if content_type and not content_type.startswith("image/"):
            return None
        if len(data) < 10_000:
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
