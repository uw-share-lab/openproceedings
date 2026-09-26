# Contributing to openproceedings

## Setup
```bash
scripts/setup-dev.sh          # git hooks (.githooks: commit-msg, pre-push), executable tooling, .env skeleton
uv sync                       # the root uv workspace: backend package + dev tools (Python 3.12, pinned by .python-version)
uv run pytest                 # backend tests; `uv run op --help` for the CLI
npm i -g backlog.md           # task tracking — https://github.com/MrLesk/Backlog.md
brew install shellcheck       # or apt-get install shellcheck — used by make lint
```
`make help` lists the entry points: `fmt` fixes the whole repo, `lint` is exactly what CI checks, and
`tooling` runs the roster, backlog and hook checks.
Put OpenReview credentials in `.env` (gitignored). The anonymous API rate-limits almost immediately.

## Flow: `feature → PR → dev → PR → main`
1. Pick or create a task: `backlog task list --plain`, `backlog task create "…" --ac "…"`.
   Never hand-edit files under `backlog/`.
2. Branch off `dev`: `git switch dev && git pull && git switch -c <type>/<slug>` (e.g. `feat/wildcard-expansion`; types: feat, fix, chore, docs, test).
3. Work test-first. Keep changes inside one spec's scope. If the spec is wrong, change the spec in the same PR.
4. Close out, in this order (approvals are per-commit, so the order matters):
   - `make test`, `make lint` and `make tooling` green → Backlog current (acceptance criteria ticked; finished
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
