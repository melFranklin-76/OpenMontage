#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

pipeline="${1:-animated-explainer}"
name="${2:-vector-databases}"
topic="${3:-How vector databases power retrieval augmented generation}"

echo "== Creator Studio local generated pipeline =="
echo "Pipeline: $pipeline"
echo "Name:     $name"
echo "Topic:    $topic"
echo

python creator-studio/run_smoke.py \
  --pipeline "$pipeline" \
  --name "$name" \
  --topic "$topic"

echo
echo "Creator Studio local generated pipeline passed."
