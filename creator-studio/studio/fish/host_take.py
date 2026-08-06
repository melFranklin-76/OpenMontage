"""Host takes — the part of the show that isn't someone else's reporting.

The script generators are deterministic, which is good for facts and bad for
opinion. Every story in a lane currently ends with the *same* stock paragraph:
`LANE_WHY_LINES` and `LANE_ANALYSIS_LINES` are four sentences each, reused on
every story in that lane forever. Across a year of nightly output that is a
few hundred videos drawing their entire viewpoint from eight paragraphs.

That matters beyond taste. YouTube's reused-content policy asks whether a
channel adds "significant original commentary" to material it did not produce,
and applies the answer to the channel as a whole. A stock line that is
byte-identical across hundreds of uploads is not commentary, and neither is
reading a wire summary aloud — including in the host's own voice. Recording
narration fixes *who made this*; only a real take fixes *why it exists*.

So the take comes from the host, not a template. The pipeline writes the facts
and a prompt; the host writes two or three sentences per story; `apply_takes`
substitutes those in place of the stock lines. `find_canned` reports whatever
is still boilerplate so a script can be stopped before it ships.

This deliberately does not generate takes automatically. An LLM take would be
story-specific but still not the creator's perspective, which is the exact
thing the policy asks for.

Usage:

    # after scripts are generated
    python -m studio.fish.host_take prompts --script fish-roundup-script.json \\
        --video-key roundup --output takes.md
    # ... host fills in takes.md ...
    python -m studio.fish.host_take apply --script fish-roundup-script.json \\
        --takes takes.md --output fish-roundup-script.json
    python -m studio.fish.host_take check --script fish-roundup-script.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

# A take shorter than this is a placeholder, not a point of view.
MIN_TAKE_WORDS = 15

_RANK_HEADING_RE = re.compile(r"^##\s+Rank\s+(\d+)\b", re.MULTILINE)
_TAKE_HEADING_RE = re.compile(r"^###\s+Your take\s*$", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_PLACEHOLDER = "(write your take here)"


def stock_phrases() -> dict[str, str]:
    """Every hardcoded editorial line the generators can emit → its origin.

    Imported lazily so the render path doesn't pull in script generation.
    """
    from .long_roundup_script import LANE_ANALYSIS_LINES
    from .reel_script import LANE_WHY_LINES

    phrases: dict[str, str] = {}
    for lane, line in LANE_WHY_LINES.items():
        phrases[line] = f"LANE_WHY_LINES[{lane!r}]"
    for lane, line in LANE_ANALYSIS_LINES.items():
        phrases[line] = f"LANE_ANALYSIS_LINES[{lane!r}]"
    return phrases


def _section_rank(script: dict, section: dict) -> int | None:
    """Which story a section belongs to. Reels carry one story overall."""
    rank = section.get("story_rank")
    if rank is None:
        rank = script.get("digest_rank")
    return rank


# ── detecting boilerplate ────────────────────────────────────────────────────

def find_canned(script: dict) -> list[dict]:
    """Sections still carrying a stock editorial line.

    Returns [{section, rank, origin}, ...] — empty means every viewpoint in
    this script came from the host.
    """
    phrases = stock_phrases()
    found: list[dict] = []
    for section in script.get("sections", []):
        narration = section.get("narration") or ""
        for phrase, origin in phrases.items():
            if phrase in narration:
                found.append({
                    "section": section.get("id", "?"),
                    "rank": _section_rank(script, section),
                    "origin": origin,
                })
    return found


def describe_canned(script: dict) -> str:
    canned = find_canned(script)
    if not canned:
        return "no stock editorial lines — every take is the host's"
    parts = [f"{c['section']} ({c['origin']})" for c in canned]
    return f"{len(canned)} stock line(s) still in script: " + ", ".join(parts)


# ── applying host takes ──────────────────────────────────────────────────────

def apply_takes(script: dict, takes: dict[int, str]) -> dict:
    """Swap stock editorial lines for the host's own words.

    Substitutes by exact phrase so it works for both generators: the reel puts
    the stock line in its own `why_it_matters` section, while the roundup
    embeds it mid-paragraph in the story body. Returns a new script; the
    original is not modified.

    A roundup body carries *two* stock lines — the why line and the analysis
    line — so the take replaces the first and the rest are dropped. Swapping
    the take into both would have the host say the same thing twice in a row.
    """
    phrases = stock_phrases()
    updated = json.loads(json.dumps(script))

    for section in updated.get("sections", []):
        rank = _section_rank(updated, section)
        take = takes.get(rank) if rank is not None else None
        if not take:
            continue
        narration = section.get("narration") or ""

        present = sorted(
            (p for p in phrases if p in narration),
            key=narration.index,
        )
        if not present:
            continue

        replaced = narration.replace(present[0], take.strip(), 1)
        for extra in present[1:]:
            replaced = replaced.replace(extra, "")
        # Dropping a paragraph leaves a run of blank lines behind.
        replaced = re.sub(r"\n{3,}", "\n\n", replaced).strip()

        section["narration"] = replaced
        section["take_source"] = "host"

    updated.setdefault("metadata", {})["host_takes_applied"] = sorted(
        r for r, t in takes.items() if t
    )
    return updated


# ── prompt file the host writes into ─────────────────────────────────────────

def write_take_prompts(
    script: dict, out_path: Path, *, video_key: str, show_date: str | date,
) -> Path:
    """Write the file the host puts their opinion into.

    Shows the facts and the stock line each take will replace, so the host can
    see exactly what the show would otherwise have said.
    """
    phrases = stock_phrases()
    stories = script.get("stories") or []
    if not stories:
        stories = [{
            "rank": script.get("digest_rank", 1),
            "title": script.get("topic", ""),
            "lane": script.get("lane", ""),
            "url": (script.get("source_attribution") or {}).get("url", ""),
            "source": (script.get("source_attribution") or {}).get("name", ""),
        }]

    lines = [
        f"# Your takes — {video_key} — {show_date}",
        "",
        f"{len(stories)} stories. Two or three sentences each, in your voice.",
        "",
        "This is the part that makes the show yours. Everything else in the "
        "script is either fact from the source or format — the take is the "
        "only place your point of view exists, and a stock line reused across "
        "every story in a lane does not count as commentary.",
        "",
        f"Write under each **### Your take** heading. At least "
        f"{MIN_TAKE_WORDS} words, or it won't be treated as filled in.",
        "",
        "---",
        "",
    ]

    for story in stories:
        rank = story.get("rank", "?")
        lane = story.get("matched_lane") or story.get("lane") or ""
        title = (story.get("title") or "").strip()
        source = (story.get("source") or "").strip()
        url = (story.get("url") or "").strip()
        summary = (story.get("summary") or "").strip()

        lines.append(f"## Rank {rank} — {title}")
        lines.append("")
        if source or url:
            lines.append(f"**Source:** {source} · {url}".strip(" ·"))
            lines.append("")
        if summary:
            lines.append(f"**What happened:** {summary}")
            lines.append("")

        stock = next((p for p, origin in phrases.items()
                      if origin.endswith(f"[{lane!r}]") and "WHY" in origin), None)
        if stock:
            lines.append("**Stock line your take replaces** — this is what "
                         "every other story in this lane says, word for word:")
            lines.append("")
            lines.append(f"> {stock}")
            lines.append("")

        lines.append("### Your take")
        lines.append("")
        lines.append(_PLACEHOLDER)
        lines.append("")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    return out_path


def read_takes(path: Path) -> dict[int, str]:
    """Parse filled-in takes, keyed by story rank.

    Placeholders, blockquotes and comments are ignored, and anything under
    MIN_TAKE_WORDS is treated as not written yet rather than accepted as a
    one-word opinion.
    """
    text = _HTML_COMMENT_RE.sub("", Path(path).read_text())

    takes: dict[int, str] = {}
    headings = list(_RANK_HEADING_RE.finditer(text))
    for i, heading in enumerate(headings):
        rank = int(heading.group(1))
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[heading.end():end]

        take_heading = _TAKE_HEADING_RE.search(block)
        if not take_heading:
            continue
        body = block[take_heading.end():]

        kept = [
            line.strip() for line in body.splitlines()
            if line.strip()
            and not line.lstrip().startswith((">", "#", "**"))
            and _PLACEHOLDER not in line
        ]
        take = " ".join(kept).strip()
        if len(take.split()) >= MIN_TAKE_WORDS:
            takes[rank] = take
    return takes


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Host takes for a FISH script")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prompts = sub.add_parser("prompts", help="Write the take prompt file")
    p_prompts.add_argument("--script", required=True)
    p_prompts.add_argument("--video-key", required=True)
    p_prompts.add_argument("--date", default=str(date.today()))
    p_prompts.add_argument("--output", required=True)

    p_apply = sub.add_parser("apply", help="Merge filled-in takes into a script")
    p_apply.add_argument("--script", required=True)
    p_apply.add_argument("--takes", required=True)
    p_apply.add_argument("--output", required=True)

    p_check = sub.add_parser("check", help="Report stock lines still in a script")
    p_check.add_argument("--script", required=True)
    p_check.add_argument("--strict", action="store_true",
                         help="Exit non-zero when any stock line remains")

    args = parser.parse_args()
    script = json.loads(Path(args.script).read_text())

    if args.command == "prompts":
        out = write_take_prompts(script, Path(args.output),
                                 video_key=args.video_key, show_date=args.date)
        print(f"Wrote take prompts to {out}")
        return 0

    if args.command == "apply":
        takes = read_takes(Path(args.takes))
        if not takes:
            print(f"No takes filled in at {args.takes} "
                  f"(each needs {MIN_TAKE_WORDS}+ words)", file=sys.stderr)
        updated = apply_takes(script, takes)
        Path(args.output).write_text(json.dumps(updated, indent=2) + "\n")
        print(f"Applied {len(takes)} take(s) → {args.output}")
        print(describe_canned(updated))
        return 0

    print(describe_canned(script))
    return 1 if (args.strict and find_canned(script)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
