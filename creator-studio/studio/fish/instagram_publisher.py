"""Publish top-ranked FISH vertical shorts to Instagram Reels.

Instagram setup (one-time, manual):

    1. Convert the FISH Instagram account to Business or Creator.
    2. Link it to a Facebook Page in Instagram business tools.
    3. Create a Meta Business app and add the Instagram Graph API product.
    4. Grant: instagram_basic, instagram_content_publish,
       pages_show_list, business_management.
    5. Exchange for a long-lived access token and look up the IG user ID via
       the connected Page's instagram_business_account field.
    6. Add GitHub secrets: IG_ACCESS_TOKEN and IG_USER_ID.

Instagram publishing uses public video URLs only. The nightly workflow hosts
ranked reels as GitHub Release assets, then this module tells Meta to fetch
those URLs.

Refresh token manually before expiry:

    python -m studio.fish.instagram_publisher --refresh-token

Publish a reel:

    python -m studio.fish.instagram_publisher \
      --script fish-script-rank1.json \
      --video-url https://github.com/.../fish-reel-rank1.mp4 \
      --output fish-ig-rank1.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from studio.fish.youtube_publisher import BASE_TAGS, LANE_TAGS

API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"
CAPTION_LIMIT = 2200
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 300


class InstagramPublishError(RuntimeError):
    """Raised when Instagram Graph API publishing fails."""


def _clean_hashtag(tag: str) -> str:
    tag = tag.strip().lstrip("#").replace(" ", "")
    return f"#{tag}" if tag else ""


def build_caption(script: dict[str, Any]) -> str:
    """Build an Instagram Reel caption from a reel_script JSON object."""
    lane = str(script.get("lane", "")).strip()
    topic = str(script.get("topic", "")).strip() or "Today's LGBT news"
    source = script.get("source_attribution", {}) or {}
    source_name = str(source.get("name", "")).strip()
    source_url = str(source.get("url", "")).strip()

    tags: list[str] = []
    for tag in BASE_TAGS + LANE_TAGS.get(lane, []):
        cleaned = _clean_hashtag(tag)
        if cleaned and cleaned.lower() not in {t.lower() for t in tags}:
            tags.append(cleaned)

    lines = [topic, ""]
    if source_name:
        lines.append(f"Source: {source_name}")
    if source_url:
        lines.append(source_url)
    if lane:
        lines.append(f"Lane: {lane}")
    lines.extend([
        "",
        "From What's the LGBT, Fish? — daily LGBT news, in one minute.",
        "",
        " ".join(tags),
    ])

    caption = "\n".join(line for line in lines if line is not None).strip()
    if len(caption) <= CAPTION_LIMIT:
        return caption

    suffix = "\n\n" + " ".join(tags)
    max_topic_len = max(0, CAPTION_LIMIT - len(suffix) - 3)
    return (caption[:max_topic_len].rstrip() + "..." + suffix)[:CAPTION_LIMIT]


def _request_json(method: str, url: str, params: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(params).encode("utf-8")
    if method == "GET":
        full_url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(full_url, method="GET")
    else:
        request = urllib.request.Request(url, data=encoded, method=method)
        request.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise InstagramPublishError(f"Instagram API HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise InstagramPublishError(f"Instagram API request failed: {exc}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InstagramPublishError(f"Instagram API returned non-JSON: {payload[:500]}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise InstagramPublishError(json.dumps(data["error"], indent=2))
    return data


def build_create_media_url(ig_user_id: str) -> str:
    return f"{GRAPH_BASE}/{ig_user_id}/media"


def build_container_status_url(creation_id: str) -> str:
    return f"{GRAPH_BASE}/{creation_id}"


def build_publish_url(ig_user_id: str) -> str:
    return f"{GRAPH_BASE}/{ig_user_id}/media_publish"


def create_media_container(video_url: str, caption: str, ig_user_id: str, token: str) -> str:
    response = _request_json(
        "POST",
        build_create_media_url(ig_user_id),
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token,
        },
    )
    creation_id = str(response.get("id", ""))
    if not creation_id:
        raise InstagramPublishError(f"No creation id returned: {response}")
    return creation_id


def poll_container(creation_id: str, token: str) -> dict[str, Any]:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _request_json(
            "GET",
            build_container_status_url(creation_id),
            {"fields": "status_code", "access_token": token},
        )
        status = str(last.get("status_code", ""))
        if status == "FINISHED":
            return last
        if status in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(f"Container {creation_id} status {status}: {last}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise InstagramPublishError(f"Timed out waiting for container {creation_id}: {last}")


def publish_container(creation_id: str, ig_user_id: str, token: str) -> dict[str, Any]:
    return _request_json(
        "POST",
        build_publish_url(ig_user_id),
        {"creation_id": creation_id, "access_token": token},
    )


def publish_reel(video_url: str, caption: str, ig_user_id: str, token: str) -> dict[str, Any]:
    """Create, poll, then publish an Instagram Reel."""
    creation_id = create_media_container(video_url, caption, ig_user_id, token)
    status = poll_container(creation_id, token)
    published = publish_container(creation_id, ig_user_id, token)
    media_id = str(published.get("id", ""))
    permalink = ""
    if media_id:
        media = _request_json(
            "GET",
            f"{GRAPH_BASE}/{media_id}",
            {"fields": "permalink", "access_token": token},
        )
        permalink = str(media.get("permalink", ""))
    return {
        "creation_id": creation_id,
        "status": status,
        "media_id": media_id,
        "permalink": permalink,
        "response": published,
    }


def refresh_access_token(token: str, app_secret: str = "") -> dict[str, Any]:
    params = {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": token,
        "access_token": token,
    }
    if app_secret:
        params["client_secret"] = app_secret
    return _request_json("GET", f"{GRAPH_BASE}/oauth/access_token", params)


def _env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"[instagram_publisher] Missing required env var: {name}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a FISH reel to Instagram Reels")
    parser.add_argument("--script", help="Path to reel_script JSON")
    parser.add_argument("--video-url", help="Public MP4 URL for Instagram to fetch")
    parser.add_argument("--output", default="", help="Where to write receipt JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print caption and planned calls only")
    parser.add_argument("--refresh-token", action="store_true", help="Refresh long-lived IG access token")
    args = parser.parse_args()

    token = _env_required("IG_ACCESS_TOKEN")

    if args.refresh_token:
        refreshed = refresh_access_token(token, os.environ.get("IG_APP_SECRET", ""))
        print(json.dumps(refreshed, indent=2))
        return 0

    if not args.script or not args.video_url:
        parser.error("--script and --video-url are required unless using --refresh-token")

    ig_user_id = _env_required("IG_USER_ID")
    script = json.loads(Path(args.script).read_text())
    caption = build_caption(script)

    if args.dry_run:
        planned = {
            "caption": caption,
            "caption_length": len(caption),
            "calls": [
                {"method": "POST", "url": build_create_media_url(ig_user_id)},
                {"method": "GET", "url": build_container_status_url("{creation_id}")},
                {"method": "POST", "url": build_publish_url(ig_user_id)},
            ],
            "video_url": args.video_url,
        }
        print(json.dumps(planned, indent=2))
        return 0

    receipt = publish_reel(args.video_url, caption, ig_user_id, token)
    receipt["video_url"] = args.video_url
    receipt["caption"] = caption

    out_path = Path(args.output) if args.output else Path(args.script).with_suffix(".instagram.json")
    out_path.write_text(json.dumps(receipt, indent=2))
    print(f"[instagram_publisher] uploaded → {receipt.get('permalink') or receipt.get('media_id')}")
    print(f"  receipt → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
