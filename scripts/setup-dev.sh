#!/usr/bin/env bash
# One-time local setup for contributors. Safe to re-run.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
common=$(git rev-parse --path-format=absolute --git-common-dir)
# In a cloud /dependabot-review clone (prs.py preflight's marker), step 0 points core.hooksPath at dev's hooks in its
# run directory; a re-run here must not point it back at the checked-out PR tree's .githooks (decision-048).
if [ -e "$common/op-no-dep-code" ]; then echo "kept core.hooksPath ($(git config core.hooksPath || true)): $common/op-no-dep-code is there"
else git config core.hooksPath .githooks; fi
# A safety net for copies without modes: every tracked file these globs match is committed 100755, so a
# clone stays clean (make tooling: .claude/scripts/check_file_modes.py, TASK-241).
chmod +x .githooks/* .claude/hooks/*.sh .claude/hooks/tests/*.sh .claude/scripts/*.py
command -v backlog >/dev/null || echo "Install Backlog.md: npm i -g backlog.md   (https://github.com/MrLesk/Backlog.md)"
# A cloud /dependabot-review run installs dev's environment once, before any PR is fetched, and none of a PR's after
# (decision-048, 2026-10-13): once prs.py preflight's marker is there, a re-run on a PR branch skips uv sync.
if [ -e "$common/op-no-dep-code" ]; then echo "skipped uv sync: $common/op-no-dep-code is there (a cloud run installs no PR's dependencies)"
elif command -v uv >/dev/null; then uv sync --locked --quiet; else echo "Install uv: https://docs.astral.sh/uv/"; fi
[ -f .env ] || { (umask 077; printf 'OPENREVIEW_USERNAME=\nOPENREVIEW_PASSWORD=\n' > .env); echo "Created .env (gitignored) — add OpenReview credentials for crawling."; }
echo "setup done: git hooks → .githooks, tooling executable."
