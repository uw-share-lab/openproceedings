#!/usr/bin/env bash
# Case table for the /dependabot-review scripts (.claude/scripts/dependabot/, TASK-211): the rows are in
# dependabot_cases.py, which runs each script against a throwaway repo with a fake curl, npm and gh first on
# PATH (dependabot_fake.py), so `make tooling` and `make mutate` (mutants in
# .claude/scripts/mutants/dependabot.json) cover them without the network.
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
python3 "$(dirname "$0")/dependabot_cases.py"
