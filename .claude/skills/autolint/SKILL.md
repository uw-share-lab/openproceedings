---
name: autolint
description: The monorepo's auto-format and lint setup (modelled on the naturalschema repo) — the PostToolUse autofix hook that formats and fixes each file as it is edited, `make fmt` / `make lint`, the pre-push git hook that mirrors CI, and the CI lint job in check mode — with the tool per file type (ruff, prettier, eslint, shellcheck) and what to do when a fix can't be applied automatically. Use when a lint check fails, when adding a language or tool to the repo, or when the autofix hook reports a problem.
---

# Autolint

Three layers, each catching what the one before could not:

| Layer | When | What | Mode |
|---|---|---|---|
| `.claude/hooks/autofix.sh` | after every Write/Edit by Claude | the edited file only | **fix** (format + safe autofixes), then report whatever remains |
| `make fmt` / `make lint` | whenever you like; `make lint` = CI | the whole repo | fmt fixes, lint checks |
| `.githooks/pre-push` | every `git push` | `make lint` | check: a push never surprises CI |
| CI `lint` job | every PR to dev/main | `make lint` | check (required status) |

## Tool per file type
| Files | Fix (autofix hook, `make fmt`) | Check (`make lint`, CI) |
|---|---|---|
| `*.py` (backend, `.claude/`) | `ruff format`, `ruff check --fix` | `ruff format --check`, `ruff check`, then `mypy --strict` for `backend/src` |
| `frontend/**/*.{ts,tsx,js,jsx,json,css,md}` | `prettier --write`, `eslint --fix` (ts/tsx/js/jsx) | `prettier --check`, `eslint`, `tsc --noEmit` |
| `*.sh`, `.githooks/*` | none; shellcheck cannot fix | `shellcheck` |
| `*.yml` workflows | none | `actionlint` if installed (CI installs it) |

Ruff's configuration lives once, in the root `pyproject.toml` (the uv workspace root). Workspace members
inherit it. Don't add per-package ruff sections unless a member truly needs different rules; if one does,
record it as a decision.

## The autofix hook's contract
- **Never blocks.** It's PostToolUse and always exits 0. Remaining problems come back to Claude as
  `additionalContext`, with the tool's output. Fix them before committing.
- **Skips** `data/`, `backlog/` (CLI-owned), `.claude/learnings/INDEX.md` and `.claude/README.md`
  (generated), and anything outside the repo.
- **Degrades gracefully.** If a tool isn't available yet (no `frontend/node_modules`, uv not synced), it
  says so once and skips. It never fails an edit because the toolchain isn't set up.
- Formats **only the file that was edited**, so an edit never produces a sweeping diff across unrelated files.

## When lint fails
1. Run `make fmt`, then `make lint`. Most failures are gone after that.
2. For what remains, fix the code. Don't add `# noqa` or `eslint-disable` unless the rule is genuinely wrong
   for that line, and give the reason in the same comment.
3. A rule that is wrong for the whole repo gets changed in `pyproject.toml` / the eslint config in its own
   commit, with the reason in the commit message.

## Setup
`scripts/setup-dev.sh` (sets `core.hooksPath` so `.githooks/pre-push` and `commit-msg` run) and `uv sync` at
the repo root (installs ruff and mypy into the workspace venv). shellcheck: `brew install shellcheck`
(macOS) or `apt-get install shellcheck`.
