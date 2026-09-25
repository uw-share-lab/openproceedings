---
description: Security review of the current branch or a named scope — OpenReview credential leaks, crawler SSRF/redirect/rate-limit handling, FastAPI input limits, injection, dependency and CI/deploy changes, hook anti-evasion — via the security-reviewer agent
argument-hint: "(optional) paths or a diff range; default: origin/dev...HEAD"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Spawn `.claude/agents/security-reviewer.md` on `$ARGUMENTS` — or, if empty, on
`git diff origin/dev...HEAD`. Give it the changed-path list and the specs that own them
(`docs/specs/01-ingestion.md` for `ingest/`, `docs/specs/04-backend-api.md` for `api/`,
`docs/specs/08-ops-and-tooling.md` for hooks, CI and deploy).

It must:
1. Grep the whole tree (not just the diff) for credential handling: OpenReview creds come only from
   `.env`, never reach logs, errors, the disk cache or recorded HTTP fixtures; `.env` and `data/` are not
   staged (`git status --porcelain`, `git diff --cached --name-only`).
2. Check crawlers for host allowlisting, redirect caps with auth stripped cross-host, `Retry-After`
   honoured with bounded retries, and no anonymous fallback.
3. Check the API for `limit ≤ 200`, query-length/wildcard/NEAR bounds, parameterised SQLite, CORS from
   config, and no raw query text in logs by default.
4. Review any dependency, lockfile, workflow or `deploy/` change.
5. If `.claude/hooks/` changed, run `for t in .claude/hooks/tests/*.sh; do bash "$t"; done` and check the
   change does not widen evasion.

Report its findings in the `.claude/skills/review-gates/SKILL.md` contract (Must / Should / Nit,
`file:line — risk — fix`) and the verdict **APPROVE** / **REQUEST CHANGES**. Findings from a standalone
run still need dispositions if they are carried into `/review-gate`.
