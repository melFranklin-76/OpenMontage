"""Watch peer creators' latest episodes and let overlapping stories lead the show.

The show keeps an ear on a set of peer commentary channels. Each night,
before the digest ranks stories, we find each watched channel's most recent
real episode, pull its auto-generated captions (text only — no video download),
and extract the topics they spent time on. Stories in our own RSS digest that
overlap those topics become tonight's agenda: they rank above RSS-only items.
We still never reuse their footage, audio, or words.

"Most recent episode" is not the same as "most recent upload": these channels
post several times a day, the newest slot is usually a Short, and a long
upload can still be a vacation vlog rather than commentary. `pick_episode`
walks back until it finds something that is actually an episode about our beat.

Copyright posture: we never reuse their footage, audio, or words. Captions are
fetched only to *read* what topics were discussed, the same as a human watching
the episode and taking notes. Nothing from the transcript enters our scripts.

Channel discovery prefers the YouTube Data API (`YOUTUBE_API_KEY`) and falls
back to the public RSS feed when no key is set. The key is not a nicety: YouTube
404s the RSS feed for datacenter IPs, so on CI the API is the only path that
works. Captions come via yt-dlp where it is allowed, and where it is not the
episode's own description stands in. Topic extraction is deterministic keyword
counting. Every network step fails soft — no signal just means no boost, never
a broken digest.

Usage (standalone report):

    python -m studio.fish.creator_watch --output creator-signals.json

Wired into the digest via `daily_digest --creator-watch`.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .broll import _STOPWORDS
from .filter import ACCEPT_TERMS
from .story_memory import recency_sort_key

# Channels the show watches. Keys are display names for the report artifact.
# TS Madison runs two separate channels and they carry different material:
# "Outlaws" is the sit-down commentary show, the other is her main channel
# where she posts daily. Both are worth listening to.
WATCHED_CHANNELS = {
    "Outlaws with TS Madison": "UCsOACvK3jQaqeNsWfiW_kUg",
    "Ts Madison": "UCE81T3u_YFLIJM6xxp7YJvg",
    "Funky Dineva": "UChIkZ9tdYNG78qoFF6oWSvA",
    "Armon Wiggins": "UCl8dvxZaiUtttyDBgIujocw",
    "Thai Rivera": "UCpzSy79UDdn0i-uVGOPyTLQ",
    "Amir Odom": "UCu28JGd1UDoQRlZZtG5Qrcw",
}

# Freshness window. This used to be 36h, which silently assumed every watched
# channel posts nightly. Funky Dineva goes live ~5 nights a week (sometimes a
# morning show too), so a Tuesday episode was already invisible by Thursday
# and the channel contributed nothing on the nights between uploads. The
# window now only has to answer "is this still current?" — not re-reading an
# episode we already mined is the state store's job (see `load_state`).
# 120h covers a mid-week miss plus a weekend gap without letting week-old
# topics keep steering the digest.
MAX_VIDEO_AGE_HOURS = 120

# How long a mined episode keeps contributing once it has aired. Deliberately
# longer than MAX_VIDEO_AGE_HOURS, because the two answer different questions:
# that one is "is this upload new enough to read tonight?", this one is "is this
# channel still current?". Discovery only has to catch an upload shortly after
# it lands, since we run nightly — but memory has to span the channel's quiet
# stretch, or a show that isn't daily goes silent between airings.
#
# Measured worst gaps between non-Short uploads (Sept 2026): Outlaws 168h,
# Armon Wiggins 144h, Amir Odom 121h, Funky Dineva 120h. Four of six exceeded
# the old 120h expiry, so they were losing their episode before the next one
# aired. 14 days clears the observed worst case with headroom while still
# dropping a channel that has genuinely stopped posting.
MAX_REMEMBERED_AGE_HOURS = 336

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

# Reported per episode, no longer a gate. It used to be one: a live run accepted
# 2,388 words of holiday vlog whose filler ("sandwich", "camera", "only") lifted
# 19% of the digest, so an episode had to use the show's own vocabulary before
# its topics could move our ranking. But that test asks the wrong question. The
# premise of watching these channels is *who* is talking, not which words they
# use: they are Black LGBTQ commentators, so whatever they are covering already
# is the conversation this show is part of, whether or not the word "gay"
# appears. Requiring the vocabulary silently threw away every episode about a
# court case, an election, or a celebrity — which is most of what they post.
#
# What still protects against that vlog is topic-agnostic and downstream:
# MIN_MATCHED_TOPICS needs two distinct overlaps before anything moves, and
# MAX_TOPIC_DIGEST_SHARE drops any topic common enough across the digest to be
# vocabulary rather than signal. Filler loses there without a subject test.
MIN_EDITORIAL_MENTIONS = 3

# Where mined topics are remembered between nightly runs, so an episode is
# read once and then reused while it stays current. CI is ephemeral — this
# path must be restored/saved by the workflow (actions/cache) or every run
# starts cold and re-fetches captions it already has.
DEFAULT_STATE_PATH = Path("creator-studio/out/fish/creator_watch_state.json")

# Scoring: each matched topic adds BOOST_PER_TOPIC to a story's relevance,
# up to MAX_BOOST total. That still breaks ties among room stories.
# Ranking itself is agenda-first: any story that overlaps enough creator
# topics sorts above RSS-only items, because option C is "the room decides
# what we talk about," not "nudge a mid-ranked headline."
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

# YouTube serves that RSS feed to browsers but answers 404 for datacenter IPs,
# which is every CI runner. A live run had all six channels fail this way, so
# the whole feature was silently dead in production while working fine locally.
# The Data API answers from anywhere, so prefer it whenever a key is configured
# and keep RSS as the zero-config local path. Listing one channel's uploads
# costs 1 unit against a 10,000/day free quota.
API_UPLOADS_URL = (
    "https://www.googleapis.com/youtube/v3/playlistItems"
    "?part=snippet&maxResults={limit}&playlistId={playlist}&key={key}"
)
API_KEY_ENV = "YOUTUBE_API_KEY"

# The Data API cannot hand us these channels' captions — Google only allows
# caption download for videos you own — and yt-dlp is bot-walled on CI. So on CI
# the only readable text is the episode's own title and description. That is far
# thinner than half an hour of talk, so it gets its own length floor: enough
# prose to mine topics from, which a one-line Short blurb is not.
MIN_DESCRIPTION_WORDS = 20

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

def uploads_playlist_id(channel_id: str) -> str:
    """A channel's uploads playlist id: the channel id with `UC` swapped for `UU`.

    Saves a `channels.list` round trip (and its quota unit) per channel.
    """
    return f"UU{channel_id[2:]}" if channel_id.startswith("UC") else channel_id


def _within_window(videos: list[dict], limit: int,
                   now: datetime | None = None) -> list[dict]:
    """Trim a newest-first upload list to the freshness window.

    Shared by both feed paths so the API and RSS can never disagree about what
    counts as current.
    """
    now = now or datetime.now(timezone.utc)
    kept: list[dict] = []
    for video in videos:
        try:
            when = datetime.fromisoformat(
                str(video.get("published", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        # Newest-first, so the first entry outside the window means every
        # remaining one is older still.
        if now - when > timedelta(hours=MAX_VIDEO_AGE_HOURS):
            break
        kept.append(video)
        if len(kept) >= limit:
            break
    return kept


def _api_error_reason(exc: "urllib.error.HTTPError") -> str:
    """The human-readable cause out of a Google API error body.

    Best effort: a failure to explain a failure must not itself raise.
    """
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return "no detail in response body"
    error = body.get("error") or {}
    message = error.get("message") or ""
    reasons = [
        d.get("reason") for d in (error.get("errors") or []) if d.get("reason")
    ]
    if message and reasons:
        return f"{message} (reason: {', '.join(reasons)})"
    return message or "no detail in response body"


def _videos_via_api(channel_id: str, key: str, timeout: int,
                    limit: int) -> list[dict] | None:
    """Recent uploads via the YouTube Data API, newest first.

    Returns None — not [] — when the call fails, so the caller can tell "API
    unusable, try RSS" apart from "API worked and this channel is quiet".
    """
    url = API_UPLOADS_URL.format(
        limit=limit, playlist=uploads_playlist_id(channel_id), key=key)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fish-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        # Google puts the real cause in the response body — "API key not valid"
        # and "YouTube Data API v3 has not been used in project N" both arrive
        # as a bare 400/403. Logging only the status sends whoever reads this
        # hunting, so surface the message itself.
        print(f"[creator_watch] Data API failed for {channel_id}: "
              f"{exc} — {_api_error_reason(exc)}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[creator_watch] Data API failed for {channel_id}: {exc}",
              file=sys.stderr)
        return None

    videos: list[dict] = []
    for item in payload.get("items", []):
        snippet = item.get("snippet") or {}
        vid = (snippet.get("resourceId") or {}).get("videoId")
        published = snippet.get("publishedAt")
        if not (vid and published):
            continue
        videos.append({
            "video_id": vid,
            "title": snippet.get("title", ""),
            "published": published,
            # The reason the API path is worth having beyond reachability:
            # captions are unavailable for channels we don't own, so the
            # description is the only prose we get on CI.
            "description": snippet.get("description", ""),
        })
    return videos


def _videos_via_rss(channel_id: str, timeout: int) -> list[dict]:
    """Recent uploads via the channel's public RSS feed, newest first.

    No API key needed, which is why it stays as the local path — but YouTube
    404s this endpoint for datacenter IPs, so it cannot be relied on in CI.
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

    videos: list[dict] = []
    for entry in re.finditer(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        block = entry.group(1)
        vid = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", block)
        title = re.search(r"<title>([^<]*)</title>", block)
        published = re.search(r"<published>([^<]+)</published>", block)
        blurb = re.search(r"<media:description>(.*?)</media:description>",
                          block, re.DOTALL)
        if not (vid and published):
            continue
        videos.append({
            "video_id": vid.group(1),
            # Titles carry entities and feed extract_topics, so unescape them
            # the same way caption text is unescaped.
            "title": _html.unescape(title.group(1)) if title else "",
            "published": published.group(1),
            "description": _html.unescape(blurb.group(1)) if blurb else "",
        })
    return videos


def recent_videos(channel_id: str, timeout: int = 15,
                  limit: int = MAX_VIDEOS_PER_CHANNEL) -> list[dict]:
    """Recent uploads for a channel, newest first.

    Prefers the Data API when YOUTUBE_API_KEY is set — the only path that works
    from CI — and falls back to the public RSS feed otherwise. Returns up to
    `limit` entries published within MAX_VIDEO_AGE_HOURS, each {"video_id",
    "title", "published", "description"}. Empty list if neither source has
    anything current.
    """
    key = os.environ.get(API_KEY_ENV, "").strip()
    videos = _videos_via_api(channel_id, key, timeout, limit) if key else None
    if videos is None:
        videos = _videos_via_rss(channel_id, timeout)

    videos = _within_window(videos, limit)
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


# ── state ────────────────────────────────────────────────────────────────────

def load_state(path: Path | None = None) -> dict[str, dict]:
    """Topics mined on previous nights, keyed by channel id.

    Each value is {"video_id", "title", "published", "topics"}. Missing or
    unreadable state is not an error — it just means every channel is read
    fresh tonight.
    """
    path = path or DEFAULT_STATE_PATH
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        print(f"[creator_watch] ignoring unreadable state at {path}: {exc}",
              file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict[str, dict], path: Path | None = None) -> None:
    """Persist mined topics. Failure is logged, never fatal — the digest still
    ships, it just re-reads captions next run."""
    path = Path(path or DEFAULT_STATE_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"[creator_watch] could not write state to {path}: {exc}",
              file=sys.stderr)


def prune_state(state: dict[str, dict], now: datetime | None = None) -> dict[str, dict]:
    """Drop remembered episodes from channels that have gone quiet for good.

    The horizon is MAX_REMEMBERED_AGE_HOURS, not the discovery window: a show
    that airs weekly must keep contributing on the nights between airings, and
    only a channel that has actually stopped posting should fall out. Entries
    with an unparseable timestamp are dropped too — better to re-read the channel
    than to trust a date we can't check.
    """
    now = now or datetime.now(timezone.utc)
    kept: dict[str, dict] = {}
    for cid, entry in state.items():
        try:
            when = datetime.fromisoformat(
                str(entry["published"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if now - when <= timedelta(hours=MAX_REMEMBERED_AGE_HOURS):
            kept[cid] = entry
    return kept


def newest_candidate_id(videos: list[dict]) -> str | None:
    """Id of the newest upload worth spending a caption fetch on.

    Shorts are excluded because `pick_episode` would skip them anyway. Used to
    decide whether anything has actually appeared since the last run: if the
    answer is the episode already in state, there is nothing new to fetch.
    """
    for video in videos:
        if not _SHORTS_TITLE_RE.search(video["title"]):
            return video["video_id"]
    return None


def editorial_mentions(transcript: str, title: str = "") -> int:
    """How often an episode touches the show's beat. Reported, not enforced.

    Reuses the digest's own ACCEPT_TERMS so "what this show covers" has one
    definition. Counts occurrences rather than using `classify_lane`, whose
    substring test is built for headlines — across half an hour of captions a
    single stray "gay" would classify a vacation vlog as on-beat.

    Logged per episode so the nightly output still shows whether the room was on
    queer news specifically. See MIN_EDITORIAL_MENTIONS for why it stopped being
    a gate.
    """
    haystack = f"{title} {transcript}".lower()
    return sum(haystack.count(term) for term in ACCEPT_TERMS)


def pick_episode(channel_id: str, label: str = "",
                 budget: "_FetchBudget | None" = None,
                 videos: list[dict] | None = None) -> dict | None:
    """Newest recent upload that is actually an episode about our beat.

    The newest upload is usually a Short, whose handful of caption words never
    survives extract_topics' recurrence threshold — so taking it would quietly
    cost the channel its whole night of signal. And a long upload can still be
    a vacation vlog. Walk back instead, skipping self-declared Shorts, thin
    transcripts, and off-beat episodes. The transcript rides along so callers
    needn't refetch it.

    `videos` lets a caller that has already read the channel's feed pass it in
    rather than paying for a second request.
    """
    budget = budget if budget is not None else _FetchBudget()
    who = label or channel_id
    attempts = 0

    for video in (recent_videos(channel_id) if videos is None else videos):
        if _SHORTS_TITLE_RE.search(video["title"]):
            continue
        if attempts >= MAX_TRANSCRIPT_ATTEMPTS:
            print(f"[creator_watch] {who}: no episode in the newest "
                  f"{MAX_TRANSCRIPT_ATTEMPTS} non-Short uploads", file=sys.stderr)
            break
        attempts += 1

        # Once yt-dlp has come back empty enough times it is blocked, not
        # unlucky. Stop paying its two-minute timeout, but keep walking: the
        # description path below needs no fetch and still yields topics.
        if budget.exhausted:
            transcript = ""
        else:
            transcript = fetch_transcript(video["video_id"])

        words = len(transcript.split())
        if words >= MIN_TRANSCRIPT_WORDS:
            budget.record(usable=True)
            print(f"[creator_watch] {who}: {video['title']!r} "
                  f"({words} caption words, "
                  f"{editorial_mentions(transcript, video['title'])} on-beat "
                  f"mentions)", file=sys.stderr)
            return {**video, "transcript": transcript}

        budget.record(usable=False)

        # No usable captions — the normal state on CI. Fall back to the prose
        # the Data API does give us, which is the episode's own description.
        blurb = _clean_description(video.get("description", ""))
        if len(blurb.split()) < MIN_DESCRIPTION_WORDS:
            print(f"[creator_watch] {who}: {video['title']!r} has {words} "
                  f"caption words (need {MIN_TRANSCRIPT_WORDS}) and too thin a "
                  f"description — not the episode, looking further back",
                  file=sys.stderr)
            continue

        print(f"[creator_watch] {who}: no captions for {video['title']!r} — "
              f"reading its description instead "
              f"({editorial_mentions(blurb, video['title'])} on-beat mentions)",
              file=sys.stderr)
        return {**video, "transcript": ""}

    return None


# ── topics ───────────────────────────────────────────────────────────────────

_DESC_LINK_RE = re.compile(r"https?://\S+|www\.\S+|\S+@\S+\.\S+")

# Descriptions are half promo: link blocks, socials, merch, business email, fair
# use boilerplate. None of that is a topic, and unlike caption filler it cannot
# be filtered by recurrence, because a description says everything exactly once.
_DESC_NOISE = {
    "patreon", "cashapp", "paypal", "venmo", "merch", "merchandise",
    "sponsor", "sponsored", "affiliate", "discount", "promo", "coupon",
    "instagram", "twitter", "tiktok", "facebook", "threads", "snapchat",
    "twitch", "onlyfans", "linktree", "https", "http",
    "business", "inquiries", "inquiry", "booking", "bookings", "email",
    "gmail", "contact", "follow", "following", "share", "likes",
    "notification", "notifications", "membership", "member", "members",
    "join", "donate", "donation", "support", "supporters", "copyright",
    "disclaimer", "usage", "purposes", "educational", "opinion", "opinions",
    "entertainment", "advice", "podcast", "episode", "stream", "streaming",
    "livestream", "footage", "welcome", "hosted", "presented",
    # "video" is already a chat stopword; descriptions use the plural.
    "videos", "perks",
}
# Residue like "iheartpodcasts" or a sponsor handle survives this list, and that
# is fine — it appears once, in one channel, and matches no headline. Genuinely
# ambiguous words ("media", "access") are left in too: MAX_TOPIC_DIGEST_SHARE
# drops them when they run through the digest and keeps them when they don't,
# which is a better test than guessing here.


def _clean_description(description: str) -> str:
    """Strip the promo scaffolding, leaving whatever prose is actually topical.

    Drops any line carrying a URL or email, or opening with a hashtag/handle —
    that is where descriptions keep their link trees, socials, and booking
    contacts. Dropping the whole line matters: a domain like "example.com"
    tokenizes into words that would otherwise read as topics.
    """
    lines = []
    for raw in description.splitlines():
        line = raw.strip()
        if not line or _DESC_LINK_RE.search(line) or line.startswith(("#", "@")):
            continue
        lines.append(line)
    return " ".join(lines)


def extract_topics(transcript: str, video_title: str = "", top_n: int = 25,
                   description: str = "") -> list[str]:
    """Deterministic topic terms from an episode's title, captions, description.

    The three sources are weighted by how deliberate they are. Title words count
    regardless of frequency (creators put the subject in the title). Transcript
    words must recur to register as a topic rather than a passing mention.
    Description words sit between: written rather than spoken, so one mention is
    meaningful — but promo-heavy, so it is cleaned and denoised first.
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

    # Weight 3 clears the recurrence threshold on a single mention, which is the
    # point: when captions are blocked this is the only body text there is.
    for w in _tokens(_clean_description(description)):
        if w in _DESC_NOISE:
            continue
        topics[w] = topics.get(w, 0) + 3

    for w in _tokens(transcript):
        topics[w] = topics.get(w, 0) + 1

    recurring = {w: n for w, n in topics.items() if n >= 3}
    ranked = sorted(recurring, key=lambda w: recurring[w], reverse=True)
    return ranked[:top_n]


def creator_topic_signals(state_path: Path | None = None) -> dict[str, dict]:
    """Topics from each watched channel's current episode. Fails soft per channel.

    An episode is mined once and then reused until the channel posts something
    newer, so a show that isn't daily keeps contributing on the nights between
    airings — up to MAX_REMEMBERED_AGE_HOURS, after which the channel counts as
    dormant. Reuse also means no fetch, which keeps yt-dlp exposure (and its CI
    bot-walling) to the nights something genuinely new appeared.
    """
    signals: dict[str, dict] = {}
    state = load_state(state_path)
    budget = _FetchBudget()

    for name, cid in WATCHED_CHANNELS.items():
        videos = recent_videos(cid)
        cached = state.get(cid)

        # Nothing newer than what we already mined → reuse it, no fetch.
        if cached and cached.get("topics") and (
                newest_candidate_id(videos) == cached.get("video_id")):
            signals[name] = {k: cached[k] for k in
                             ("video_id", "title", "published", "topics")}
            print(f"[creator_watch] {name}: reusing {cached['title']!r} "
                  f"({len(cached['topics'])} topics, still current)",
                  file=sys.stderr)
            continue

        episode = pick_episode(cid, label=name, budget=budget, videos=videos)
        if not episode:
            # A newer upload existed but wasn't usable (Short, off-beat, no
            # captions). The previously mined episode is still current, so it
            # remains the channel's best available signal.
            if cached and cached.get("topics"):
                signals[name] = {k: cached[k] for k in
                                 ("video_id", "title", "published", "topics")}
                print(f"[creator_watch] {name}: nothing usable newer — falling "
                      f"back to {cached['title']!r}", file=sys.stderr)
            else:
                print(f"[creator_watch] {name}: no usable episode tonight",
                      file=sys.stderr)
            continue

        topics = extract_topics(episode["transcript"],
                                video_title=episode["title"],
                                description=episode.get("description", ""))
        if not topics:
            print(f"[creator_watch] {name}: {episode['title']!r} yielded no "
                  f"topics", file=sys.stderr)
            continue

        # Deliberately drop `transcript` and `description`: signals are written
        # to the digest artifact, and their words must never be persisted
        # alongside ours. Only the mined topic terms survive.
        entry = {
            "video_id": episode["video_id"],
            "title": episode["title"],
            "published": episode["published"],
            "topics": topics,
        }
        signals[name] = entry
        state[cid] = entry
        print(f"[creator_watch] {name}: {episode['title']!r} → "
              f"{len(topics)} topics", file=sys.stderr)

    state = prune_state(state)
    save_state(state, state_path)

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


def sort_by_agenda(items: list[dict]) -> list[dict]:
    """Room overlap first, then relevance, then recency.

    A 0.70 story two creators hit tonight outranks a 1.0 RSS-only headline.
    """
    return sorted(
        items,
        key=lambda row: (
            (row.get("creator_signal") or {}).get("channel_count", 0),
            row.get("relevance_score", 0.0),
            recency_sort_key(row),
        ),
        reverse=True,
    )


def boost_candidates(digest: dict, signals: dict[str, dict]) -> dict:
    """Mark RSS stories that overlap watched creators and rank those first.

    Mutates and returns the digest. Each overlapping story records which
    channels and topics lifted it (`creator_signal`) so the ordering stays
    explainable. RSS-only stories remain, below the agenda.
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
        matches: list[tuple[str, list[str]]] = []
        for channel, topics in usable.items():
            matched = [t for t in topics if t in story_words]
            if len(matched) >= MIN_MATCHED_TOPICS:
                matches.append((channel, matched))
        if not matches:
            continue
        matches.sort(key=lambda row: len(row[1]), reverse=True)
        topics: list[str] = []
        seen: set[str] = set()
        for _channel, matched in matches:
            for topic in matched:
                if topic not in seen:
                    seen.add(topic)
                    topics.append(topic)
        boost = min(len(topics) * BOOST_PER_TOPIC, MAX_BOOST)
        item["relevance_score"] = round(item["relevance_score"] + boost, 3)
        item["creator_signal"] = {
            "channel": matches[0][0],
            "channels": [name for name, _matched in matches],
            "channel_count": len(matches),
            "matched_topics": topics[:8],
            "boost": boost,
        }

    digest["items"] = sort_by_agenda(digest["items"])
    digest["agenda"] = sorted({
        topic for topics in usable.values() for topic in topics
    })
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
    parser.add_argument("--state", default=None,
                        help="Where mined topics are remembered between runs "
                             f"(default: {DEFAULT_STATE_PATH})")
    args = parser.parse_args()

    signals = creator_topic_signals(Path(args.state) if args.state else None)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signals, indent=2) + "\n")
    print(f"Wrote signals for {len(signals)} channel(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
