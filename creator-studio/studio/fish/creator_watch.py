"""Watch peer creators' latest episodes and boost overlapping FISH stories.

The show keeps an ear on a small set of peer commentary channels. Each night,
before the digest ranks stories, we look at each watched channel's most recent
upload, pull its auto-generated captions (text only — no video download), and
extract the topics they spent time on. Any story in our own RSS digest that
overlaps those topics gets a relevance boost: their signal, our stories.

Copyright posture: we never reuse their footage, audio, or words. Captions are
fetched only to *read* what topics were discussed, the same as a human watching
the episode and taking notes. Nothing from the transcript enters our scripts.

Free/local per project preference: channel discovery uses YouTube's public RSS
feed (no API key), captions come via yt-dlp, topic extraction is deterministic
keyword counting. Every network step fails soft — no signal just means no
boost, never a broken digest.

Usage (standalone report):

    python -m studio.fish.creator_watch --output creator-signals.json

Wired into the digest via `daily_digest --creator-watch`.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .broll import _STOPWORDS

# Channels the show watches. Keys are display names for the report artifact.
WATCHED_CHANNELS = {
    "Outlaws with TS Madison": "UCsOACvK3jQaqeNsWfiW_kUg",
    "Funky Dineva": "UChIkZ9tdYNG78qoFF6oWSvA",
}

# Only consider uploads from roughly the prior night — an old video's topics
# are stale signal.
MAX_VIDEO_AGE_HOURS = 36

# Scoring: each matched topic adds BOOST_PER_TOPIC to a story's relevance,
# up to MAX_BOOST total. Small on purpose — peer overlap should break ties
# and lift a mid-ranked story, not override our own editorial ranking.
# A single shared word is coincidence, not coverage: a live run showed
# one-word overlaps boosting half the digest, so a boost requires at least
# MIN_MATCHED_TOPICS distinct topics in common.
BOOST_PER_TOPIC = 0.03
MAX_BOOST = 0.09
MIN_MATCHED_TOPICS = 2

RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={cid}"

# Talk-show transcripts are conversational; the b-roll stopword list alone
# leaves too much filler ("really", "gonna", "people"). Extend it.
_CHAT_STOPWORDS = _STOPWORDS | {
    "yeah", "okay", "right", "gonna", "wanna", "gotta", "know", "like",
    "well", "look", "listen", "thing", "things", "people", "person",
    "really", "actually", "literally", "honestly", "basically", "kind",
    "sort", "little", "big", "good", "bad", "great", "whole", "every",
    "because", "though", "always", "never", "very", "much", "many",
    "them", "they", "their", "theirs", "your", "yours", "ours", "mine",
    "here", "there", "then", "than", "some", "something", "anything",
    "everything", "nothing", "someone", "everybody", "anybody", "nobody",
    "come", "came", "going", "went", "want", "wanted", "make", "made",
    "take", "took", "give", "gave", "tell", "told", "talk", "talking",
    "said", "saying", "show", "channel", "video", "subscribe", "comment",
    "comments", "today", "tonight", "yesterday", "tomorrow", "girl",
    "child", "chile", "baby", "honey", "lord", "jesus", "amen",
    "have", "back", "love", "loved", "think", "thought", "being", "been",
    "knew", "feel", "felt", "live", "life", "yall", "nbsp", "gone",
    "done", "doing", "does", "getting", "keep", "kept", "even", "ever",
    "first", "last", "next", "time", "times", "year", "years", "week",
    "money", "somebody", "everyone", "anyone", "thank", "thanks", "please",
    # Second pass from a live run: these leaked through and matched half the
    # digest, turning the boost into noise.
    "also", "other", "others", "another", "around", "should", "would",
    "could", "once", "whatever", "whenever", "story", "stories", "called",
    "believe", "believed", "ready", "hour", "hours", "morning", "weekend",
    "situation", "different", "anyway", "damn", "hell", "yes", "okay",
    "guys", "friend", "friends", "change", "changed", "play", "played",
    "start", "started", "stop", "stopped", "point", "place", "house",
    "home", "work", "working", "worked", "call", "calling", "watch",
    "watching", "heard", "hear", "seen", "sing", "singing", "song",
}


# ── channel feed ─────────────────────────────────────────────────────────────

def latest_video(channel_id: str, timeout: int = 15) -> dict | None:
    """Newest upload for a channel via its public RSS feed.

    Returns {"video_id", "title", "published"} or None if the feed is
    unreachable or the newest upload is older than MAX_VIDEO_AGE_HOURS.
    """
    url = RSS_URL.format(cid=channel_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fish-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"[creator_watch] feed fetch failed for {channel_id}: {exc}",
              file=sys.stderr)
        return None

    entry = re.search(r"<entry>(.*?)</entry>", xml, re.DOTALL)
    if not entry:
        return None
    block = entry.group(1)
    vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
    title = re.search(r"<title>([^<]*)</title>", block)
    published = re.search(r"<published>([^<]+)</published>", block)
    if not (vid and published):
        return None

    try:
        when = datetime.fromisoformat(published.group(1))
    except ValueError:
        return None
    age = datetime.now(timezone.utc) - when
    if age > timedelta(hours=MAX_VIDEO_AGE_HOURS):
        print(f"[creator_watch] newest upload for {channel_id} is "
              f"{age.total_seconds() / 3600:.0f}h old — skipping", file=sys.stderr)
        return None

    return {
        "video_id": vid.group(1),
        "title": title.group(1) if title else "",
        "published": published.group(1),
    }


# ── captions ─────────────────────────────────────────────────────────────────

def _vtt_to_text(vtt: str) -> str:
    """Flatten a VTT caption file to plain prose, deduping rolling repeats."""
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (not line or line == "WEBVTT" or "-->" in line
                or line.startswith(("Kind:", "Language:", "NOTE"))
                or line.isdigit()):
            continue
        line = re.sub(r"<[^>]+>", "", line)      # inline timing tags
        line = _html.unescape(line)              # &nbsp; etc. — not topic words
        line = line.strip()
        # Auto-captions repeat each line as the window rolls; keep first only.
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return " ".join(lines)


def fetch_transcript(video_id: str, timeout: int = 120) -> str:
    """Auto-caption text for a video via yt-dlp. "" on any failure."""
    with tempfile.TemporaryDirectory(prefix="fish_cw_") as td:
        out = Path(td) / "cap"
        cmd = [
            "yt-dlp", "--skip-download",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "en.*", "--sub-format", "vtt",
            "-o", str(out),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"[creator_watch] yt-dlp unavailable/failed: {exc}", file=sys.stderr)
            return ""
        vtts = sorted(Path(td).glob("cap*.vtt"))
        if not vtts:
            print(f"[creator_watch] no captions for {video_id}", file=sys.stderr)
            return ""
        return _vtt_to_text(vtts[0].read_text(errors="replace"))


# ── topics ───────────────────────────────────────────────────────────────────

def extract_topics(transcript: str, video_title: str = "", top_n: int = 25) -> list[str]:
    """Deterministic topic terms from a transcript + episode title.

    Title words count regardless of frequency (creators put the subject in the
    title); transcript words need to recur to register as a topic rather than
    a passing mention.
    """
    topics: dict[str, int] = {}

    def _tokens(text: str) -> list[str]:
        # Capture apostrophes INSIDE the token, then discard the whole word:
        # talk-show transcripts are wall-to-wall contractions ("don't",
        # "wasn't", "y'all") and none of them are topics. Splitting at the
        # apostrophe instead would leak stems like "didn" and "wasn".
        words = re.findall(r"[A-Za-z][A-Za-z'-]+", text.lower().replace("’", "'"))
        return [w for w in words
                if w not in _CHAT_STOPWORDS and len(w) > 3 and "'" not in w]

    for w in _tokens(video_title):
        topics[w] = topics.get(w, 0) + 5

    for w in _tokens(transcript):
        topics[w] = topics.get(w, 0) + 1

    recurring = {w: n for w, n in topics.items() if n >= 3}
    ranked = sorted(recurring, key=lambda w: recurring[w], reverse=True)
    return ranked[:top_n]


def creator_topic_signals() -> dict[str, dict]:
    """Topics from each watched channel's latest episode. Fails soft per channel."""
    signals: dict[str, dict] = {}
    for name, cid in WATCHED_CHANNELS.items():
        video = latest_video(cid)
        if not video:
            continue
        transcript = fetch_transcript(video["video_id"])
        topics = extract_topics(transcript, video_title=video["title"])
        if not topics:
            continue
        signals[name] = {**video, "topics": topics}
        print(f"[creator_watch] {name}: {video['title']!r} → "
              f"{len(topics)} topics", file=sys.stderr)
    return signals


