# README.md went a milestone stale because no diff touched it

**Key lesson:** A reviewer that checks only the docs a diff touches never looks at a README nobody edits. Give README.md an unconditional check on every diff (its Status and Quickstart against the change), and run every Quickstart command when you write it.

- **Date:** 2026-09-29 · **Task:** task-120 · **Area:** tooling
- **Artifacts:** `README.md` (§Status, §Quickstart), `.claude/agents/docs-reviewer.md` (step 10), `.claude/skills/task-hygiene/SKILL.md`

## What we set out to do
Give README.md setup and run instructions, as the owner asked, and bring its status line up to date.

## What we learned
- On 2026-09-29 README.md had no setup or run instructions, only a link to CONTRIBUTING.md. Its status said "the UI is under way … pages still placeholders", though M3b had built them (TASK-041 to TASK-045), and it didn't mention the M4 crawlers or `op eval coverage` (evidence: `git show origin/dev:README.md` before this change).
- The task-hygiene rule already covered READMEs. `docs-reviewer` greps for the docs that describe each changed path, but a status line describes no path, so it was never pulled in.
- Writing the Quickstart from memory would have shipped four errors, all caught by running or grepping each step. Three spec links were wrong (the files are `03-search-engine.md`, `04-backend-api.md`, `05-frontend.md`). The health route is `/api/v1/healthz`, not `/health`. `current` must resolve to an index directory directly under `indexes/`: `state.index_path` refuses anything else (`outside_indexes`). And a plain `ln -s` onto an existing `current` puts the new link inside the old index directory, silently leaving `current` where it was, so a re-promotion needs `ln -sfn`. `NEXT_PUBLIC_API_BASE_URL` is compiled in at build time, so it has to be set before `npm run build`.

## Dead ends — don't repeat these
- Checking "does `make e2e` exist" by listing targets with `^[a-zA-Z_-]+:` looked like a miss, but the target is `e2e: frontend-deps`. Grep for the target name directly.

## Decisions (and what would change them)
- README keeps the run path (data → snapshot → index → current → API → UI). CONTRIBUTING keeps contributor setup and the workflow, and links to the Quickstart. Production deployment is described as planned (M6, TASK-065) until `deploy/` exists.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/agents/docs-reviewer.md` (step 10: README on every diff), `.claude/skills/task-hygiene/SKILL.md` (the README row and note), `CLAUDE.md` (Makefile targets), `CONTRIBUTING.md` (link to the Quickstart)
- Test or hook added? — no: the check is a reviewer step, and a Quickstart can't be run in CI without network and hours of crawling
