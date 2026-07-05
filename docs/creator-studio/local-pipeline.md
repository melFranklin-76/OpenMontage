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

## Check recent workflow runs

    gh run list --workflow creator-studio-local-pipeline.yml --limit 5
