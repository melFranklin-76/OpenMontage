
# 4A — Real Research Artifact Generation

## Goal

Replace the fake/seeded `research_brief.json` used in the Creator Studio smoke flow with a real generated research artifact.

The Research stage should produce a valid `research/research_brief.json` based on:

- project topic

- selected pipeline

- project persona

- platform

- the existing research stage request

- the existing research brief schema

## In scope

- Add a real research artifact generator.

- Use the existing Research stage handoff structure.

- Write `research/research_brief.json`.

- Validate the output against `schemas/artifacts/research_brief.schema.json`.

- Keep the output deterministic enough for tests.

- Add tests for the new research artifact generator.

- Keep the later stages fixture-only.

## Out of scope

Do not touch:

- real video rendering

- provider APIs

- OAuth

- social publishing

- scheduler

- analytics

- real video generation

- real audio generation

- real image generation

- real external research calls

- later stage real generation

## Acceptance criteria

- A new branch exists: `creator-studio-4a-real-research`.

- `research/research_brief.json` can be generated without manually seeding fake fixture JSON.

- The generated research brief passes the existing JSON schema.

- Existing full smoke flow still reaches `publish_complete`.

- All Creator Studio tests pass.

- No provider calls, rendering, publishing, OAuth, scheduler, or analytics are added.

