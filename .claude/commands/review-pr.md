---
description: Whole-PR review before merge — fold every routed reviewer's verdict, check scope, base branch, PR body sections, the op-review attestation for the head sha and the learnings entry — via the pr-reviewer agent
argument-hint: "(optional) PR number; default: the current branch vs origin/dev"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Review pull request `$ARGUMENTS` (or, if empty, the current branch against `origin/dev`) as a whole,
following `.claude/skills/review-gates/SKILL.md`.

1. **Gather.** `gh pr view $ARGUMENTS --json number,title,body,baseRefName,headRefOid,labels` and
   `gh pr diff $ARGUMENTS --name-only` (or `git diff --name-only origin/dev...HEAD`).
2. **Route.** Apply the routing table to the changed paths. If the PR body's **Review** section does not
   already show a verdict for the head sha from every routed reviewer, spawn the missing ones in parallel
   (always `.claude/agents/code-reviewer.md`; plus e.g. `.claude/agents/security-reviewer.md` for
   `ingest/`/`api/`/hooks/lockfiles, `.claude/agents/exactness-guardian.md` for `query/`/`engine/`).
3. **Fold.** Spawn `.claude/agents/pr-reviewer.md` with the PR number, the changed-path list, the routed
   reviewer set, and every reviewer's output. It checks base (`feature → dev`, `dev → main` only), scope
   vs the Backlog task and spec, the body sections `/open-pr` writes (Summary, Spec(s), Tests, Review,
   Learnings), the `<!-- op-review: <sha> APPROVE -->` line against `headRefOid`, the learnings entry, and
   AI attribution.
4. **Report** the routed-reviewer → verdict table, consolidated Must / Should / Nit (`file:line —
   problem — fix`), and the verdict **APPROVE** / **REQUEST CHANGES**. For REQUEST CHANGES, say which
   step fixes it (`/review-gate` again for a stale sha, `/record-learnings` for a missing entry, editing
   the body for a missing section). Do not post anything to GitHub unless asked.
