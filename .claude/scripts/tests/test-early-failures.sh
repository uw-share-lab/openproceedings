#!/usr/bin/env bash
# Case table for OP_EARLY_FAILURES (backend/tests/conftest.py `_EarlyFailures`, TASK-057): run its pytest cases so
# `make tooling` and `make mutate` (mutants in .claude/scripts/mutants/gates.json) cover it.
set -euo pipefail
cd "$(dirname "$0")/../../.."
python=".venv/bin/python"
[ -x "$python" ] || python="python3"
out=$(env -u OP_EARLY_FAILURES "$python" -m pytest -q -p no:cacheprovider backend/tests/unit/test_early_failures.py 2>&1) \
  || { printf '%s\n' "$out"; echo "test-early-failures.sh: FAILED"; exit 1; }
echo "test-early-failures.sh: passed"
