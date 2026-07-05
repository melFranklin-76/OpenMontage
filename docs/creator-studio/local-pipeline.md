# Creator Studio Local Pipeline

[![Creator Studio Local Pipeline](https://github.com/melFranklin-76/OpenMontage/actions/workflows/creator-studio-local-pipeline.yml/badge.svg?branch=main)](https://github.com/melFranklin-76/OpenMontage/actions/workflows/creator-studio-local-pipeline.yml)

Creator Studio has a fully local generated smoke pipeline for developer verification.

The local pipeline does not render video, publish video, call providers, call social APIs, or require OAuth.

## Workflow status

The status badge reports the latest status for the Creator Studio local pipeline workflow on `main`.

The workflow can run manually through `workflow_dispatch` and automatically through the weekly schedule in `.github/workflows/creator-studio-local-pipeline.yml`.

A passing workflow means the local generated pipeline completed without rendering video, publishing video, calling providers, calling social APIs, or requiring OAuth.

## Run locally

    ./scripts/creator_studio_local_pipeline.sh

## Run from GitHub Actions

    gh workflow run creator-studio-local-pipeline.yml \
      -f pipeline=animated-explainer \
      -f name=vector-databases \
      -f topic="How vector databases power retrieval augmented generation"

## Download workflow artifacts

After a successful Creator Studio Local Pipeline workflow run, download the uploaded project artifacts with the run ID.

    gh run list --workflow creator-studio-local-pipeline.yml --limit 5

    rm -rf /tmp/creator-studio-artifacts
    mkdir -p /tmp/creator-studio-artifacts
    gh run download RUN_ID --dir /tmp/creator-studio-artifacts

Replace `RUN_ID` with the numeric workflow run ID from the newest successful `Creator Studio Local Pipeline` run.

## Review downloaded artifacts

The downloaded artifact should include the generated project folder and smoke log.

    find /tmp/creator-studio-artifacts -maxdepth 6 -type f | sort | grep -E 'run.json|checkpoint_|research_brief.json|proposal_packet.json|script.json|scene_plan.json|asset_manifest.json|edit_decisions.json|render_report.json|publish_log.json|vector-databases.log'

Expected files include:

    run.json
    checkpoint_research.json
    checkpoint_publish.json
    research/research_brief.json
    proposal/proposal_packet.json
    script/script.json
    scene_plan/scene_plan.json
    assets/asset_manifest.json
    edit/edit_decisions.json
    compose/render_report.json
    publish/publish_log.json
    logs/vector-databases.log

## Check recent workflow runs

    gh run list --workflow creator-studio-local-pipeline.yml --limit 5
