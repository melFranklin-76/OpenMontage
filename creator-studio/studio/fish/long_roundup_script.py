"""Long-form roundup script for What's the LGBT, Fish?

Chains the top-N ranked stories from a daily digest into a single ~24-minute
YouTube long-form script: cold open, intro, N story chapters (each with a
lane-tinted title reveal, hook, story body, why-it-matters, and transition
to the next), and an outro with CTA + hashtags.

Output shape (drop-in for long_roundup_render.py):

    {
      show, format: "roundup",
      date, target_duration_seconds,
      stories: [{ rank, title, source, url, lane, ... }],
      sections: [
        { id: "cold_open",     narration, duration_seconds, chapter_ts: None },
        { id: "intro",         narration, duration_seconds, chapter_ts: 0 },
        { id: "ch1_title",     narration, duration_seconds, chapter_ts: 60, ... },
        { id: "ch1_body",      narration, duration_seconds, ... },
        ...
        { id: "outro",         narration, duration_seconds, chapter_ts: 1400 }
      ],
      hashtags: [...],
      chapter_timestamps: [{ seconds, label }]  # for YouTube description
    }

The script is deterministic-local per AGENT_GUIDE — an LLM upgrade layer
(claude-fable-5 for narration polish) can slot in later without changing
the schema.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from .daily_digest import build_daily_candidates
from .intake import fetch_live_stories
from .reel_script import BASE_HASHTAGS, LANE_HASHTAGS, LANE_WHY_LINES, _truncate_words

SHOW_NAME = "What's the LGBT, Fish?"
TARGET_STORY_COUNT = 10
WORDS_PER_SECOND = 2.5      # ~150 WPM Piper speaking rate

# Tone note: the host register is gay male queer-news commentary —
# direct address, campy energy, opinionated asides — in the spirit of
# creators like Funky Dineva. Facts stay straight; delivery has flavor.
# Keep it monetization-safe: no slurs, no defamation, no unverified tea.

COLD_OPEN_LINES = [
    "Hey y'all, hey! It is your girl, and this is What's the LGBT, Fish? — "
    "the only roundup that loves you enough to tell you the truth. "
    "{count_word} stories today, honey. No fluff, no filler, and absolutely no "
    "both-sides-ing our own existence. Just what happened, who it happened "
    "to, and why you need to know before somebody's cousin misquotes it in "
    "a group chat.",
]

INTRO_LINES_TEMPLATE = (
    "Alright, let's get into it. Today is {date_readable}, and baby, the "
    "news did NOT take a day off — we've got {count_word} stories from {lanes_summary}. "
    "Now one ground rule before we start, because y'all know I keep it "
    "honest: the order of these stories comes from our relevance scoring, "
    "not from me playing favorites. Four lanes — lesbian, gay, bisexual, "
    "and trans — and every single story earned its seat at "
    "this table. Some of this you will not find on anybody's front page. "
    "That's not an accident, and that's exactly why we're here. So pour "
    "your little beverage and let's talk about it."
)

LANE_ANALYSIS_LINES = {
    "gay": (
        "And listen — visibility is not a trophy you win once and put on a "
        "shelf, it's rent, and it is due every single day. We hold the frame "
        "or somebody else writes the caption for us. That's just facts."
    ),
    "lesbian": (
        "Now can we talk about how lesbian stories always get filed under "
        "'women' or shoved into the big LGBT folder until the specifics "
        "disappear? Not on this show, baby. We say who it's about, by name, "
        "with our whole chest."
    ),
    "bisexual": (
        "And you already know how this goes — the minute a bi person makes "
        "the news, the headlines flatten them into gay or straight depending "
        "on who's standing next to them. Not here. We call it what it is, "
        "because bi erasure is played out and we are not participating."
    ),
    "trans": (
        "Now hold on, because this is the part where I need y'all to lean "
        "in. Trans stories can carry some of the highest stakes in our whole "
        "community and get the least coverage — and that gap? That gap is "
        "the entire reason this show exists. We lead with our sisters and "
        "brothers, period."
    ),
}


LANE_TITLE_TEMPLATE = {
    "gay":         "Story {n} of {total} — from the gay lane",
    "lesbian":     "Story {n} of {total} — from the lesbian lane",
    "bisexual":    "Story {n} of {total} — from the bi visibility lane",
    "trans": "Story {n} of {total} — centering trans voices",
}

NUMBER_WORDS = {
    1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
    6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
}

TRANSITION_LINES = [
    "Okay, moving right along, because the tea does not steep itself.",
    "Now hold that thought, because this next one? Whew.",
    "Alright, deep breath, y'all — story {next_n}, let's go.",
    "Meanwhile, in a whole other corner of the community...",
    "And just when you thought the day was done, baby, it was not.",
    "Speaking of stories that deserve way more attention than they got.",
    "Now this next one, I need y'all to really hear me on.",
    "Okay okay okay — next story, because we have things to discuss.",
    "That was story {n}. Story {next_n} is where it gets interesting.",
    "Let me sip some water, because this next one took me OUT.",
    "Y'all still with me? Good, because we are not done.",
    "Now switch gears with me for a second.",
    "And the news just kept on newsing, honey.",
    "This next story? I have thoughts. Let's get into them.",
]

OUTRO_LINES_TEMPLATE = (
    "And THAT, my loves, is {count_word_lower} stories in {total_min} minutes — you are "
    "officially caught up, and nobody at brunch can tell you nothing. If "
    "any of these stories hit you somewhere real, get in those comments and "
    "talk to me — the algorithm rewards conversation and I reward good tea. "
    "Every single source is linked down in the description, with chapter "
    "timestamps, so if somebody in your life needs exactly ONE of these "
    "stories, you can send them straight to it. Clip it, share it, forward "
    "it to your messiest group chat. Follow for tomorrow's roundup — same "
    "time, same energy, same four lanes. And until then, you know what to "
    "do: keep asking... what's the LGBT, Fish? Okay bye!"
)


_ARTICLE_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def _strip_html(html: str) -> str:
    """Very-basic HTML → plain text. Not perfect, good enough for enrichment."""
    # Drop <script>/<style>/<nav>/<footer>/<aside> blocks entirely
    html = re.sub(
        r"<(script|style|nav|footer|aside|header|form)[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Convert paragraph and heading tags to newlines
    html = re.sub(r"</?(p|h[1-6]|br|li|div)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Drop all remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    # HTML entities we care about
    html = (html.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#8217;", "'").replace("&#8216;", "'")
                .replace("&#8220;", '"').replace("&#8221;", '"')
                .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    # Strip URLs — Piper TTS spells these out letter by letter
    html = re.sub(r"https?://\S+", "", html)
    html = re.sub(r"www\.\S+", "", html)
    return re.sub(r"[ \t]+", " ", html)


def _fetch_article(url: str, timeout: int = 15) -> str:
    """Direct fetch + HTML cleanup. Returns "" on any failure."""
    if not url:
        return ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _ARTICLE_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(300_000)
            encoding = resp.headers.get_content_charset() or "utf-8"
        html = raw.decode(encoding, errors="replace")
        return _strip_html(html)
    except Exception as exc:  # noqa: BLE001
        print(f"[roundup] article fetch failed for {url}: {exc}", file=sys.stderr)
        return ""


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _extract_key_sentences(article_text: str, max_sentences: int = 10) -> list[str]:
    """Pick the most information-dense sentences from Jina-Reader output.

    We drop obvious nav/UI/boilerplate lines and prefer sentences that contain
    numbers, dates, quoted material, or proper nouns beyond the first word.
    """
    if not article_text:
        return []

    # Strip any URLs/emails that survived HTML cleanup — TTS spells them out
    body = re.sub(r"https?://\S+", "", article_text)
    body = re.sub(r"www\.\S+", "", body)
    body = re.sub(r"\S+@\S+\.\S+", "", body)
    body = re.sub(r"\s+", " ", body)

    candidates: list[tuple[int, str]] = []
    for sent in _SENTENCE_SPLIT.split(body):
        s = sent.strip()
        if not (60 <= len(s) <= 320):
            continue
        low = s.lower()
        # Boilerplate skips
        if any(kw in low for kw in (
            "cookie", "subscribe", "newsletter", "sign in",
            "privacy policy", "terms of service", "©", "all rights reserved",
            "read more", "click here", "follow us", "advertisement",
        )):
            continue
        score = 0
        if re.search(r"\b(19|20)\d{2}\b", s):          # a year
            score += 2
        if re.search(r"\b\d{1,3}[,%]?\b", s):           # any number
            score += 1
        if re.search(r"[\"“][^\"”]{15,}[\"”]", s):      # a quote
            score += 3
        # Proper-noun-ish token beyond the first word
        words = s.split()
        if any(w[:1].isupper() and w.isalpha() for w in words[1:]):
            score += 1
        candidates.append((score, s))

    candidates.sort(key=lambda t: t[0], reverse=True)
    seen: set[str] = set()
    picked: list[str] = []
    for _, s in candidates:
        key = s[:60].lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(s)
        if len(picked) >= max_sentences:
            break
    return picked


def _dur_from_text(text: str) -> int:
    """Estimate spoken seconds from word count (150 WPM ~= 2.5 wps)."""
    words = len(text.split())
    return max(3, round(words / WORDS_PER_SECOND))


def _readable_date(iso: str) -> str:
    """Return 'July 8, 2026' from '2026-07-08'."""
    try:
        y, m, d = iso.split("-")
        month = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ][int(m) - 1]
        return f"{month} {int(d)}, {y}"
    except Exception:
        return iso


def _lanes_summary(stories: list[dict]) -> str:
    """Human-readable summary like 'lesbian, gay, and trans lanes'."""
    lanes = []
    seen: set[str] = set()
    for s in stories:
        lane = s.get("matched_lane") or s.get("lane") or ""
        if lane and lane not in seen:
            seen.add(lane)
            lanes.append(lane)
    if not lanes:
        return "across the community"
    if len(lanes) == 1:
        return f"the {lanes[0]} lane"
    if len(lanes) == 2:
        return f"the {lanes[0]} and {lanes[1]} lanes"
    return "the " + ", ".join(lanes[:-1]) + f", and {lanes[-1]} lanes"


def _story_narration(story: dict, article_sentences: list[str] | None = None) -> str:
    """Compose the narration for a single story block.

    If article_sentences are provided (from Jina Reader), splice them in
    after the hook to give each block real journalistic depth instead of
    the 12-word RSS summary alone.
    """
    title = story.get("title", "").strip()
    summary = story.get("summary", "").strip()
    source = story.get("source", "").strip()
    lane = story.get("matched_lane") or story.get("lane") or ""

    hook = title.rstrip(".") + "."
    parts: list[str] = [hook]

    if article_sentences:
        parts.append("\nOkay, so here's the rundown.\n")
        connectors = [
            None, None,
            "\nNow here's where it gets real.\n",
            None,
            "\nAnd it did not stop there, baby.\n",
            None, None,
            "\nStay with me, because there's more.\n",
            None, None,
        ]
        for j, sent in enumerate(article_sentences[:10]):
            conn = connectors[j] if j < len(connectors) else None
            if conn:
                parts.append(conn)
            # Strip any stray URLs from individual sentences
            clean = re.sub(r"https?://\S+", "", sent).strip()
            if clean:
                parts.append(clean)
    elif summary:
        clean_summary = re.sub(r"https?://\S+", "", _truncate_words(summary, 80))
        parts.append(clean_summary)
        parts.append(
            "\nNow that's the short version... the wire copy was stingy today... "
            "so we'll keep this one tight and let the source fill in the rest.\n"
        )

    parts.append("\nSo why does this matter?\n")
    parts.append(LANE_WHY_LINES.get(lane, "This story matters to our community."))

    # Host analysis — lane-specific framing to add depth
    analysis = LANE_ANALYSIS_LINES.get(lane)
    if analysis:
        parts.append("\n" + analysis)

    if source:
        parts.append(
            f"\nThat reporting comes from {source}... link's in the description, "
            "go show them some love.\n"
        )

    return "\n".join(parts)


def build_roundup_script(
    digest: dict,
    story_count: int = TARGET_STORY_COUNT,
    enrich_via_jina: bool = True,
) -> dict:
    """Turn a daily digest into a long-form roundup script."""
    items = digest.get("items", [])[:story_count]
    if not items:
        raise ValueError("Digest has no items")

    digest_date = digest.get("date", date.today().isoformat())
    date_readable = _readable_date(digest_date)
    n_stories = len(items)
    count_word = NUMBER_WORDS.get(n_stories, str(n_stories))

    sections: list[dict] = []

    # Cold open (no chapter marker — it's pre-intro hook)
    cold_open = COLD_OPEN_LINES[0].format(count_word=count_word)
    sections.append({
        "id": "cold_open",
        "narration": cold_open,
        "duration_seconds": _dur_from_text(cold_open),
        "chapter_ts": None,
        "visual_hint": "Show logo card with cold-open text overlay",
    })

    # Intro
    intro = INTRO_LINES_TEMPLATE.format(
        date_readable=date_readable,
        lanes_summary=_lanes_summary(items),
        count_word=count_word.lower(),
    )
    sections.append({
        "id": "intro",
        "narration": intro,
        "duration_seconds": _dur_from_text(intro),
        "chapter_ts": 0,      # first chapter — filled with running total below
        "chapter_label": "Intro",
        "visual_hint": "Host title card, date, story-count teaser",
    })

    # Story blocks
    for i, story in enumerate(items, start=1):
        lane = story.get("matched_lane") or story.get("lane") or ""
        title_line = LANE_TITLE_TEMPLATE.get(
            lane, "Story {n} of {total}"
        ).format(n=i, total=n_stories)

        sections.append({
            "id": f"ch{i}_title",
            "narration": title_line,
            "duration_seconds": _dur_from_text(title_line) + 1,   # + beat of silence
            "chapter_ts": 0,
            "chapter_label": f"{i}. {_truncate_words(story.get('title', ''), 12)}",
            "story_rank": i,
            "story_url": story.get("url", ""),
            "story_source": story.get("source", ""),
            "lane": lane,
            "visual_hint": "Full-frame lane-tinted card with story number + headline",
        })

        enrichment: list[str] = []
        if enrich_via_jina and story.get("url"):
            article = _fetch_article(story["url"])
            enrichment = _extract_key_sentences(article)
            if enrichment:
                print(
                    f"[roundup] enriched story {i} with {len(enrichment)} sentences",
                    file=sys.stderr,
                )
        body = _story_narration(story, article_sentences=enrichment)
        sections.append({
            "id": f"ch{i}_body",
            "narration": body,
            "duration_seconds": _dur_from_text(body),
            "enriched": bool(enrichment),
            "story_rank": i,
            "story_url": story.get("url", ""),
            "story_source": story.get("source", ""),
            "lane": lane,
            "visual_hint": "Hero image with Ken Burns motion; no burned narration captions",
        })

        # Transition between stories (skip after last)
        if i < len(items):
            trans_line = TRANSITION_LINES[i % len(TRANSITION_LINES)].format(
                n=i, next_n=i + 1
            )
            sections.append({
                "id": f"ch{i}_transition",
                "narration": trans_line,
                "duration_seconds": _dur_from_text(trans_line),
                "visual_hint": "Interstitial brand ident, 1s beat",
            })

    # Outro
    total_est = sum(s["duration_seconds"] for s in sections)
    total_min = round(total_est / 60)
    # Hashtags are never spoken — they live in script["hashtags"] and end up
    # in the YouTube/IG description, not the narration.
    outro = OUTRO_LINES_TEMPLATE.format(
        total_min=total_min, count_word_lower=count_word.lower(),
    )
    sections.append({
        "id": "outro",
        "narration": outro,
        "duration_seconds": _dur_from_text(outro),
        "chapter_ts": 0,
        "chapter_label": "Outro & credits",
        "visual_hint": "Brand card, socials, CTA follow prompt",
    })

    # Fill in real chapter_ts values based on running duration
    running = 0
    chapter_timestamps: list[dict] = []
    for s in sections:
        if s.get("chapter_ts") is not None:
            s["chapter_ts"] = running
            if s.get("chapter_label"):
                chapter_timestamps.append({
                    "seconds": running,
                    "label": s["chapter_label"],
                })
        running += s["duration_seconds"]

    target_duration = sum(s["duration_seconds"] for s in sections)

    lane_hashtags = set()
    for story in items:
        lane = story.get("matched_lane") or story.get("lane") or ""
        for t in LANE_HASHTAGS.get(lane, []):
            lane_hashtags.add(t)

    return {
        "show": SHOW_NAME,
        "format": "roundup",
        "script_date": date.today().isoformat(),
        "digest_date": digest_date,
        "target_duration_seconds": target_duration,
        "story_count": len(items),
        "stories": [
            {
                "rank": i + 1,
                "title": s.get("title", ""),
                "source": s.get("source", ""),
                "url": s.get("url", ""),
                "lane": s.get("matched_lane") or s.get("lane") or "",
                "relevance_score": s.get("relevance_score", 0.0),
            }
            for i, s in enumerate(items)
        ],
        "sections": sections,
        "chapter_timestamps": chapter_timestamps,
        "hashtags": BASE_HASHTAGS + sorted(lane_hashtags),
        "metadata": {
            "generated_by": "creator-studio/studio/fish/long_roundup_script.py",
            "generation_mode": "deterministic_local",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a FISH long-form roundup script")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--digest", help="Path to a daily digest JSON file")
    src.add_argument("--live", action="store_true", help="Fetch fresh stories and build")
    parser.add_argument("--count", type=int, default=TARGET_STORY_COUNT,
                        help=f"Story count (default: {TARGET_STORY_COUNT})")
    parser.add_argument("--output", required=True, help="Output script JSON path")
    parser.add_argument(
        "--no-enrich", action="store_true",
        help="Skip Jina Reader article enrichment (offline / debug)",
    )
    args = parser.parse_args()

    if args.live:
        digest = build_daily_candidates(fetch_live_stories())
    else:
        digest = json.loads(Path(args.digest).read_text())

    script = build_roundup_script(
        digest, story_count=args.count, enrich_via_jina=not args.no_enrich,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, indent=2) + "\n")

    total = script["target_duration_seconds"]
    mins, secs = divmod(total, 60)
    print(f"Wrote roundup script: {mins}m {secs}s across {len(script['sections'])} sections, "
          f"{script['story_count']} stories")
    print(f"  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
