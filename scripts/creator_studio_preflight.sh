#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "== Creator Studio preflight =="
echo

echo "[1/5] Smoke test"
python -m pytest tests/creator_studio/test_run_smoke.py -q

echo
echo "[2/5] Creator Studio test suite"
python -m pytest tests/creator_studio -q

echo
echo "[3/5] Compile Python files"
python -m compileall -q creator-studio/studio creator-studio/run_smoke.py

echo
echo "[4/5] Check whitespace errors"
git diff --check

echo
echo "[5/5] Working tree summary"
git status --short

echo
echo "Creator Studio preflight passed."
