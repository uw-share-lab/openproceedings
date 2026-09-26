#!/usr/bin/env bash
# Case table for the test-suite network guard (backend/tests/conftest.py): run its pytest cases so
# `make tooling` and `make mutate` (mutants in .claude/scripts/mutants/gates.json) cover it.
set -euo pipefail
cd "$(dirname "$0")/../../.."
python=".venv/bin/python"
[ -x "$python" ] || python="python3"
"$python" -m pytest -q -p no:cacheprovider backend/tests/unit/test_no_network.py >/dev/null
echo "test-network-guard.sh: passed"
