---
id: TASK-269
title: 'cmdparse: sudo -e / sudoedit read as a non-write'
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-26 13:07'
labels:
  - hooks
  - security
dependencies: []
priority: low
ordinal: 176000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
cmdparse treats sudo -e <file> (sudoedit) as running no write, so the gates that judge writes (protect-data-dir, enforce-backlog-cli) don't see it edit the file. Security-gate Nit on the 0.4.0 promotion; already on main.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 sudo -e, sudo --edit and sudoedit name their file arguments as writes
- [x] #2 Case-table rows for each, under data/indexes and backlog/
- [x] #3 make tooling and make mutate-changed: no survivors
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: cmdparse reads sudoedit as sudo -e with sudo's getopt (bundles, -u, --edit/--ed, --); each file is an Argv.creates write. -D dir: checked from both dirs. -R/--chroot with an edit is a ParseError (refused). enforce-backlog-cli covers file tools only, so the backlog/ rows are protect-data-dir's (its headers now say so). 24 rows; 15 mutants KILLED.

2026-10-25 (review rounds 1-3, a9913868 and 2e74966b): cmdparse case-folds every command name for every gate (basename, lower-cased, wrappers included); builtins that act on the shell itself and reserved words match only as spelled. New Argv.external: after a getopt wrapper, env/nohup, any other wrapper but command/builtin/time as spelled, a path or a case-changed name, the command runs in a child, so cd/pushd/popd and exports leave the walk's state alone. A command name hidden by an expansion the walk can't resolve raises UnresolvedName (a ParseError, refused wherever an unparseable command is); X=git; $X and $VENV/bin/python still resolve, $EDITOR f is now refused by protect-data-dir. zsh noglob/nocorrect/- are wrappers. enforce-pr's parse-fail fallback is case-blind (grep -Eqi). Gates table 1819 rows, pr-workflow 443, 0 failed; narrowed mutate 58 mutants 0 problems (4 marked equivalent with reasons); full make mutate-changed on a frozen clone in review round 4.

2026-10-26 (review round 4, 7bacedb0): UnresolvedName reverted (see TASK-266); a name the walk can't resolve is read as written, so "$PYTHON" -m pytest and $EDITOR f are allowed again. Round 4's further parser differentials (split values, zsh command cd, quoted time, external eval, find -exec sh -c, glob names) were declined by the owner as deliberate evasion, out of the hooks' scope (2026-10-25).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cmdparse reads sudoedit and sudo -e with sudo's getopt (bundles, -u, --edit, --), and each file is a write; -D is checked from both dirs, and -R/--chroot with an edit is refused. Review rounds 1-3: command names are case-folded for every gate, except builtins and reserved words, which match only as spelled. Argv.external keeps a builtin run in a child (after a getopt wrapper, env/nohup, a path or a case-changed name) from moving the walk's directory or exports. enforce-pr's parse-fail fallback is case-blind, and zsh noglob/nocorrect/- are wrappers. Round 4's adversarial parser differentials were declined as out of scope by the owner (2026-10-25). Gates and pr-workflow tables pass.
<!-- SECTION:FINAL_SUMMARY:END -->
