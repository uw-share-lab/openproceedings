---
name: repo-conventions
description: Where things live in the openproceedings monorepo and the naming rules for branches, commits, results, plans and data — the layout from spec 08, what is committed vs gitignored, and the files nobody hand-edits. Use when creating a file or directory, naming a branch or commit, deciding where a result or plan goes, or reviewing a diff for misplaced files.
---

# Repo conventions (spec 08 §Monorepo layout)

## Layout — put things where spec 08 says
| Path | Holds | Notes |
|---|---|---|
| `pyproject.toml`, `uv.lock` (root) | The **uv workspace** root: repo-wide ruff config, dev group (ruff, mypy), one lock | `uv sync` at the root; members join via `[tool.uv.workspace] members` |
| `Makefile` | `sync`, `fmt`, `lint`, `tooling`, `test`, `e2e`, `openapi`, `changelog`, `hooks`, `mutate`, `mutate-changed` | `make lint` is exactly CI's `lint` job; pre-push runs `make lint` + `make tooling` |
| `.githooks/` | `commit-msg` (attribution), `pre-push` (`make lint` + `make tooling`) | Installed by `scripts/setup-dev.sh` |
| `.github/` | Workflows, `dependabot.yml` | Actions pinned by SHA; Dependabot never bumps `tantivy` (spec 08 §Release) |
| `backend/` (M1) | The uv workspace member, package `openproceedings` (`backend/pyproject.toml`) | |
| `backend/src/openproceedings/ingest/` | 01: `record.py`, `classify.py`, `urls.py`, `volumes.py` (+ `pmlr_volumes.toml`, the PMLR volume table), `ris.py`, `dedup.py`, `snapshot.py`; `sources/` (M4 crawlers: `http.py` the one HTTP layer, `common.py`, `openreview_client.py`, `openreview_v2.py`, `openreview_v1.py`, `neurips.py`, `pmlr.py`, `crawl.py`) | Only place that makes network calls (`sources/http.py`, for every crawler) |
| `backend/src/openproceedings/query/` | 02: `normalize.py`, `mathsyms.py`, `lexer.py`, `parser.py`, `ast.py`, `canonical.py`, `defaults.py`, `compat.py` | Pure; no I/O |
| `backend/src/openproceedings/engine/` | 03: `protocol.py`, `reference.py`, `index.py`, `compile.py`, `tantivy_engine.py` (ranking included), `exclusions.py`, `highlight.py`, `parity.py` | Pure except index file reads |
| `backend/src/openproceedings/api/` | 04: `app.py`, `config.py`, `state.py`, `deps.py`, `errors.py`, `middleware.py`, `models.py` (the contract), `openapi.py`, `server.py`; routers `search.py`, `papers.py`, `meta.py`, `coverage.py`, `records.py`, `export.py`, `health.py` | Transport only: routes call the package-level functions below |
| `backend/src/openproceedings/semantic/` | 06 (deferred: phase 2, decision-017; not created) | Never imported by `query/` or `engine/` matching code |
| `backend/src/openproceedings/eval/` | 07 report generators | Writes to `docs/results/` |
| `backend/src/openproceedings/diagnostics.py` | The error-code registry (`error-diagnostics`) | |
| `backend/src/openproceedings/vocab.py` | Venue, track and status vocabularies (spec 01), shared by ingest and the query language | Pure |
| `backend/src/openproceedings/logs.py` | The only place logging is configured (`logging-standards`) | |
| `backend/src/openproceedings/storage.py` | Locks, staging, fsync and read-only sealing (`snapshots`, `tantivy-indexing`) | The only code that places or seals `data/` directories |
| `backend/src/openproceedings/export.py` | 04 exports (RIS, CSV, BibTeX, JSONL) | Shared by `op export` and the API (task-036) |
| `backend/src/openproceedings/search.py` | One ranked search | Run by `op search` and `GET /search` alike |
| `backend/src/openproceedings/records.py` | Search records: `ids_hash`, the append-only store, replay | The only writer of `data/records/records.sqlite` |
| `backend/src/openproceedings/coverage.py` | The snapshot manifest's venue × year × track × status breakdown | Never recounts |
| `backend/src/openproceedings/timestamps.py` | The API's one timestamp form (UTC RFC 3339, `Z`) | |
| `backend/src/openproceedings/cli.py` | `op` entry point | Thin: calls the same functions as the API |
| `backend/tests/{unit,golden,differential,bench,contract,e2e,deploy,fixtures}/` | Tests by kind (`testing-standards`); `e2e/fixture_server.py` serves the temporary 5k browser fixture; `deploy/fixture_data.py` writes the deploy smoke test's data directory | |
| `frontend/` (M3) | 05: Next.js app, an npm workspace | `frontend/src/api/schema.ts` is generated |
| `frontend/e2e/` | Playwright full-stack, accessibility and visual tests; platform-specific baselines in `__screenshots__/` | Run with `make e2e` |
| `CHANGELOG.md` (root) | Release notes, generated from merged PRs by `.claude/scripts/changelog.py` (`make changelog`) | Spec 08 §Release, decision-023 |
| `docs/releases.toml` | Each release's data: the `index_version` it was verified on, its snapshot hash, the three versions | Read by `changelog.py`; a released table is never edited |
| `docs/specs/` | `NN-name.md`, changed only by PR (`spec-writing`) | |
| `docs/{design,usability,research}/` | Created as needed | |
| `docs/plans/` | Implementation plans, `YYYY-MM-DD-<slug>.md` | |
| `docs/results/` | Dated reports, `YYYY-MM-DD-<slug>.md`, plus `coverage-sources.md` | Numbers live here, never in learnings |
| `backlog/` | Backlog.md store: tasks, completed, docs, decisions | CLI only (`decision-records`) |
| `.claude/` | Agents, skills, commands, hooks, learnings | Committed; linted by `lint_tooling.py`; roster in the generated `.claude/README.md` |
| `deploy/` | Dockerfiles, `compose.yml` | Every image a build pulls (`FROM`, `# syntax=`, `COPY --from=`, `RUN --mount` `from=`) is `name:tag@sha256:<multi-arch index digest>` (spec 08 §Deploy; `check_digest_pins.py` in `make tooling`); Dependabot's `docker` entry bumps the `FROM` digests |
| `data/` | `cache/`, `snapshots/`, `indexes/`, `embeddings/`, `research/`, `records/` (`records.sqlite`) | **Gitignored. Never committed.** Snapshots and indexes are immutable |

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
- `CHANGELOG.md` — regenerate with `make changelog` (spec 08 §Release).
- Review records — only `record-review.py` writes them.

## Names
- **Branches:** `<type>/<slug>`, where type ∈ `feat`, `fix`, `chore`, `docs`, `test`
  (e.g. `feat/wildcard-expansion-cap`), plus `release/X.Y.Z` and `release/X.Y.Z-back-merge` for a release's
  own bookkeeping only (spec 08 §Release; `changelog.py` leaves them out). Never work on `dev` or `main`
  (`pr-workflow`).
- **Commits and PR titles:** `<type>: <imperative summary>` (`fix: keep NEAR within one field`), with a
  body that says *why*. No AI attribution (`no-ai-attribution`).
- **Dated files:** ISO date first, from the session's context date — never invented.
- **Python modules:** `snake_case.py`; one concept per module; tests mirror the module path.
- **People:** refer to roles ("the second reviewer", "the review lead"), never names, in code, docs,
  learnings and commit messages.

## Gotchas
- Decisions go through `backlog decision create` (`backlog/decisions/`); there is no `docs/decisions/`.
- A file that belongs to two areas goes where its *owning spec* puts it; import across, don't copy.
