"""Social research intake for What's the LGBT, Fish?

Supplements the RSS pipeline with social signal from Reddit, X/Twitter,
Hacker News, and Exa web search via two tools installed on this machine:

  - last30days-skill  (~/.claude/skills/last30days/)
    Runs a multi-source social research pass and returns a synthesised brief
    scored by real human engagement (upvotes, likes, retweets).

  - Agent-Reach  (~/.agent-reach-venv/bin/agent-reach)
    Direct platform access: Reddit public JSON, twitter-cli, Exa search,
    YouTube transcripts, RSS — zero API fees for Reddit/HN/Exa.

Both tools produce free-text output that this module parses into the same
normalised story dict that daily_digest.py already consumes:

    {title, source, url, published_at, summary}

Usage (CLI):
    python -m studio.fish.social_research --topic "LGBT news today"
    python -m studio.fish.social_research --topic "LGBT news" --source reddit
    python -m studio.fish.social_research --output stories.json

Integration with daily_digest:
    from .social_research import fetch_social_stories
    items = fetch_social_stories(topic="LGBT news this week")
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

# ── constants ────────────────────────────────────────────────────────────────

AGENT_REACH_BIN = Path.home() / ".agent-reach-venv" / "bin" / "agent-reach"
LAST30_SKILL_DIR = Path.home() / ".claude" / "skills" / "last30days"

DEFAULT_TOPIC = "LGBT LGBTQ gay lesbian bisexual transgender news"

# Subreddits with consistent LGBT news signal
LGBT_SUBREDDITS = [
    "lgbt",
    "gaynews",
    "LGBTnews",
    "ainbow",          # r/ainbow — large general LGBT community
    "transgender",
    "bisexual",
    "BlackLGBT",
    "latebloomerlesbians",
]

_TODAY = date.today().isoformat()

Source = Literal["reddit", "web", "all"]


# ── normalisation helpers ─────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    """Strip markdown artefacts and excessive whitespace."""
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)   # bold/italic
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)    # markdown links
    text = re.sub(r"https?://\S+", "", text)                  # bare URLs
    return " ".join(text.split()).strip()


def _truncate(text: str, words: int = 60) -> str:
    parts = text.split()
    if len(parts) <= words:
        return text
    return " ".join(parts[:words]) + "..."


def _make_story(title: str, summary: str, source: str, url: str = "") -> dict:
    return {
        "title": _clean(title)[:200],
        "summary": _truncate(_clean(summary)),
        "source": source,
        "url": url,
        "published_at": _now_iso(),
    }


# ── Reddit via Agent-Reach ───────────────────────────────────────────────────

def _agent_reach_available() -> bool:
    return AGENT_REACH_BIN.exists()


def fetch_reddit_stories(
    subreddits: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Pull hot posts from LGBT subreddits via Reddit RSS feeds.

    Reddit 403-blocks the public .json endpoints for non-browser clients,
    but the .rss feeds remain open — so we parse those with feedparser.
    """
    import time
    import urllib.error
    import urllib.request

    import feedparser

    if subreddits is None:
        subreddits = LGBT_SUBREDDITS

    stories: list[dict] = []
    headers = {"User-Agent": "fish-pipeline/1.0 (LGBT news digest)"}

    def _get(url: str) -> bytes:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()

    for i, sub in enumerate(subreddits):
        if i:
            time.sleep(3)  # Reddit rate-limits rapid unauthenticated requests
        url = f"https://www.reddit.com/r/{sub}/hot.rss?limit={limit}"
        try:
            try:
                raw = _get(url)
            except urllib.error.HTTPError as exc:
                if exc.code != 429:
                    raise
                time.sleep(20)  # back off once, then retry
                raw = _get(url)
            feed = feedparser.parse(raw)
            if feed.bozo and not feed.entries:
                raise RuntimeError(feed.get("bozo_exception", "empty feed"))
            for entry in feed.entries[:limit]:
                title = (entry.get("title") or "").strip()
                if not title:
                    continue
                summary_html = entry.get("summary", "") or ""
                summary = re.sub(r"<[^>]+>", " ", summary_html)
                stories.append(_make_story(
                    title=title,
                    summary=summary[:300] or f"r/{sub} hot post",
                    source=f"r/{sub}",
                    url=entry.get("link", ""),
                ))
        except Exception as exc:  # noqa: BLE001
            print(f"[social_research] reddit r/{sub} failed: {exc}", file=sys.stderr)

    return stories


def fetch_web_stories(topic: str = DEFAULT_TOPIC, limit: int = 10) -> list[dict]:
    """Search news via Google News RSS — free, no API key, no auth."""
    import urllib.parse
    import urllib.request

    import feedparser

    query = urllib.parse.quote(topic)
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fish-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            feed = feedparser.parse(resp.read())
        stories = []
        for entry in feed.entries[:limit]:
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            outlet = ""
            if " - " in title:  # Google News appends "Title - Outlet"
                title, outlet = title.rsplit(" - ", 1)
            summary = re.sub(r"<[^>]+>", " ", entry.get("summary", "") or "")
            stories.append(_make_story(
                title=title,
                summary=summary[:300] or title,
                source=outlet or "Google News",
                url=entry.get("link", ""),
            ))
        return stories
    except Exception as exc:  # noqa: BLE001
        print(f"[social_research] Google News search failed: {exc}", file=sys.stderr)
        return []


