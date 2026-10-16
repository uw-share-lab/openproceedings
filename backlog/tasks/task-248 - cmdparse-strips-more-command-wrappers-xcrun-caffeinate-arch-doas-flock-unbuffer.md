---
id: TASK-248
title: >-
  cmdparse strips more command wrappers (xcrun, caffeinate, arch, doas, flock,
  unbuffer)
status: In Progress
assignee: []
created_date: '2026-10-14 16:32'
updated_date: '2026-10-16 19:53'
labels:
  - tooling
dependencies: []
priority: low
ordinal: 174000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-244's security review found that git run behind a wrapper cmdparse doesn't strip (xcrun git restore backlog/..., caffeinate, arch, doas, flock, unbuffer) reaches every gate that uses cmdparse as an unknown command: protect-data-dir, enforce-pr-workflow, require-review and block-ai-attribution all miss it (xcrun git commit -m ... reaches the attribution gate unstripped too). cmdparse.WRAPPERS / WRAPPER_VALUE_OPTS list env, nice, timeout and others but not these. Today this sits under protect-data-dir's documented limitation (obfuscated commands may bypass).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each listed wrapper is stripped by cmdparse before every gate reads the command, with its value-taking options and its non-option arguments (flock's lock file and its -c '<cmd>' string, arch -arch <a>)
- [x] #2 Case-table rows in each gate's table and mutants in .claude/scripts/mutants/gates.json cover them
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
cmdparse.WRAPPER_VALUE_OPTS lists xcrun (-sdk/--sdk/-toolchain/--toolchain), caffeinate (-t/-w), arch (-arch/-d/-e; -e NAME=value sets NAME and -d NAME unsets it for what arch runs, as env's do), doas (-a/-u/-C) and flock (-w/-E/--wait/--timeout/--conflict-exit-code), and unbuffer. flock's -c/--command '<cmd>' after the lock file is rewritten to sh -c '<cmd>', so the walk reads it like any child shell. flock creates its lock file, so the file goes into Argv.creates with the directory flock ran in, and the walk yields it as a >> redirect of an empty command of its own, before whatever flock runs (eval and cd included); every gate's write rules then apply (flock .git/op-reviews/<sha>, flock data/snapshots/..., flock backlog/... are refused). 'flock 9' alone locks a descriptor and creates nothing. Review rounds 1-3 found doas -a, arch -e and -d, and the lock file (first hidden from require-review's record check, then dropped after eval/cd). Rows: test-enforce-pr-workflow.sh (regression rows; the flock -c/--command rows and the arch -e/-d GIT_DIR rows kill mutants), and block-ai-attribution / require-review / protect-data-dir rows in test-openproceedings-gates.sh (TASK-248 section). 22 TASK-248 mutants in gates.json. xcrun -f/--find and doas -C only find or check the tool without running it; reading what follows as the command is the conservative side. Not done here (pre-existing, reported as follow-ups): a short-option cluster ending in a value option (flock -nw 5, doas -nu root, sudo -nu root) is not split; env -C / sudo -D move the parser's directory for every later command, not just the one they run.
<!-- SECTION:NOTES:END -->
