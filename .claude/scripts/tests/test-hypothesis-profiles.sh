#!/usr/bin/env bash
# Case table for the Hypothesis profiles' wall-clock rule (backend/tests/conftest.py, decision-024): run its
# pytest cases so `make tooling` and `make mutate` (mutants in .claude/scripts/mutants/gates.json) cover it.
# Twice: as on a laptop (CI unset) and as on a CI runner (CI set: Hypothesis then loads its built-in `ci` profile
# at import, which the repo's profiles must not inherit; TASK-146).
set -euo pipefail
cd "$(dirname "$0")/../../.."
python=".venv/bin/python"
[ -x "$python" ] || python="python3"
run() {  # quiet on success; on failure, pytest's report (make tooling prints a failing table's output)
  local out
  out=$("$@" "$python" -m pytest -q -p no:cacheprovider backend/tests/unit/test_hypothesis_profiles.py 2>&1) \
    || { printf '%s\n' "$out"; echo "test-hypothesis-profiles.sh: FAILED with: $*"; exit 1; }
}
run env -u CI
run env CI=true
echo "test-hypothesis-profiles.sh: passed"
