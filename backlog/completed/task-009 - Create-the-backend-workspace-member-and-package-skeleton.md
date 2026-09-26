---
id: TASK-009
title: Create the backend workspace member and package skeleton
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:19'
labels:
  - backend
  - ops
milestone: m-1
dependencies:
  - TASK-008
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
backend/ as a uv workspace member with the openproceedings package, `op` entry point, logs.py and diagnostics.py (spec 08 layout).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 backend/pyproject.toml added to [tool.uv.workspace] members; uv sync at root installs it
- [x] #2 `op --help` lists the planned subcommands as stubs
- [x] #3 logs.py configures JSON logging per the logging-standards skill; diagnostics.py holds the code registry
- [x] #4 mypy --strict and ruff pass; pytest runs an empty suite in CI with the ci Hypothesis profile
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
TDD: tests for cli stubs, JSON logging, diagnostics registry first; then backend/ uv member (src layout, op entry point), root workspace members + pytest/hypothesis dev deps + mypy strict config, Hypothesis profiles in conftest, CI green.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
backend/ is a uv workspace member (package openproceedings, Python 3.12). op CLI with all 10 planned subcommands as stubs naming their tasks (exit 2). logs.py: JSON (or text) logging configured only here: event constants, structured fields, query-text redaction by default, secrets always redacted, contextvars bind(). diagnostics.py: Diagnostic model (frozen, half-open code-point spans) and the code registry with spec 04 HTTP statuses. 49 tests; mypy --strict and ruff clean; pytest runs with the ci Hypothesis profile.
<!-- SECTION:FINAL_SUMMARY:END -->
