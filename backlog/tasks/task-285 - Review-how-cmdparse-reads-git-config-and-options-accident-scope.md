---
id: TASK-285
title: Review how cmdparse reads git config and options (accident scope)
status: In Progress
assignee: []
created_date: '2026-10-26 20:37'
updated_date: '2026-10-28 20:31'
labels:
  - tooling
  - hooks
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Proposed after the TASK-282 reviews (2026-10-22/23): they found four push-gate bypasses in how cmdparse reads git's own config and options, none in code that task set out to change (git_bool reading git's true 1k/0x1/+1 as false, a value with a newline forging a key, a remote name with a space hiding one, remote names differing only in case). One focused review of cmdparse's git config and option reading: push.default / remote.pushDefault / branch.<b>.pushRemote / remote.<r>.push resolution, includeIf and include.path, -c and GIT_CONFIG_* env, option bundling and abbreviations, case rules for keys and subsections. Scope (owner, 2026-10-25 decision recorded in .claude/learnings/2026-10-26-hardening-the-hook-parser-against-evasion-never-converged.md): the hooks guard against an agent's mistakes, so report misreadings of configuration a real repo or agent would plausibly have; decline constructs only deliberate evasion would write. Misreadings include over-refusals: a setting a real repo has that makes a gate refuse an ordinary push or commit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A security-reviewer or qa-auditor pass over cmdparse's git config and option reading, with probes run as data through probe_hook.py --file
- [x] #2 Every finding a real repo or agent could plausibly hit is fixed with a case-table row and a mutant; evasion-only findings are declined in writing
- [x] #3 make tooling and make mutate-changed pass
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review pass: a security-reviewer pass over cmdparse's git config and option reading (push.default, remote.pushDefault, branch.<b>.pushRemote/merge, remote.<r>.push/.mirror, push.followTags, include/includeIf, -c/--config-env/GIT_CONFIG_*, global options, push option values and bundling, abbreviations, key case), probes fed as data through probe_hook.py --file against scratch fixture repos.

Fixed (each with case-table rows and mutants in gates.json):
- enforce-pr-workflow: git push --branches (git's newer name for --all) was allowed; now refused like --all (--bra too).
- enforce-pr-workflow: a push option's value (-o ci.skip, --push-option, --repo, --receive-pack, --exec) was read as the remote/refspec, so 'git push -o ci.skip origin' skipped the refspec-less config checks (push.default=upstream to dev). push_positionals moved from require-review into cmdparse; both gates use it.
- Over-refusal: 'git branch --set-upstream-to=origin/x && git pull' (git's own advice) was refused by enforce, require-review and protect-data-dir: branch -u/-t set config_written, which fails every later git command. It now sets upstream_written (creates_with_upstream), which refuses only a later push.
- Over-refusal: remote.<r>.push = HEAD (or +HEAD) refused every refspec-less push; it is now read as 'git push <remote> HEAD'. push_config joins a repeated remote.<r>.push key's values, so a HEAD can't hide another refspec.
- Over-refusal: require-review refused every refspec-less push under push.followTags (repo config or -c). Owner decision 2026-10-28: dropped, overriding TASK-067/TASK-282 on this point. The tags it adds point into the commits pushed, exactly as with a named refspec, which was always allowed. TASK-282's git_bool rows now run on remote.origin.mirror, so that code stays tested.
- Messages: enforce's FailClosed refusal names the rule that fired (it always blamed an ambiguous abbreviation); protect-data-dir's parse refusal includes the exception text.

Declined (rejected: deliberate evasion, out of the hooks' scope): -c branch.<b>.merge=... with push.default=upstream; a remote.<r>.push mapping feat to dev then 'git push origin feat'; -d bundled in a short cluster (-fd); --recurse-submodules check as a separate word; --attr-source as a global option; a commit message that is an ambiguous long-option prefix; HOME=/GIT_CONFIG_GLOBAL= before a refspec-less push (already refused).

Verification: make mutate-changed (--jobs 4) on 4a23eb6f: 864 mutants, 0 problems. After the followTags change only the case tables, make tooling (incl. mutate --check) and make lint were rerun, per the owner; the nightly mutation shards cover every mutant.
<!-- SECTION:NOTES:END -->
