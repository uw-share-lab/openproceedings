# Contributing to openproceedings

## Setup
```bash
scripts/setup-dev.sh          # git hooks (.githooks), executable tooling, .env skeleton
npm i -g backlog.md           # task tracking — https://github.com/MrLesk/Backlog.md
```
Put OpenReview credentials in `.env` (gitignored). The anonymous API rate-limits almost immediately.

## Flow: `feature → PR → dev → PR → main`
1. Pick or create a task: `backlog task list --plain`, `backlog task create "…" --ac "…"`.
   Never hand-edit files under `backlog/`.
2. Branch off `dev`: `git switch dev && git pull && git switch -c <initials>/<area>-<topic>`.
3. Work test-first. Keep changes inside one spec's scope. If the spec is wrong, change the spec in the same PR.
4. Close out, in this order (approvals are per-commit, so the order matters):
   - tests green → Backlog updated → docs as-built
   - `/record-learnings` → commit the entry and `INDEX.md`
   - `/review-gate`. Every finding gets a disposition: `fixed <sha>`, `task-NNN`, or `rejected: <reason>`.
     A must-fix can only be fixed.
   - `/open-pr` (pushes, opens the PR into `dev`, attests the review).
5. CI must pass: `lint`, `test`, `claude-tooling`, `attribution`, `learnings`, `review-attested`.
   Merge into `dev` yourself once it's green.
6. Promote `dev → main` with a PR (`--base main --head dev`). It needs a second person's approval.

## Rules the tooling enforces
- **No AI authorship** in commits or PRs: no `Co-Authored-By: Claude` and no "Generated with …" footers.
  The `.claude/` tooling is committed, but people author the work.
- **`data/` is never committed.** Snapshots and indexes are immutable. Build new ones rather than editing.
- **Exactness is the product.** Any change to `query/` or `engine/` goes through `exactness-guardian`,
  and the differential suite (Tantivy vs the reference oracle) must stay green.

## Working without Claude Code
Every gate is also in git or CI:
- `.githooks/commit-msg` rejects attribution.
- The `pr-gates` workflow checks attribution, the learnings entry and the review attestation.
- Branch protection enforces the flow.
To run a review round by hand, do what `.claude/commands/review-gate.md` describes, then record it with
`python3 .claude/scripts/record-review.py`.
