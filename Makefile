# openproceedings monorepo — common entry points. Standard: .claude/skills/autolint/SKILL.md
.PHONY: help sync frontend-deps fmt lint tooling test e2e openapi hooks mutate mutate-changed

SHELL_FILES := $(wildcard .claude/hooks/*.sh .claude/hooks/tests/*.sh .claude/scripts/tests/*.sh scripts/*.sh .githooks/*)
PY_TARGETS  := .claude $(wildcard backend)

help:
	@echo "sync     - uv sync (root uv workspace) + npm ci (root npm workspace: frontend/)"
	@echo "fmt      - auto-format and auto-fix everything (ruff, prettier, eslint)"
	@echo "lint     - check-only: what CI's lint job runs (ruff, mypy, shellcheck, frontend)"
	@echo "tooling  - roster lint, roster/learnings indexes, backlog hygiene, hook case tables"
	@echo "test     - backend (pytest) and frontend (vitest) tests"
	@echo "e2e      - Playwright spec-05 flow, WCAG 2.2 AA and visual regression"
	@echo "openapi  - regenerate the OpenAPI snapshot and frontend/src/api/schema.ts (commit both; CI checks)"
	@echo "hooks    - install git hooks (commit-msg, pre-push) via scripts/setup-dev.sh"
	@echo "mutate   - mutation-test every gate check in parallel (nightly CI; after changing a gate)"
	@echo "mutate-changed - only mutants in files changed vs origin/dev (what reviews run)"

# The npm workspace root is the repo root (package.json, package-lock.json); dependencies are hoisted to
# ./node_modules. Once frontend/ exists, its checks never skip silently: a missing install is an error.
frontend-deps:
	@if [ -f frontend/package.json ] && [ ! -d node_modules ]; then \
	  echo "frontend/ exists but node_modules/ does not: run make sync (npm ci)"; exit 1; fi

# --ignore-scripts: no dependency install script runs (only unrs-resolver and the optional fsevents have one,
# and lint, tests and the build pass without them); CI installs the same way.
sync:
	uv sync --locked
	@if [ -f package-lock.json ]; then npm ci --ignore-scripts; fi

fmt: frontend-deps
	uv run --locked ruff format $(PY_TARGETS)
	uv run --locked ruff check --fix $(PY_TARGETS)
	@if [ -f frontend/package.json ]; then cd frontend && npx --no-install prettier --write . && npx --no-install eslint --fix .; fi

lint: frontend-deps
	uv run --locked ruff format --check $(PY_TARGETS)
	uv run --locked ruff check $(PY_TARGETS)
	@if [ -d backend/src ]; then uv run --locked mypy --strict backend/src; fi
	shellcheck -x $(SHELL_FILES)
	@# next typegen writes the route types (PageProps, LayoutProps) that tsc needs; it reads only src/app
	@if [ -f frontend/package.json ]; then cd frontend && npx --no-install prettier --check . && npx --no-install eslint . \
	  && npx --no-install next typegen >/dev/null && npx --no-install tsc --noEmit; fi

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

test: frontend-deps
	@if [ -d backend ]; then uv run --locked pytest -q; fi
	@if [ -f frontend/package.json ]; then npm test --workspace frontend; fi

e2e: frontend-deps
	@if [ -f frontend/package.json ]; then npm run e2e --workspace frontend; fi

# The API contract (api-contract skill): the committed OpenAPI snapshot, then the TypeScript types generated
# from it. Run after any change to a route or a response model; CI's test job runs it and fails on a diff.
openapi: frontend-deps
	uv run --locked op openapi --out backend/tests/contract/openapi.json
	npm run --silent gen:api --workspace frontend

hooks:
	scripts/setup-dev.sh

mutate:
	python3 .claude/scripts/mutate.py

mutate-changed:
	python3 .claude/scripts/mutate.py --changed
