# Creator Studio Local Pipeline

Creator Studio has a fully local generated smoke pipeline for developer verification.

The local pipeline does not render video, publish video, call providers, call social APIs, or require OAuth.

## Run locally

    ./scripts/creator_studio_local_pipeline.sh

## Run from GitHub Actions

    gh workflow run creator-studio-local-pipeline.yml \
      -f pipeline=animated-explainer \
      -f name=vector-databases \
      -f topic="How vector databases power retrieval augmented generation"

## Check recent workflow runs

    gh run list --workflow creator-studio-local-pipeline.yml --limit 5
