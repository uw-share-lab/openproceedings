---
id: TASK-244
title: >-
  protect-data-dir.sh lets git restore, checkout and reset move backlog files
  back
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-13 19:42'
updated_date: '2026-10-14 00:50'
labels:
  - tooling
  - bug
dependencies: []
priority: high
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
During PR #146 (TASK-241) a subagent completed task-241 before review finished, then three times put the pre-completion copy back under backlog/tasks/ with git (restore/rm) and re-finalized through the CLI. CLAUDE.md says protect-data-dir.sh enforces no shell edits under backlog/, but it only reads git rm and git mv, and only plain paths: git restore, git checkout <tree-ish> -- <path>, git reset <tree-ish> -- <path>, git magic pathspecs (:/backlog), git globs whose * crosses / ('*.md'), whole-tree pathspecs (.) and --pathspec-from-file all pass. Backlog.md 1.53 cannot edit a completed task, so completing early leaves no CLI way back; the skill must say so plainly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every git command shape that writes backlog/ files in the worktree or index by pathspec (rm, mv, restore, checkout <tree-ish> --, reset <tree-ish> --, stash push --, apply, checkout-index, update-index, read-tree --prefix) is refused by protect-data-dir.sh, including -C, cd, globs, magic pathspecs, whole-tree pathspecs, --pathspec-from-file, xargs and unresolvable paths
- [x] #2 The backlog CLI, decision-body edits, read-only git (log/show/diff, dry runs), unstaging (restore --staged, reset HEAD --), branch/commit-level operations (checkout/switch a branch, rebase, merge, cherry-pick, reset to a commit) and pathspecs that exclude backlog/ stay allowed, and the rule is documented
- [x] #3 Case-table rows cover every blocked and allowed shape; make tooling is green and every new mutant is killed (make mutate-changed)
- [x] #4 CLAUDE.md, the task-hygiene skill and spec 08 describe the hook as built, and task-hygiene says what to do when a completed task needs changes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduce each shape through probe_hook.py (data only). 2. In protect-data-dir.sh, one rule for git commands that write backlog/ files by pathspec: a pathspec reaches backlog/ when it is in it, is the worktree root (or above), is a git glob or magic pathspec from such a place, or can't be read; an exclude of backlog/ lifts it. Allowed: unstaging, dry runs, read-only and commit-level commands. 3. Case-table rows, GIT_LONG_OPTS for restore/rm/mv/apply, mutants. 4. Docs: CLAUDE.md, task-hygiene, spec 08, hook comment.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review round 1 (code, docs, security, qa) and the coordinator's audit: added git clean, am, merge-file, read-tree -u, -p with no path, find -fprint/-f, patch, tar/unzip, cp -R/rsync/ditto landing paths, touch/sponge; commands git runs from its own words (-c values, GIT_PAGER/EDITOR…, rebase --exec, bisect run, submodule foreach, grep -O, difftool -x, filter-branch filters, git config values) are checked as commands; malformed payloads fail closed; unresolvable paths refused where backlog/ is; git pathspecs into data/snapshots|indexes refused; literal pathspecs; relative --work-tree after -C. Closing-workflow docs now finalize after the last review round. Known limitation (owner ruling via the coordinator): obfuscated commands may bypass; the backstop is git history plus review (git${IFS}rm, config/hook scripts written earlier, unstripped wrappers). Follow-up: cmdparse wrapper list (xcrun, caffeinate, arch, doas, flock, unbuffer) to file at the end.

Review round 2 (security regression report via the coordinator; code/qa/docs/security reviewers): a nested -c value that failed to parse exited 0 and ended the check (fail-open regression from round 1). Now any parse failure refuses everywhere and only command settings' -c values are parsed. Also tar x in any cluster, ditto contents, -t dir, find -D/-O/-follow, separate path-valued values, rebase/difftool/grep abbreviations, git config --file/set, filter-branch --setup, copy headers, byte-level unquoting, apply --check && apply allowed, clean -X. The origin/dev case table, run against the new hook, has no row that blocked before and passes now (only the three git clean -e data rows changed, allow to block, by design).
<!-- SECTION:NOTES:END -->