# ── boost ────────────────────────────────────────────────────────────────────

def boost_candidates(digest: dict, signals: dict[str, dict]) -> dict:
    """Boost digest stories whose text overlaps watched creators' topics.

    Mutates and returns the digest. Each boosted story records which channel
    and topics lifted it (`creator_signal`) so the ordering stays explainable.
    """
    if not signals:
        return digest

    for item in digest.get("items", []):
        text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        story_words = set(re.findall(r"[A-Za-z][A-Za-z'-]+", text))
        best: tuple[str, list[str]] | None = None
        for channel, sig in signals.items():
            matched = [t for t in sig["topics"] if t in story_words]
            if len(matched) >= MIN_MATCHED_TOPICS and (
                    best is None or len(matched) > len(best[1])):
                best = (channel, matched)
        if best:
            channel, matched = best
            boost = min(len(matched) * BOOST_PER_TOPIC, MAX_BOOST)
            item["relevance_score"] = round(item["relevance_score"] + boost, 3)
            item["creator_signal"] = {
                "channel": channel,
                "matched_topics": matched[:6],
                "boost": boost,
            }

    digest["items"].sort(key=lambda row: row["relevance_score"], reverse=True)
    digest["creator_watch"] = {
        name: {"video_id": s["video_id"], "title": s["title"],
               "topics": s["topics"]}
        for name, s in signals.items()
    }
    return digest


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report topics from watched creators' latest episodes")
    parser.add_argument("--output", required=True, help="Signals JSON path")
    args = parser.parse_args()

    signals = creator_topic_signals()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals, indent=2) + "\n")
    print(f"Wrote signals for {len(signals)} channel(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
