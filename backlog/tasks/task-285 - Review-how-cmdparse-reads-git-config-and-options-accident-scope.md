---
id: TASK-285
title: Review how cmdparse reads git config and options (accident scope)
status: To Do
assignee: []
created_date: '2026-10-26 20:37'
labels:
  - tooling
  - hooks
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Proposed after the TASK-282 review (2026-10-22): its reviews found three push-gate bypasses in how cmdparse reads git's own config and options, none in code that task set out to change (git_bool reading git's true 1k/0x1/+1 as false, a config value forging a key, remote names differing only in case). One focused review of cmdparse's git config and option reading: push.default / remote.pushDefault / branch.<b>.pushRemote / remote.<r>.push resolution, includeIf and include.path, -c and GIT_CONFIG_* env, option bundling and abbreviations, case rules for keys and subsections. Scope (owner, 2026-10-25, learnings 2026-10-26-hardening-the-hook-parser-against-evasion-never-converged.md): the hooks guard against an agent's mistakes, so report misreadings of configuration a real repo or agent would plausibly have; decline constructs only deliberate evasion would write.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A security-reviewer or qa-auditor pass over cmdparse's git config and option reading, with probes run as data through probe_hook.py --file
- [ ] #2 Every finding a real repo or agent could plausibly hit is fixed with a case-table row and a mutant; evasion-only findings are declined in writing
- [ ] #3 make tooling and make mutate-changed pass
<!-- AC:END -->
