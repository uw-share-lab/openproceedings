---
id: TASK-009
title: Create the backend workspace member and package skeleton
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
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
- [ ] #1 backend/pyproject.toml added to [tool.uv.workspace] members; uv sync at root installs it
- [ ] #2 `op --help` lists the planned subcommands as stubs
- [ ] #3 logs.py configures JSON logging per the logging-standards skill; diagnostics.py holds the code registry
- [ ] #4 mypy --strict and ruff pass; pytest runs an empty suite in CI with the ci Hypothesis profile
<!-- AC:END -->
