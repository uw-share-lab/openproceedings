---
description: Review the frontend diff (or one route) for reviewer workflow clarity and WCAG 2.2 AA — spawns ux-reviewer and accessibility-auditor in parallel and merges their findings
argument-hint: "(optional) a route like /search or /record/[id], or a diff range; default origin/dev...HEAD -- frontend/"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Run a frontend review. Target: $ARGUMENTS — if empty, the branch diff `origin/dev...HEAD -- frontend/`.

1. **Scope.** If the target is a route, list the components under `frontend/src/` that render it. If it
   is a diff, `git diff --name-only <range> -- frontend/`. Nothing under `frontend/` → say so and stop.
2. **Environment.** Start `op serve` on the fixture index and the frontend (`npm run dev` in `frontend/`)
   so both reviewers exercise the running app, not only the code. Never point either at `data/indexes/`
   for a production index.
3. **Spawn in parallel, one message:**
   - `.claude/agents/ux-reviewer.md` — URL-is-state, facet click rewrites `q`, every exclusion, expansion,
     warning and translation visible, export and record-page flows.
   - `.claude/agents/accessibility-auditor.md` — keyboard-only flows through editor, builder and results,
     Text/Builder focus management, non-colour highlights, contrast in both themes, 320/360 px reflow,
     axe runs per `.claude/skills/accessibility/SKILL.md`.
   Give each the target, the running URLs, `docs/specs/05-frontend.md`, and the reviewer output contract
   from `.claude/skills/review-gates/SKILL.md`.
4. **Consolidate.** Merge duplicates (keep the higher severity), group Must / Should / Nit with
   `file:line — problem — fix` and the reproduction each reviewer gave.
5. **Report** the merged table, each reviewer's verdict, and the combined verdict (REQUEST CHANGES if
   either requested changes). This command does **not** record an approval; the pre-push record comes
   only from `/review-gate`, which routes these same two reviewers for `frontend/**`.
