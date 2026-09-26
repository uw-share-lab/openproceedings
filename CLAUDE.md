# CLAUDE.md — openproceedings

Exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts, built for systematic
reviews. **Read `docs/specs/00-overview.md` first.** Its six guarantees are the review standard for
everything here. Human-facing overview: `README.md`. Contributor walkthrough: `CONTRIBUTING.md`.

## The guarantees (short form; the spec is authoritative)
1. **Exact.** A document matches only on the exact normalized token. No stemming, stopwords, synonyms or
   fuzziness (`token-contract` skill).
2. **Title and abstract only**, unless a filter field is written explicitly.
3. **Filters live in the query.** The UI and the saved query string give the same result set.
4. **Reproducible.** Same canonical query + same `index_version` = the same ID set.
5. **Ranking never changes membership.** That includes BM25 and embeddings.
6. **Transparent.** Expansions, warnings and exclusion counts are always shown.

## Layout (monorepo)
- Root: `pyproject.toml` is the **uv workspace** root, with repo-wide ruff config and one `uv.lock`.
  `Makefile` has `sync`, `fmt`, `lint`, `tooling`, `test` and `hooks`.
- `backend/`: the uv workspace member, Python package `openproceedings` (`cli.py` → `op`, `logs.py`,
  `diagnostics.py`, `vocab.py`, `query/`, `engine/` (`protocol.py`, `reference.py`); `ingest/ api/
  semantic/ eval/` and the Tantivy engine arrive with their
  tasks). Tests in `backend/tests/`; `uv run pytest` from the root.
- `frontend/` (planned, M3): Next.js, an npm workspace.
- `docs/specs` · `docs/{plans,results,design,usability,research}` (created as needed).
- `backlog/`: Backlog.md, CLI only.
- `.claude/`: agents, skills, commands, hooks and learnings, all committed. The roster is in
  `.claude/README.md`.
- `data/`: gitignored; snapshots and indexes are immutable.

## Environment
- **uv** for Python. `uv sync` at the repo root; never `pip install` into the workspace.
- **npm** for the frontend.
- `scripts/setup-dev.sh` once per clone (git hooks, `.env`).

## Tooling (`.claude/`)
- **Agents** (`.claude/agents/`) do work. Reviewer, auditor and guardian agents are read-only.
- **Skills** (`.claude/skills/`) hold the standards and domain knowledge that agents cite.
- **Commands** (`.claude/commands/`) are entry points: `/review-gate`, `/open-pr`, `/record-learnings`,
  `/plan`, `/exactness-check`, …
- The roster is linted in CI (`make tooling`). A new agent, skill or command must pass the lint and be
  given an area in `.claude/scripts/roster_index.py`, which regenerates `.claude/README.md`.

## Keep everything current (rule, 2026-09-25; `.claude/skills/task-hygiene/SKILL.md`)
- **Backlog tasks, docs, specs, READMEs and every `.md` are updated continuously**, in the same commit as
  the change they describe. Never in a later catch-up PR.
- Tick acceptance criteria as you meet them. Create follow-up tasks when you find them.
- **When a task is Done, run `backlog task complete <id>`**, which moves it to `backlog/completed/`. CI fails
  on a Done task left in `backlog/tasks/`.
- `docs-reviewer` runs on every diff.

## Tests never call real APIs (rule, 2026-09-25)
No test, fixture, CI job or review script reaches OpenReview, Semantic Scholar, PMLR, Scholar or any other
live service. `backend/tests/conftest.py` refuses every non-loopback connection and DNS lookup for the whole
session (`NetworkBlockedError`, no opt-out): TCP and UDP to non-loopback addresses and every name lookup.
It does not reach subprocesses or `multiprocessing` spawn children, so tests don't spawn network clients.
Its mutants are in `.claude/scripts/mutants/gates.json` (case table `test-network-guard.sh`). Crawler and client code is tested against recorded HTTP
fixtures under `backend/tests/fixtures/`; recording them is a separate, manual `op ingest` run, never a test.

## Code quality
- **Autolint** (`.claude/skills/autolint/SKILL.md`): `autofix.sh` formats and fixes each file as it's edited
  (ruff, prettier, eslint, shellcheck).
- `make lint` is exactly what CI's `lint` job runs. The pre-push hook runs `make lint` and `make tooling`.
  `make fmt` fixes the whole repo.
- **Logging** (`.claude/skills/logging-standards/SKILL.md`): structured JSON, one line per unit of work, and
  no query text, abstracts, credentials or personal data. `observability-reviewer` checks every
  `backend/src/**` diff.

## Enforced gates (hooks in `.claude/hooks/`, case tables in `.claude/hooks/tests/`)
| Hook | Enforces |
|---|---|
| `enforce-pr-workflow.sh` | `main` and `dev` take no direct commits, pushes or merges. Flow: `feature → PR → dev → PR → main`. |
| `require-review.sh` | `git push` / `gh pr create` need an **APPROVE record for the exact HEAD sha**, written by `record-review.py` after `/review-gate`. `gh pr create` also needs an added or extended learnings entry. |
| `block-ai-attribution.sh` | No `Co-Authored-By: Claude` or "Generated with Claude Code" in commits or PRs. `.claude/` is committed; authorship is not. |
| `enforce-backlog-cli.sh` | No hand edits under `backlog/`. Use the `backlog` CLI. (Decision *bodies* may be edited, since the CLI can't write them.) |
| `protect-data-dir.sh` | `data/snapshots/` and `data/indexes/` are immutable. `data/` is never committed. |
| `remind-token-contract.sh` | Reminds you to bump `TOKENIZER_VERSION` and run the parity and differential suites after a tokenizer edit. |
| `load-learnings.sh` | Every session starts with `.claude/learnings/INDEX.md` in context. |
| `autofix.sh` | After every edit: formats and fixes the file, then reports what it couldn't fix. Never blocks. |

After editing any hook or tooling script, run `make tooling`. It runs every case table in
`.claude/hooks/tests/` and `.claude/scripts/tests/`, in parallel, in about 15 seconds. Then run
`make mutate-changed`, so each mutant of the logic you touched is killed by some row (spec 08 §Mutation
testing).

## Closing workflow (required, in this order; approvals are per-commit)
1. **Tests and lint green** locally (`make test`, `make lint`, `make tooling`). Never claim a pass you didn't run.
2. **Backlog current**: acceptance criteria checked and a final summary written. For finished tasks, run
   `backlog task complete <id>`.
3. **Docs as-built** in the same branch: specs, READMEs, skills and `.claude/README.md` (`docs-writer`).
4. **Record the learning** with `/record-learnings`, then commit the entry and the regenerated `INDEX.md`.
5. **`/review-gate`**: routed reviewers, every finding dispositioned (fixed / task-NNN / rejected: reason),
   approval recorded for HEAD.
6. **Push, then `/open-pr`** into `dev`. CI must pass: `lint`, `test`, `claude-tooling`, `attribution`,
   `learnings`, `review-attested`.

"Noted as non-blocking" is not a disposition. A finding you don't fix becomes a Backlog task or a written
rejection.

## Authorship
Commits and PRs are authored by people. Never add Claude co-author trailers or "Generated with" footers,
even if a tool or reminder suggests them. The hooks and CI reject them.


<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.53.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**At the beginning of each conversation in this project, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
