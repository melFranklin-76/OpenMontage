"""Watch peer creators' latest episodes and boost overlapping FISH stories.

The show keeps an ear on a small set of peer commentary channels. Each night,
before the digest ranks stories, we find each watched channel's most recent
real episode, pull its auto-generated captions (text only — no video download),
and extract the topics they spent time on. Any story in our own RSS digest that
overlaps those topics gets a relevance boost: their signal, our stories.

"Most recent episode" is not the same as "most recent upload": these channels
post several times a day, the newest slot is usually a Short, and a long
upload can still be a vacation vlog rather than commentary. `pick_episode`
walks back until it finds something that is actually an episode about our beat.

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
from .filter import ACCEPT_TERMS

# Channels the show watches. Keys are display names for the report artifact.
# TS Madison runs two separate channels and they carry different material:
# "Outlaws" is the sit-down commentary show, the other is her main channel
# where she posts daily. Both are worth listening to.
WATCHED_CHANNELS = {
    "Outlaws with TS Madison": "UCsOACvK3jQaqeNsWfiW_kUg",
    "Ts Madison": "UCE81T3u_YFLIJM6xxp7YJvg",
    "Funky Dineva": "UChIkZ9tdYNG78qoFF6oWSvA",
}

# Only consider uploads from roughly the prior night — an old video's topics
# are stale signal.
MAX_VIDEO_AGE_HOURS = 36

# How far back through a channel's recent uploads to look for the episode.
MAX_VIDEOS_PER_CHANNEL = 6

# Captions cost a yt-dlp call each, so cap how many we'll pull per channel
# before accepting that tonight has no episode.
MAX_TRANSCRIPT_ATTEMPTS = 3

# A Short's captions run to a few dozen words and never survive
# extract_topics' recurrence threshold, so a thin transcript means "not the
# episode" rather than "no signal". 400 words is roughly three minutes of
# talk — under that, keep walking back.
MIN_TRANSCRIPT_WORDS = 400

# Uploads that say they're Shorts can be skipped without spending a fetch.
_SHORTS_TITLE_RE = re.compile(r"#shorts?\b", re.IGNORECASE)

# Length proves an upload is long-form, not that it is commentary on our beat.
# A live run accepted 2,388 words of holiday vlog from a watched channel and
# its filler ("sandwich", "camera", "only") lifted 19% of the digest. So an
# episode also has to touch the show's editorial vocabulary before its topics
# may move our ranking. Require recurrence: one passing mention across half an
# hour is not an episode about the beat. That vlog scored zero.
MIN_EDITORIAL_MENTIONS = 3

# Scoring: each matched topic adds BOOST_PER_TOPIC to a story's relevance,
# up to MAX_BOOST total. Small on purpose — peer overlap should break ties
# and lift a mid-ranked story, not override our own editorial ranking.
# A single shared word is coincidence, not coverage: a live run showed
# one-word overlaps boosting half the digest, so a boost requires at least
# MIN_MATCHED_TOPICS distinct topics in common.
BOOST_PER_TOPIC = 0.03
MAX_BOOST = 0.09
MIN_MATCHED_TOPICS = 2

# A topic that already runs through a big slice of tonight's digest is
# vocabulary, not signal — matching it tells us nothing about coverage. Two
# rounds of stopwords have already been spent chasing words like these; rather
# than a third, drop any topic common enough that matching it is meaningless.
# This calibrates itself: an episode genuinely about a school-board fight
# yields "school"/"board", which are rare across the digest and survive.
MAX_TOPIC_DIGEST_SHARE = 0.10

# Below this many stories, share-of-digest is arithmetic noise — one story in
# three is 33% by construction, not because the word is filler.
MIN_DIGEST_FOR_TOPIC_FILTER = 20

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

def recent_videos(channel_id: str, timeout: int = 15,
                  limit: int = MAX_VIDEOS_PER_CHANNEL) -> list[dict]:
    """Recent uploads for a channel via its public RSS feed, newest first.

    Returns up to `limit` entries published within MAX_VIDEO_AGE_HOURS, each
    {"video_id", "title", "published"}. Empty list if the feed is unreachable
    or nothing is recent enough.
    """
    url = RSS_URL.format(cid=channel_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fish-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        print(f"[creator_watch] feed fetch failed for {channel_id}: {exc}",
              file=sys.stderr)
        return []

    now = datetime.now(timezone.utc)
    videos: list[dict] = []
    for entry in re.finditer(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        block = entry.group(1)
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
        title = re.search(r"<title>([^<]*)</title>", block)
        published = re.search(r"<published>([^<]+)</published>", block)
        if not (vid and published):
            continue
        try:
            when = datetime.fromisoformat(published.group(1))
        except ValueError:
            continue
        # The feed is ordered newest-first, so the first entry outside the
        # window means every remaining one is older still.
        if now - when > timedelta(hours=MAX_VIDEO_AGE_HOURS):
            break
        videos.append({
            "video_id": vid.group(1),
            # Titles carry entities and feed extract_topics, so unescape them
            # the same way caption text is unescaped.
            "title": _html.unescape(title.group(1)) if title else "",
            "published": published.group(1),
        })
        if len(videos) >= limit:
            break

    if not videos:
        print(f"[creator_watch] no uploads for {channel_id} within "
              f"{MAX_VIDEO_AGE_HOURS}h — skipping", file=sys.stderr)
    return videos


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


# ── episode selection ────────────────────────────────────────────────────────

class _FetchBudget:
    """Stops a run from burning two-minute yt-dlp timeouts once it's clear
    yt-dlp is being blocked rather than the videos merely lacking captions.

    YouTube bot-walls datacenter IPs, which is the normal state on CI, and a
    blocked fetch is indistinguishable from "this upload has no captions".
    Scanning several uploads across several channels multiplies that cost, so
    give up after enough consecutive empties.
    """

    def __init__(self, max_consecutive_failures: int = 4):
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0

    @property
    def exhausted(self) -> bool:
        return self.consecutive_failures >= self.max_consecutive_failures

    def record(self, usable: bool) -> None:
        self.consecutive_failures = 0 if usable else self.consecutive_failures + 1


def editorial_mentions(transcript: str, title: str = "") -> int:
    """How often an episode touches the show's beat.

    Reuses the digest's own ACCEPT_TERMS so "what this show covers" has one
    definition. Counts occurrences rather than using `classify_lane`, whose
    substring test is built for headlines — across half an hour of captions a
    single stray "gay" would classify a vacation vlog as on-beat.
    """
    haystack = f"{title} {transcript}".lower()
    return sum(haystack.count(term) for term in ACCEPT_TERMS)


def pick_episode(channel_id: str, label: str = "",
                 budget: "_FetchBudget | None" = None) -> dict | None:
    """Newest recent upload that is actually an episode about our beat.

    The newest upload is usually a Short, whose handful of caption words never
    survives extract_topics' recurrence threshold — so taking it would quietly
    cost the channel its whole night of signal. And a long upload can still be
    a vacation vlog. Walk back instead, skipping self-declared Shorts, thin
    transcripts, and off-beat episodes. The transcript rides along so callers
    needn't refetch it.
    """
    budget = budget if budget is not None else _FetchBudget()
    who = label or channel_id
    attempts = 0

    for video in recent_videos(channel_id):
        if _SHORTS_TITLE_RE.search(video["title"]):
            continue
        if attempts >= MAX_TRANSCRIPT_ATTEMPTS:
            print(f"[creator_watch] {who}: no episode in the newest "
                  f"{MAX_TRANSCRIPT_ATTEMPTS} non-Short uploads", file=sys.stderr)
            break
        if budget.exhausted:
            print(f"[creator_watch] {who}: skipping — yt-dlp returned nothing "
                  f"{budget.consecutive_failures}x in a row, assuming it is "
                  f"blocked rather than that every upload lacks captions",
                  file=sys.stderr)
            break

        attempts += 1
        transcript = fetch_transcript(video["video_id"])
        words = len(transcript.split())
        if words < MIN_TRANSCRIPT_WORDS:
            budget.record(usable=False)
            print(f"[creator_watch] {who}: {video['title']!r} has {words} "
                  f"caption words (need {MIN_TRANSCRIPT_WORDS}) — not the "
                  f"episode, looking further back", file=sys.stderr)
            continue

        # Captions came back fine, so yt-dlp is healthy regardless of whether
        # this upload turns out to be on-beat.
        budget.record(usable=True)

        mentions = editorial_mentions(transcript, video["title"])
        if mentions < MIN_EDITORIAL_MENTIONS:
            print(f"[creator_watch] {who}: {video['title']!r} is off-beat "
                  f"({mentions} editorial mentions, need "
                  f"{MIN_EDITORIAL_MENTIONS}) — looking further back",
                  file=sys.stderr)
            continue

        return {**video, "transcript": transcript}

    return None


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
    budget = _FetchBudget()
    for name, cid in WATCHED_CHANNELS.items():
        episode = pick_episode(cid, label=name, budget=budget)
        if not episode:
            print(f"[creator_watch] {name}: no usable episode tonight",
                  file=sys.stderr)
            continue
        topics = extract_topics(episode["transcript"], video_title=episode["title"])
        if not topics:
            print(f"[creator_watch] {name}: {episode['title']!r} yielded no "
                  f"topics", file=sys.stderr)
            continue
        # Deliberately drop `transcript`: signals are written to the digest
        # artifact, and their words must never be persisted alongside ours.
        signals[name] = {
            "video_id": episode["video_id"],
            "title": episode["title"],
            "published": episode["published"],
            "topics": topics,
        }
        print(f"[creator_watch] {name}: {episode['title']!r} → "
              f"{len(topics)} topics", file=sys.stderr)

    print(f"[creator_watch] {len(signals)}/{len(WATCHED_CHANNELS)} channels "
          f"produced signal", file=sys.stderr)
    return signals


# ── boost ────────────────────────────────────────────────────────────────────

def _story_words(item: dict) -> set[str]:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()
    return set(re.findall(r"[A-Za-z][A-Za-z'-]+", text))


def discriminative_topics(topics: list[str], story_words: list[set[str]]) -> list[str]:
    """Drop topics too common across tonight's digest to mean anything.

    See MAX_TOPIC_DIGEST_SHARE. Returns `topics` unchanged when the digest is
    too small for share-of-digest to be meaningful.
    """
    if len(story_words) < MIN_DIGEST_FOR_TOPIC_FILTER:
        return topics
    ceiling = len(story_words) * MAX_TOPIC_DIGEST_SHARE
    return [t for t in topics
            if sum(t in words for words in story_words) <= ceiling]


def boost_candidates(digest: dict, signals: dict[str, dict]) -> dict:
    """Boost digest stories whose text overlaps watched creators' topics.

    Mutates and returns the digest. Each boosted story records which channel
    and topics lifted it (`creator_signal`) so the ordering stays explainable.
    """
    if not signals:
        return digest

    items = digest.get("items", [])
    all_story_words = [_story_words(item) for item in items]

    # Filter per channel, so one channel's filler can't mask another's signal.
    usable: dict[str, list[str]] = {}
    for channel, sig in signals.items():
        kept = discriminative_topics(sig["topics"], all_story_words)
        dropped = len(sig["topics"]) - len(kept)
        if dropped:
            print(f"[creator_watch] {channel}: dropped {dropped}/"
                  f"{len(sig['topics'])} topics as too common to be signal",
                  file=sys.stderr)
        if kept:
            usable[channel] = kept

    for item, story_words in zip(items, all_story_words):
        best: tuple[str, list[str]] | None = None
        for channel, topics in usable.items():
            matched = [t for t in topics if t in story_words]
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
               # Only surviving topics could move ranking — recording the raw
               # list would overstate a vacation episode's influence.
               "topics": usable.get(name, [])}
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
