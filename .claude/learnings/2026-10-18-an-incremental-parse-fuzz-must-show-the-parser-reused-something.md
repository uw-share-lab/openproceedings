# An incremental-parse fuzz passes vacuously unless it shows the parser reused something

**Key lesson:** a test that compares an incremental parse with a full parse must also assert that the incremental parse kept old subtrees, or a parse that reuses nothing passes it.

- **Date:** 2026-10-18 · **Task:** task-264 (with task-260, task-262, task-263) · **Area:** frontend | tooling
- **Artifacts:** `frontend/src/editor/lang/grammar.test.ts` ("holds over a long query under 200 seeded random edits"), `.claude/scripts/dependabot/npm_lock.py` (`OWNER_ACCEPTED`), `.claude/commands/dependabot-review.md` (step 5's port recipe, §10 "When the owner accepts a hard stop")

## What we set out to do
Four small follow-ups from the 2026-10-17/18 Dependabot batch (#161, #163, #165): a long-query incremental-reparse
test, an owner-decision allowlist for `npm_lock.py`, a free-port recipe that `make e2e` can't trip on, and two
stale version mentions.

## What we learned
- **Equal output doesn't show the incremental path ran.** With fragments built wrong, Lezer would simply parse
  from scratch and the comparison would still pass. Counting the steps where the new tree holds a child object
  of the old tree (identity, `Tree.children`) shows reuse: 199 of 200 steps keep one on the 12k-character golden
  query. The test requires more than 150. A deliberately wrong change map (the edit's range not mapped) fails at
  step 0 (evidence: a throwaway edit of the test, reverted).
- **Incremental isn't faster on this grammar's long query** (about 25 ms against 28 ms for a full parse of
  ~12k characters, local throwaway bench), so speed is no proof of reuse either. The 200 steps take about 5 s;
  the test has a 60 s timeout because `grammar.test.ts` has already flaked under load (TASK-182).
- **`toEqual` on ~1.6k tokens at every step was not the cost** (the parse is): a JSON-string compare first, with
  `toEqual` only to show a difference, changed nothing measurable, but keeps the failure message (the step and
  the edit) readable.
- **An owner's acceptance belongs to one package at one version.** `OWNER_ACCEPTED` keys on `name@version`, so a
  later version of the accepted package is a new package again, and an accepted package still goes through the
  registry checks (integrity, tarball, cooldown) like a changed entry. A row and a mutant pin each half.
- **Free ports picked one at a time collide with the e2e fixture server**, which also listens on API +1 and +2
  (`tight`, `plain`; TASK-182): `make e2e` failed with `EADDRINUSE` twice in the batch. Step 5 now picks an API
  port whose +1 and +2 are free and a web port 5 above it.

## Dead ends — don't repeat these
- Printing from a Vitest test through `console.log` and grepping the run's output showed nothing; throwing an
  `Error` with the numbers in its message was the quick way to read a throwaway benchmark.

## Decisions (and what would change them)
- 200 seeded edits, not the reviewer's 16k: deterministic and about 5 s. A grammar change that makes reuse
  context-dependent (a token that reads far ahead) is when to raise it.
- The allowlist lives in `npm_lock.py` itself, changed only through an ordinary PR into `dev`, because the
  checkers run from `dev`'s copy and a Dependabot PR may not touch tooling.

## Follow-ups
- [ ] none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/codemirror-lezer/SKILL.md` (Testing the grammar, item 3), `.claude/skills/testing-standards/SKILL.md` (e2e ports), `.claude/commands/dependabot-review.md` (step 5, §10, §11), `docs/specs/08-ops-and-tooling.md` (§Dependabot)
- Test or hook added? — the grammar test; three `dependabot_cases.py` rows and four mutants in `.claude/scripts/mutants/dependabot.json`
