#!/usr/bin/env bash
# One-time local setup for contributors. Safe to re-run.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/* .claude/hooks/*.sh .claude/hooks/tests/*.sh .claude/scripts/*.py
command -v backlog >/dev/null || echo "Install Backlog.md: npm i -g backlog.md   (https://github.com/MrLesk/Backlog.md)"
command -v uv >/dev/null || echo "Install uv: https://docs.astral.sh/uv/"
[ -f .env ] || { printf 'OPENREVIEW_USERNAME=\nOPENREVIEW_PASSWORD=\n' > .env; echo "Created .env (gitignored) — add OpenReview credentials for crawling."; }
echo "setup done: git hooks → .githooks, tooling executable."
