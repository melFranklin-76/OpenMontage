"""Publish a FISH reel MP4 to YouTube Shorts.

Uses the YouTube Data API v3 via google-api-python-client + google-auth.
Requires a one-time OAuth flow to produce an offline refresh token; from then
on the module runs unattended in CI or scheduled jobs.

Setup (one-time, local):

    1. Create a Google Cloud project + enable YouTube Data API v3
    2. Create an OAuth 2.0 Client ID (Desktop app), download client_secret.json
    3. Save it to ~/.fish/youtube_client_secret.json
    4. Run: python -m studio.fish.youtube_publisher --auth
       - Opens a browser, prompts for consent, writes ~/.fish/youtube_token.json
    5. For CI: copy ~/.fish/youtube_token.json contents into a GitHub secret
       (YOUTUBE_TOKEN_JSON) and the workflow will write it back to disk.

Publish a reel:

    python -m studio.fish.youtube_publisher \\
      --script fish-script-rank1.json \\
      --video fish-reel-rank1.mp4 \\
      --privacy unlisted           # or "private" | "public"

The video ID + watch URL land in a JSON side-file next to the video.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Env / config paths
FISH_CONFIG_DIR = Path(os.environ.get("FISH_CONFIG_DIR", Path.home() / ".fish"))
CLIENT_SECRET_PATH = FISH_CONFIG_DIR / "youtube_client_secret.json"
TOKEN_PATH = FISH_CONFIG_DIR / "youtube_token.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# YouTube category IDs — 25 is "News & Politics"
CATEGORY_ID = "25"

BASE_TAGS = ["Shorts", "LGBT", "LGBTQ", "queer", "news", "whatsthelgbtfish"]

LANE_TAGS = {
    "gay":         ["gay", "gaynews", "pride"],
    "lesbian":     ["lesbian", "wlw", "sapphic"],
    "bisexual":    ["bisexual", "bivisibility", "bipride"],
    "Black trans": ["Black trans", "BlackTransLivesMatter", "transrights"],
    "legacy":      ["lgbthistory", "queerhistory", "stonewall"],
}


# ── OAuth ────────────────────────────────────────────────────────────────────

def _load_credentials():
    """Load or refresh cached OAuth credentials. Fails clearly if missing."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        sys.exit(
            "[youtube_publisher] Missing deps. Install:\n"
            "  pip install google-auth google-auth-oauthlib "
            "google-api-python-client"
        )

    if not TOKEN_PATH.exists():
        sys.exit(
            f"[youtube_publisher] No cached token at {TOKEN_PATH}.\n"
            "Run once locally: python -m studio.fish.youtube_publisher --auth"
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json())
        else:
            sys.exit(
                "[youtube_publisher] Cached token invalid and no refresh token."
                " Re-run --auth."
            )
    return creds


def run_auth_flow() -> None:
    """One-time interactive OAuth flow; produces YOUTUBE_TOKEN_JSON."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_SECRET_PATH.exists():
        sys.exit(
            f"[youtube_publisher] Missing client secret at {CLIENT_SECRET_PATH}.\n"
            "Download OAuth 2.0 Desktop Client credentials from Google Cloud "
            "Console and save them there."
        )

    FISH_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"[youtube_publisher] Wrote token to {TOKEN_PATH}")
    print(
        "For CI: copy this file's contents to a GitHub secret named "
        "YOUTUBE_TOKEN_JSON."
    )


def hydrate_token_from_env() -> None:
    """CI helper: write YOUTUBE_TOKEN_JSON env var to disk if set."""
    token_env = os.environ.get("YOUTUBE_TOKEN_JSON")
    if token_env and not TOKEN_PATH.exists():
        FISH_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(token_env)


# ── metadata ─────────────────────────────────────────────────────────────────

def build_metadata(script: dict, privacy: str = "unlisted") -> dict:
    lane = script.get("lane", "")
    topic = script.get("topic", "").strip() or "Today's LGBT news"
    source = script.get("source_attribution", {})
    source_name = source.get("name", "")
    source_url = source.get("url", "")

    tags = BASE_TAGS + LANE_TAGS.get(lane, [])
    # YouTube caps tag string length at 500 chars total; trim conservatively
    tags = tags[:15]

    # Title must be ≤100 chars including "#Shorts" tag
    title = f"{topic[:80]} #Shorts".strip()
    if len(title) > 100:
        title = title[:99]

    description_lines = [
        topic,
        "",
        f"Lane: {lane}" if lane else "",
        f"Source: {source_name}" if source_name else "",
        source_url,
        "",
        "From What's the LGBT, Fish? — daily LGBT news, in one minute.",
        "",
        " ".join(f"#{t}" for t in tags),
    ]
    description = "\n".join(line for line in description_lines if line is not None).strip()

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }


# ── upload ───────────────────────────────────────────────────────────────────

def upload_video(video_path: Path, metadata: dict) -> dict:
    """Upload a video file to YouTube. Returns the API response."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        sys.exit(
            "[youtube_publisher] Missing deps. Install:\n"
            "  pip install google-api-python-client"
        )

    if not video_path.exists():
        sys.exit(f"[youtube_publisher] video not found: {video_path}")

    creds = _load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=-1,        # single-shot upload for < 100MB reels
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=metadata,
        media_body=media,
    )

    print(f"[youtube_publisher] uploading {video_path} ({video_path.stat().st_size} bytes)...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  progress: {int(status.progress() * 100)}%")

    return response


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a FISH reel to YouTube Shorts")
    parser.add_argument("--auth", action="store_true", help="Run one-time OAuth setup")
    parser.add_argument("--script", help="Path to reel_script JSON (for metadata)")
    parser.add_argument("--video", help="Path to the MP4 to upload")
    parser.add_argument(
        "--privacy", default="unlisted",
        choices=["private", "unlisted", "public"],
        help="Initial privacy status (default: unlisted)",
    )
    parser.add_argument(
        "--output", default="",
        help="Where to write the upload receipt JSON (default: alongside video)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Build metadata but skip the upload — useful for CI validation",
    )
    args = parser.parse_args()

    if args.auth:
        run_auth_flow()
        return 0

    if not args.script or not args.video:
        parser.error("--script and --video are required (or use --auth)")

    hydrate_token_from_env()

    script = json.loads(Path(args.script).read_text())
    metadata = build_metadata(script, privacy=args.privacy)

    if args.dry_run:
        print("[youtube_publisher] --dry-run, metadata only:")
        print(json.dumps(metadata, indent=2))
        return 0

    video_path = Path(args.video)
    response = upload_video(video_path, metadata)

    video_id = response.get("id", "")
    receipt = {
        "video_id": video_id,
        "watch_url": f"https://youtube.com/shorts/{video_id}" if video_id else "",
        "privacy": args.privacy,
        "metadata": metadata,
        "response": {k: response.get(k) for k in ("id", "kind", "etag")},
    }

    out_path = Path(args.output) if args.output else video_path.with_suffix(".youtube.json")
    out_path.write_text(json.dumps(receipt, indent=2))

    print(f"[youtube_publisher] uploaded → {receipt['watch_url']}")
    print(f"  receipt → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