# ── Twitter/X via twitter-cli ────────────────────────────────────────────────

def fetch_twitter_stories(
    query: str = "LGBT OR LGBTQ news -is:retweet lang:en",
    limit: int = 10,
) -> list[dict]:
    """Search recent tweets via twitter-cli (requires browser login via OpenCLI)."""
    twitter_cli = Path.home() / ".agent-reach-venv" / "bin" / "twitter"
    if not twitter_cli.exists():
        # Try system PATH
        import shutil
        if not shutil.which("twitter"):
            print("[social_research] twitter-cli not available, skipping", file=sys.stderr)
            return []
        twitter_bin = "twitter"
    else:
        twitter_bin = str(twitter_cli)

    try:
        result = subprocess.run(
            [twitter_bin, "search", query, "--limit", str(limit), "--json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        tweets = json.loads(result.stdout)
        stories = []
        for t in tweets:
            text = t.get("text") or t.get("full_text") or ""
            url = t.get("url") or t.get("link") or ""
            author = t.get("author") or t.get("username") or "X/Twitter"
            if not text or len(text) < 20:
                continue
            stories.append(_make_story(
                title=text[:120],
                summary=text,
                source=f"@{author}" if not author.startswith("@") else author,
                url=url,
            ))
        return stories

    except Exception as exc:  # noqa: BLE001
        print(f"[social_research] twitter search failed: {exc}", file=sys.stderr)
        return []


# ── Hacker News via public API ───────────────────────────────────────────────

def fetch_hn_stories(query: str = "LGBT gay lesbian bisexual transgender", limit: int = 5) -> list[dict]:
    """Search Hacker News via Algolia public API — zero auth, zero cost."""
    import urllib.request
    import urllib.parse

    url = (
        "https://hn.algolia.com/api/v1/search?"
        + urllib.parse.urlencode({"query": query, "tags": "story", "hitsPerPage": limit})
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        stories = []
        for hit in data.get("hits", []):
            title = hit.get("title") or ""
            story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            points = hit.get("points") or 0
            if not title:
                continue
            stories.append(_make_story(
                title=title,
                summary=f"Hacker News — {points} points",
                source="Hacker News",
                url=story_url,
            ))
        return stories
    except Exception as exc:  # noqa: BLE001
        print(f"[social_research] HN search failed: {exc}", file=sys.stderr)
        return []


# ── main public interface ─────────────────────────────────────────────────────

def fetch_social_stories(
    topic: str = DEFAULT_TOPIC,
    source: Source = "all",
    reddit_limit: int = 8,
    web_limit: int = 10,
    twitter_limit: int = 10,
    hn_limit: int = 5,
) -> list[dict]:
    """Return normalised story dicts from social sources, ready for the FISH filter.

    Drop-in replacement / supplement for fetch_live_stories() in intake.py.

    Args:
        topic:          Search query for web/Twitter/HN sources.
        source:         "reddit" | "web" | "all"
        reddit_limit:   Max posts per subreddit.
        web_limit:      Max Exa web results.
        twitter_limit:  Max tweets.
        hn_limit:       Max HN stories.

    Returns:
        List of story dicts: {title, summary, source, url, published_at}
    """
    stories: list[dict] = []

    if source in ("reddit", "all"):
        print("[social_research] fetching Reddit...", file=sys.stderr)
        stories.extend(fetch_reddit_stories(limit=reddit_limit))

    if source in ("web", "all"):
        print("[social_research] fetching web (Exa)...", file=sys.stderr)
        stories.extend(fetch_web_stories(topic=topic, limit=web_limit))

    if source == "all":
        print("[social_research] fetching Hacker News...", file=sys.stderr)
        stories.extend(fetch_hn_stories(query=topic, limit=hn_limit))

    if source == "all":
        print("[social_research] fetching Twitter/X...", file=sys.stderr)
        stories.extend(fetch_twitter_stories(limit=twitter_limit))

    # Deduplicate by URL, preserving order
    seen: set[str] = set()
    unique: list[dict] = []
    for s in stories:
        key = s["url"] or s["title"]
        if key not in seen:
            seen.add(key)
            unique.append(s)

    print(f"[social_research] {len(unique)} unique social stories fetched", file=sys.stderr)
    return unique


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch LGBT news from social sources for the FISH pipeline"
    )
    parser.add_argument(
        "--topic",
        default=DEFAULT_TOPIC,
        help="Search query for web/Twitter/HN (default: %(default)r)",
    )
    parser.add_argument(
        "--source",
        choices=["reddit", "web", "all"],
        default="all",
        help="Which social sources to pull from (default: all)",
    )
    parser.add_argument(
        "--output",
        help="Write normalised stories JSON to this path (default: stdout)",
    )
    parser.add_argument(
        "--reddit-limit", type=int, default=8,
        help="Max posts per subreddit (default: 8)",
    )
    parser.add_argument(
        "--web-limit", type=int, default=10,
        help="Max Exa web results (default: 10)",
    )
    args = parser.parse_args()

    stories = fetch_social_stories(
        topic=args.topic,
        source=args.source,
        reddit_limit=args.reddit_limit,
        web_limit=args.web_limit,
    )

    out = json.dumps(stories, indent=2)
    if args.output:
        Path(args.output).write_text(out)
        print(f"Wrote {len(stories)} stories to {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
