# OpenMontage Project State

Last verified: 2026-07-23

## Current Focus

Make FISH backgrounds reliably match the story being told, then continue
improving retention through faster openings, tighter scripts, and stronger
visual pacing.

## Current Main Branch

- Branch: `main`
- Commit: `3550071` — Improve FISH video brightness and text readability (#73)
- Local and remote `main` matched when this file was created.

## Active Pull Request

- Draft PR [#74 — Require story-relevant FISH backgrounds](https://github.com/melFranklin-76/OpenMontage/pull/74)
- Branch: `fish-visual-relevance-gate`
- Commit: `e6f0932`
- Automated FISH and Creator Studio checks pass.
- Awaiting one live production run and visual review before merge.

## Current Workflow Status

- FISH Daily Digest checks for PR #74: passing
- Creator Studio CI for PR #74: passing
- Recent FISH Shorts Stagger runs on `main`: passing
- Last verified end-to-end daily digest on PR #73 rendered ten Shorts, rendered
  the long-form roundup, uploaded a private YouTube draft, and uploaded the
  GitHub artifact successfully.

## Completed

- FISH daily digest and four editorial lanes: gay, lesbian, bisexual, and trans
- Daily Black trans story search without repeatedly labeling scripts as
  "Black trans"
- Shorts rendering and staggered publishing workflow
- Long-form roundup rendering and private YouTube draft upload
- Brian host voice and dry/literal FISH vocabulary
- Removal of obsolete `legacy` lane handling
- Removal of long-form burned narration captions
- Public release assets and GitHub Actions pipeline
- Exact licensed story-media resolver
- Real Wikimedia Commons footage support
- Article hero-image fallback
- Remotion Shorts with word-highlight captions
- Improved background brightness and title/caption readability
- FFmpeg segment normalization for mixed sample-aspect ratios

## Known Issues and Review Items

- Visually validate PR #74 against a real daily episode before merging.
- Confirm every story uses exact media, its article image, or validated stock;
  unrelated generic lane footage must not return.
- Continue improving opening speed and long-form visual pacing.
- Continue tightening script wit, word repetition, and pronunciation.
- Audit open issues #34-#37 against current code before implementing or closing
  them; some described functionality may already exist.

## Architecture Decisions

- Exact licensed footage or imagery outranks stock footage.
- The source article's hero image outranks generic stock motion.
- Public-person stories require exact media or the source article image.
- Raw headline text is never sent directly to Pexels.
- Generic pride/lane footage is not acceptable merely to keep the screen moving.
- If relevant media cannot be verified, use branded graphics instead of an
  unrelated clip.
- The daily search may target Black trans stories, but generated narration
  should not repeatedly emphasize race unless it is materially relevant.
- Production uploads remain private drafts until reviewed.

## Current Next Step

Run FISH Daily Digest from the PR #74 branch, inspect the resulting private
draft for visual relevance, and merge #74 only if the episode passes review.

## Exact Next Terminal Commands

```bash
cd /Users/melfranklin/AIProjects/OpenMontage
gh workflow run fish-daily-digest.yml --ref fish-visual-relevance-gate
gh run list --workflow fish-daily-digest.yml --branch fish-visual-relevance-gate --limit 1
```

After the run completes:

```bash
gh run view <RUN_ID> --log
gh pr checks 74
```

## Required Validation Commands

```bash
cd /Users/melfranklin/AIProjects/OpenMontage
python3.12 -m pytest tests/creator_studio/test_run_smoke.py -q
python3.12 -m pytest tests/creator_studio -q
```

## Recent Pull Requests

- #74 Require story-relevant FISH backgrounds — open draft
- #73 Improve FISH video brightness and text readability — merged
- #72 Use an absolute Remotion props path with FFmpeg fallback — merged
- #71 Render Shorts through Remotion with word-highlight captions — merged
- #70 Play real Commons footage of the story subject — merged
- #69 Stop media resolver matches from Title-Case junk subjects — merged
- #68 Never send literal headline words to Pexels — merged
- #67 Add licensed story-specific media resolution — merged
- #66 Remove committed run artifact and ignore `/out/` — merged
- #65 Fix repeated-number bug, dry voice, and b-roll relevance — merged

## Future Milestones

1. Merge the verified visual-relevance gate.
2. Add scene-level media changes so one visual does not loop for an entire story.
3. Add a reviewable approval queue for stories, scripts, captions, and assets.
4. Connect selected FISH stories to Creator Studio research briefs.
5. Maintain a curated editorial source registry with trust notes.
6. Track retention, watch time, comments, and subscriber conversion by episode.

## Update Rule

Update this file after each merged PR or material workflow change. Record the
verified commit, current workflow status, active blocker, and exact next command.
