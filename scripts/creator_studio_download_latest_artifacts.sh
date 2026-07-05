#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_NAME="${CREATOR_STUDIO_ARTIFACT_WORKFLOW:-creator-studio-local-pipeline.yml}"
BRANCH_NAME="${CREATOR_STUDIO_ARTIFACT_BRANCH:-main}"
OUTPUT_DIR="${1:-/tmp/creator-studio-artifacts}"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI is required: gh" >&2
  exit 1
fi

RUN_ID="$(
  gh run list \
    --workflow "$WORKFLOW_NAME" \
    --branch "$BRANCH_NAME" \
    --limit 10 \
    --json databaseId,conclusion \
    --jq 'map(select(.conclusion=="success"))[0].databaseId'
)"

if [[ -z "${RUN_ID}" || "${RUN_ID}" == "null" ]]; then
  echo "error: no successful $WORKFLOW_NAME run found on branch $BRANCH_NAME" >&2
  exit 1
fi

rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

echo "Downloading Creator Studio artifacts"
echo "Workflow: $WORKFLOW_NAME"
echo "Branch:   $BRANCH_NAME"
echo "Run ID:   $RUN_ID"
echo "Output:   $OUTPUT_DIR"
echo

gh run download "$RUN_ID" --dir "$OUTPUT_DIR"

echo
echo "Downloaded files:"
find "$OUTPUT_DIR" -maxdepth 4 -type f | sort

echo
echo "Key files:"
find "$OUTPUT_DIR" -type f \
  \( -name "run.json" -o -name "stage_request.json" -o -name "metadata.json" -o -name "*.log" \) \
  | sort
