# openproceedings monorepo — common entry points. Standard: .claude/skills/autolint/SKILL.md
.PHONY: help sync fmt lint tooling test hooks mutate mutate-changed

SHELL_FILES := $(wildcard .claude/hooks/*.sh .claude/hooks/tests/*.sh .claude/scripts/tests/*.sh scripts/*.sh .githooks/*)
PY_TARGETS  := .claude $(wildcard backend)

help:
	@echo "sync     - uv sync (root workspace) + npm ci (frontend, once it exists)"
	@echo "fmt      - auto-format and auto-fix everything (ruff, prettier, eslint)"
	@echo "lint     - check-only: what CI's lint job runs (ruff, mypy, shellcheck, frontend)"
	@echo "tooling  - roster lint, roster/learnings indexes, backlog hygiene, hook case tables"
	@echo "test     - backend and frontend tests"
	@echo "hooks    - install git hooks (commit-msg, pre-push) via scripts/setup-dev.sh"
	@echo "mutate   - mutation-test every gate check in parallel (nightly CI; after changing a gate)"
	@echo "mutate-changed - only mutants in files changed vs origin/dev (what reviews run)"

sync:
	uv sync --locked
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi

fmt:
	uv run --locked ruff format $(PY_TARGETS)
	uv run --locked ruff check --fix $(PY_TARGETS)
	@if [ -d frontend/node_modules ]; then cd frontend && npx --no-install prettier --write . && npx --no-install eslint --fix .; fi

lint:
	uv run --locked ruff format --check $(PY_TARGETS)
	uv run --locked ruff check $(PY_TARGETS)
	@if [ -d backend/src ]; then uv run --locked mypy --strict backend/src; fi
	shellcheck -x $(SHELL_FILES)
	@if [ -d frontend/node_modules ]; then cd frontend && npx --no-install prettier --check . && npx --no-install eslint . && npx --no-install tsc --noEmit; fi

tooling:
	python3 .claude/scripts/lint_tooling.py
	python3 .claude/scripts/roster_index.py --check
	python3 .claude/scripts/learnings_index.py --check
	python3 .claude/scripts/check_backlog.py
	@# case tables run in parallel; each writes its output to a temp file, and any failure prints in full
	@d=$$(mktemp -d); pids=""; for t in .claude/hooks/tests/*.sh .claude/scripts/tests/*.sh; do \
	  ( bash "$$t" > "$$d/$$(basename $$t).out" 2>&1; echo $$? > "$$d/$$(basename $$t).rc" ) & pids="$$pids $$!"; done; \
	  wait $$pids; rc=0; for f in "$$d"/*.rc; do n=$$(basename "$$f" .rc); \
	  if [ "$$(cat "$$f")" != 0 ]; then cat "$$d/$$n.out"; rc=1; else echo "$$n: $$(tail -1 "$$d/$$n.out")"; fi; done; rm -rf "$$d"; exit $$rc

test:
	@if [ -d backend ]; then uv run --locked pytest -q; fi
	@if [ -f frontend/package.json ]; then cd frontend && npm test -- --run; fi

hooks:
	scripts/setup-dev.sh

mutate:
	python3 .claude/scripts/mutate.py

mutate-changed:
	python3 .claude/scripts/mutate.py --changed
