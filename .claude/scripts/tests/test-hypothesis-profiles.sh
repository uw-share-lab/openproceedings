#!/usr/bin/env bash
# Case table for the Hypothesis profiles' wall-clock rule (backend/tests/conftest.py, decision-024): run its
# pytest cases so `make tooling` and `make mutate` (mutants in .claude/scripts/mutants/gates.json) cover it.
set -euo pipefail
cd "$(dirname "$0")/../../.."
python=".venv/bin/python"
[ -x "$python" ] || python="python3"
"$python" -m pytest -q -p no:cacheprovider backend/tests/unit/test_hypothesis_profiles.py >/dev/null
echo "test-hypothesis-profiles.sh: passed"
