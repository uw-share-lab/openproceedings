---
name: repo-conventions
description: Where things live in the openproceedings monorepo and the naming rules for branches, commits, results, plans and data — the layout from spec 08, what is committed vs gitignored, and the files nobody hand-edits. Use when creating a file or directory, naming a branch or commit, deciding where a result or plan goes, or reviewing a diff for misplaced files.
---

# Repo conventions (spec 08 §Monorepo layout)

## Layout — put things where spec 08 says
| Path | Holds | Notes |
|---|---|---|
| `pyproject.toml`, `uv.lock` (root) | The **uv workspace** root: repo-wide ruff config, dev group (ruff, mypy), one lock | `uv sync` at the root; members join via `[tool.uv.workspace] members` |
| `Makefile` | `sync`, `fmt`, `lint`, `tooling`, `test`, `hooks` | `make lint` is exactly what CI and pre-push run |
| `.githooks/` | `commit-msg` (attribution), `pre-push` (`make lint` + `make tooling`) | Installed by `scripts/setup-dev.sh` |
| `.github/` | Workflows, `dependabot.yml` | Actions pinned by SHA |
| `backend/` (M1) | The uv workspace member, package `openproceedings` (`backend/pyproject.toml`) | |
| `backend/src/openproceedings/ingest/` | 01: `sources/`, `classify.py`, `dedup.py`, `snapshot.py`, `ris.py` | Only place that makes network calls |
| `backend/src/openproceedings/query/` | 02: `normalize.py`, `lexer.py`, `parser.py`, `ast.py`, `canonical.py`, `compat.py` | Pure; no I/O |
| `backend/src/openproceedings/engine/` | 03: `reference.py`, `tantivy_engine.py`, `compile.py`, `rank.py`, `highlight.py` | Pure except index file reads |
| `backend/src/openproceedings/api/` | 04: app, routers, `exporters/`, `records.py` | The only writer of `data/records.sqlite` |
| `backend/src/openproceedings/semantic/` | 06 (phase 2) | Never imported by `query/` or `engine/` matching code |
| `backend/src/openproceedings/eval/` | 07 report generators | Writes to `docs/results/` |
| `backend/src/openproceedings/diagnostics.py` | The error-code registry (`error-diagnostics`) | |
| `backend/src/openproceedings/logs.py` | The only place logging is configured (`logging-standards`) | |
| `backend/src/openproceedings/cli.py` | `op` entry point | Thin: calls the same functions as the API |
| `backend/tests/{unit,golden,differential,contract,fixtures}/` | Tests by kind (`testing-standards`) | |
| `frontend/` (M3) | 05: Next.js app, an npm workspace | `frontend/src/api/schema.ts` is generated |
| `docs/specs/` | `NN-name.md`, changed only by PR (`spec-writing`) | |
| `docs/{design,usability,research}/` | Created as needed | |
| `docs/plans/` | Implementation plans, `YYYY-MM-DD-<slug>.md` | |
| `docs/results/` | Dated reports, `YYYY-MM-DD-<slug>.md`, plus `coverage-sources.md` | Numbers live here, never in learnings |
| `backlog/` | Backlog.md store: tasks, completed, docs, decisions | CLI only (`decision-records`) |
| `.claude/` | Agents, skills, commands, hooks, learnings | Committed; linted by `lint_tooling.py`; roster in the generated `.claude/README.md` |
| `deploy/` | Dockerfiles, `compose.yml` | |
| `data/` | `cache/`, `snapshots/`, `indexes/`, `embeddings/`, `research/`, `records.sqlite` | **Gitignored. Never committed.** Snapshots and indexes are immutable |

## Never committed
`data/` in any form (no `git add -f data/`; `protect-data-dir.sh` blocks it), `.env` (OpenReview
credentials), the Hypothesis database `.hypothesis/`, review records (they live in `.git/op-reviews/`),
Covidence exports containing screening decisions, and anything with reviewer or participant personal data.
Test fixtures are the exception: small, hand-built or sampled records under `backend/tests/fixtures/`.

## Never hand-edited
- `backlog/**` task, draft, doc and milestone files (`enforce-backlog-cli.sh`). Decision **bodies** are the
  one exception.
- `frontend/src/api/schema.ts` — regenerate it from the OpenAPI schema.
- `.claude/learnings/INDEX.md` — regenerate with `python3 .claude/scripts/learnings_index.py`.
- `.claude/README.md` — regenerate with `python3 .claude/scripts/roster_index.py`.
- Review records — only `record-review.py` writes them.

## Names
- **Branches:** `<type>/<slug>`, where type ∈ `feat`, `fix`, `chore`, `docs`, `test`
  (e.g. `feat/wildcard-expansion-cap`). Never work on `dev` or `main` (`pr-workflow`).
- **Commits and PR titles:** `<type>: <imperative summary>` (`fix: keep NEAR within one field`), with a
  body that says *why*. No AI attribution (`no-ai-attribution`).
- **Dated files:** ISO date first, from the session's context date — never invented.
- **Python modules:** `snake_case.py`; one concept per module; tests mirror the module path.
- **People:** refer to roles ("the second reviewer", "the review lead"), never names, in code, docs,
  learnings and commit messages.

## Gotchas
- Decisions go through `backlog decision create` (`backlog/decisions/`); there is no `docs/decisions/`.
- A file that belongs to two areas goes where its *owning spec* puts it; import across, don't copy.
