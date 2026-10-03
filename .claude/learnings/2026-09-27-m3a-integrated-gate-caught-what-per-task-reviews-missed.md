# The integrated M3a gate caught cross-task bugs that every per-task review had passed

**Key lesson:** When tasks run in parallel worktrees, per-task reviews only see their own seam; run one integrated review gate over the merged milestone before any contract freezes, and reserve Backlog task and decision ids centrally, because parallel `backlog … create` calls collide.

- **Date:** 2026-09-27 · **Task:** M3a (task-034–040, 073, 075, 078, 080; gate branch `feat/m3a-api`) · **Area:** api
- **Artifacts:** 37b8916 (TASK-078 → TASK-080 renumber), 610f193 and 6edb001 (`.claude/worktrees/` skipped by tooling), 6ca7451 (BibTeX `@`, bootstrap citability), f424b5d (canonical-length cap, decision-008), 70f2e1f (v1 freeze, body cap), `backend/tests/contract/test_contract_v1.py`, `backlog/decisions/decision-008 …`, `decision-009 …`

## What we set out to do
Build the M3a API (search, parse, papers, meta, coverage, exports, search records, OpenAPI) as parallel tasks in agent worktrees, each reviewed on its own, then freeze `/api/v1`.

## What we learned
- **Parallel creation collides on ids.** Two worktrees each ran `backlog task create` from the same base and both got TASK-078; one had to be renumbered to TASK-080 at merge (37b8916). Decision records collide the same way. The CLI numbers from the checkout it runs in, not from a shared counter.
- **Agent worktrees under `.claude/worktrees/` bloat the tooling.** `lint_tooling.py`, the case tables and `mutate.py` walked every nested checkout until they were told to skip the gitignored directory (610f193, 6edb001).
- **Per-task reviews passed; the integrated gate found bugs that live between tasks:**
  - A saved query's canonical form could exceed the 2,000-code-point cap that its input passed, so the record replayed as `mismatch` (query × records; decision-008, `QUERY_VERSION` "2").
  - A record over a RIS-only (bootstrap) corpus offered its `total` as a PRISMA identification number (records × ingest; `identification_citable`, body v2).
  - A bare `@` in a title opened a new BibTeX entry in refaudit and BibTeX (export × real titles; every `@` is now `{@}`).
  - No request-body cap: a POST could stream any size before validation (app × every POST route; 413 `API_BODY_TOO_LARGE`, task-079).
- **The first API freeze needs a checklist, not taste.** What `test_contract_v1.py` now pins: every sent field required in the schema; `*_total` counts; one UTC `Z` timestamp form; one crawl-window shape; unknown or repeated parameters refused; path-id patterns; open vs closed enums (decision-009); `ErrorCode` derived from the registry; status-specific headers declared; `info.version` = `v1`; `verb_noun` operationIds.

## Dead ends — don't repeat these
- Trusting a green per-task review as evidence for the milestone. Each reviewer read its diff against a base that didn't yet have the sibling tasks, so none could see a cross-task seam.
- Letting each worktree regenerate `openapi.json`/`schema.ts` and resolving the merge conflict by hand; merge, then rerun `make openapi`.

## Decisions (and what would change them)
- One integrated `/review-gate` per milestone before the contract freezes (the milestone cadence) → cross-task bugs are only visible there → a CI job that runs the routed reviewers on the merged tree.
- Ids: create tasks and decisions from the integration branch, or renumber at merge and grep for the old id → the CLI has no shared counter → Backlog.md adding one.

## Follow-ups
- [ ] task-083 — `op record save/replay` over `openproceedings.records` (the CLI half of search records).
- [ ] task-087 — `/paper/[id]` highlights need a `q` on `GET /papers/{id}` or client-side carry-over.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/api-contract/SKILL.md` (§v1 shape rules), spec 04 §Conventions, `.claude/skills/review-gates/SKILL.md` (package-root `search.py`/`records.py`/`export.py` routed)
- Test or hook added? — `backend/tests/contract/test_contract_v1.py`; the worktree skip in `lint_tooling.py` and `mutate.py`
