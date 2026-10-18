---
id: TASK-253
title: >-
  cmdparse: wrapper option parsing (grouped and attached short options,
  long-option prefixes) and two older gaps
status: In Progress
assignee: []
created_date: '2026-10-16 22:50'
updated_date: '2026-10-18 17:03'
labels:
  - tooling
dependencies: []
priority: medium
ordinal: 166000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found while reviewing TASK-248 (PR #158, 2026-10-16); all predate that branch and are on dev. (1) _strip_prefixes doesn't split a short-option cluster that ends in a value-taking option, so the value is read as the command: sudo -nu root git push, flock -nw 5 <file> ..., doas -nu root .... (2) env -C dir and sudo -D dir move the parser's directory for every later command instead of only the one they run: env -C /tmp true; git commit is judged as if it ran in /tmp. (3) sh -c '...' >> file and eval ... >> file drop their own redirects, so a write to a protected path through them isn't seen. The hooks are agent guardrails, not a security boundary; keep the fix bounded and fail closed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 env -C and sudo -D change the directory only for the command they run
- [ ] #2 sh -c and eval keep their own redirects, so protect-data-dir sees the write
- [ ] #3 Each case has rows (probes as data only) in the affected gates' tables and a killed mutant in .claude/scripts/mutants/gates.json
- [ ] #4 Getopt-style wrappers (flock, doas, caffeinate, env, sudo, nice, timeout) split a short-option group, where a value-taking letter takes the rest of the word or else the next word (flock -nw 5 <file>, -w5, sudo -nu root); a long option resolves only by unique prefix of the wrapper's known long options (flock --wai 5 /tmp/l git push hides the push today); an ambiguous or unknown long option, or any argument the parser can't place for certain (an unexpected word after flock's lock file), fails closed with a ParseError
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16: widened with the automated security review's flock finding on PR #158 (MEDIUM): grouped short flags, the attached form, unique-prefix long options and an unexpected word after the lock file. The new wrappers (TASK-248) made it reachable; sudo -nu root has the same gap on dev. Deferred from #158 because it changes the option loop every wrapper shares, where review loops have caused regressions; keep the fix bounded (about 3 review rounds). Priority raised to medium.

2026-10-16, related (not an AC): TASK-183's agent edited decision-035's body with a shell python script and protect-data-dir didn't refuse it, though the hook forbids shell edits under backlog/. It falls under the hook's documented limit (interpreters writing files are obfuscation it doesn't model); decide while here whether python3 -c/heredoc writes naming a backlog/ path should be refused.

2026-10-18 (branch fix/cmdparse-wrapper-options, with TASK-254): getopt wrappers (env, sudo, nice, timeout, doas, caffeinate, flock) now carry every option each takes (cmdparse.GETOPT_WRAPPERS, GNU and BSD), read by _getopt: short groups, a value letter taking the rest of the word or the next word, unique long prefixes, -- ending options, env - as -i, nice -5 as -n 5; an unknown or ambiguous option, a missing value, or another option after flock's lock file than -c/--command is a ParseError. env -S words are read as env's own (options included). env -C / sudo -D set Argv.chdir: only that command moves, its redirects are anchored where the shell is (a $/~ target there is a ParseError), and an unresolvable directory stays put, marked unknown. sh -c and eval yield their own redirects first as a command of none.

Lead's addition (TASK-261 review): protect-data-dir's older mv check read mv's -t value as a source, so mv -t .. README.md was refused wherever .. holds data/snapshots. mv_operands now reads -t DIR / --target-directory[=]DIR (and unique prefixes, attached -tDIR) as the destination and every other word as a source; an attached -t$X is refused where data/ is. Rows: mv -t .. / --target .. / --target-directory=.. / -vt.. allowed, mv src ..  and cp -t .. allowed, mv -t /tmp data/snapshots and --target-directory=/tmp ... data/indexes refused.

Related (not an AC), decided here: python3 -c / heredoc programs that write under backlog/ stay outside protect-data-dir's model (the hook's documented limit: interpreters writing files are obfuscation it doesn't parse); refusing every interpreter call that names a backlog/ path would refuse reads too, and the CLI-only rule is backed by review and enforce-backlog-cli's file-tool guard.
<!-- SECTION:NOTES:END -->
