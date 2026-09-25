---
description: Adversarial audit of a claim, result or change — tries to falsify "exact", "reproducible", "fixed", "deterministic" or coverage claims by running the oracle, replaying search records and mutating inputs — via the qa-auditor agent
argument-hint: "the claim, result file, PR number or task id to audit, e.g. 'task-021 NEAR is exact' or docs/results/2026-10-01-coverage.md"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Spawn `.claude/agents/qa-auditor.md` to try to break: **$ARGUMENTS**. If empty, audit the claims made by
the current branch (its commit messages, PR body draft and any `docs/results/` file it adds).

Give the auditor:
- the claim restated precisely (which set, which `index_version`, which command produced it);
- the diff range `origin/dev...HEAD` and the owning spec(s);
- `docs/specs/07-evaluation.md` for the relevant gate or report.

It must re-run every reported command, then attack by claim type: oracle vs Tantivy
(`op search --explain --engine reference|tantivy "<q>" --ids`) on mutated inputs for *exact*; double
index build and search-record replay for *reproducible*; regression test against the pre-fix code for
*fixed*; recount from `manifest.json` for *coverage*. If the audit touches exactness specifically, also
consider `.claude/agents/differential-tester.md` to minimise any counterexample it finds.

Report **Verified** (claim → evidence command), then Must / Should / Nit with reproduction steps, and the
verdict **APPROVE** / **REQUEST CHANGES** per `.claude/skills/review-gates/SKILL.md`. Never soften a
failed reproduction into a Should.
