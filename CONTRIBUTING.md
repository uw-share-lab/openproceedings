# Contributing to openproceedings

## Setup
To run the app (get data, build an index, start the API and UI), follow the README's
[Quickstart](README.md#quickstart). What follows is the contributor setup on top of it.
```bash
scripts/setup-dev.sh          # git hooks (.githooks: commit-msg, pre-push), executable tooling, .env skeleton
uv sync                       # the root uv workspace: backend package + dev tools (Python 3.12, pinned by .python-version)
uv run pytest                 # backend tests; `uv run op --help` for the CLI
npm ci --ignore-scripts       # the root npm workspace (frontend/); Node 22, pinned by .nvmrc
npm test --workspace frontend # frontend tests (Vitest); `npm run dev --workspace frontend` serves the UI
npm i -g backlog.md           # task tracking — https://github.com/MrLesk/Backlog.md
brew install shellcheck       # or apt-get install shellcheck — used by make lint
```
`make help` lists the entry points: `sync` runs `uv sync` and `npm ci --ignore-scripts`, `fmt` fixes the whole repo, `lint`
is exactly what CI checks (frontend included: prettier, eslint, `next typegen` + `tsc --noEmit`; it fails if
`node_modules/` is missing), `tooling` runs the roster, backlog and hook checks, and `openapi` regenerates
the API contract (below).

**Changed a route, a parameter or a response model? Run `make openapi` and commit both files it writes:**
`backend/tests/contract/openapi.json` (the OpenAPI snapshot, from `op openapi`) and
`frontend/src/api/schema.ts` (TypeScript types generated from it by `openapi-typescript`). Never edit either
by hand. The contract test (`test_openapi_snapshot.py`) and CI's `test` job both fail while they are stale,
and the snapshot diff is what a reviewer reads to classify the change (`.claude/skills/api-contract/SKILL.md`).
When branches that each change the API merge, rerun `make openapi` on the merge result rather than resolving
conflicts in the generated files by hand.
**Backend-only contributors need Node too:** the pre-push hook runs `make lint`, which checks `frontend/`,
so install Node 22 and run `npm ci --ignore-scripts` once even if you never touch the UI (no dependency's
install script runs; nothing here needs one).
Put OpenReview credentials in `.env` (gitignored) as `OPENREVIEW_USERNAME` and `OPENREVIEW_PASSWORD` (the
names `setup-dev.sh` writes; scholarmend's `SCHOLARMEND_OPENREVIEW_*` names are not read). Without them the
API answers every request with an HTML browser-check page instead of JSON (checked 2026-09-27).

## Flow: `feature → PR → dev → PR → main`
1. Pick or create a task: `backlog task list --plain`, `backlog task create "…" --ac "…"`.
   Never hand-edit files under `backlog/`.
2. Branch off `dev`: `git switch dev && git pull && git switch -c <type>/<slug>` (e.g. `feat/wildcard-expansion`; types: feat, fix, chore, docs, test).
3. Work test-first. Keep changes inside one spec's scope. If the spec is wrong, change the spec in the same PR.
4. Close out, in this order (approvals are per-commit, so the order matters):
   - the local tests the change calls for green (the `.claude/skills/pr-workflow/SKILL.md` §Local test runs
     table; often the full `make test`), plus `make lint` and `make tooling` → Backlog current (acceptance criteria ticked; finished
     tasks moved with `backlog task complete <id>`) → docs, specs and READMEs as-built in the same branch
   - `/record-learnings` → commit the entry and `INDEX.md`
   - `/review-gate`. Every finding gets a disposition: `fixed <sha>`, `task-NNN`, or `rejected: <reason>`.
     A must-fix can only be fixed, and every Should is fixed in the same round too. Only work that genuinely
     can't be done yet becomes a task, with the reason.
   - `/open-pr` (pushes, opens the PR into `dev`, attests the review).
5. CI must pass: `lint`, `test`, `claude-tooling`, `attribution`, `learnings`, `review-attested`.
   Merge into `dev` yourself once it's green.
6. Promote `dev → main` with a PR (`--base main --head dev`). It needs a second person's approval.

## Rules the tooling enforces
- **No AI authorship** in commits or PRs: no `Co-Authored-By: Claude` and no "Generated with …" footers.
  The `.claude/` tooling is committed, but people author the work.
- **`data/` is never committed.** Snapshots and indexes are immutable. Build new ones rather than editing.
- **Tests never call real APIs.** `backend/tests/conftest.py` refuses every non-loopback connection and DNS
  lookup (`NetworkBlockedError`); crawlers are tested against recorded fixtures.
- **Exactness is the product.** Any change to `query/` or `engine/` goes through `exactness-guardian`,
  and the differential suite (Tantivy vs the reference oracle) must stay green.

## Working without Claude Code
Every gate is also in git or CI:
- `.githooks/commit-msg` rejects attribution.
- The `pr-gates` workflow checks attribution, the learnings entry and the review attestation.
- Branch protection enforces the flow.
To run a review round by hand, do what `.claude/commands/review-gate.md` describes, then record it with
`python3 .claude/scripts/record-review.py`.
