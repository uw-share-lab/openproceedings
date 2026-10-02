# A quoted command substitution is a command, and only the scanner that knows the quotes can find it

**Key lesson:** Find command substitutions while the quote state is known (in `cmdparse.preprocess`), mark them in the word, walk their bodies before the command and restore the text; after shlex has removed the quotes, `'$(x)'` and `"$(x)"` look the same.

- **Date:** 2026-10-02 · **Task:** task-156 · **Area:** tooling
- **Artifacts:** `.claude/hooks/lib/cmdparse.py` (`_substitution_end`, `_mark`, `_restore`, `_subshell`),
  `.claude/hooks/{block-ai-attribution,require-review,protect-data-dir,enforce-pr-workflow}.sh`,
  `.claude/hooks/tests/test-openproceedings-gates.sh` (TASK-156 rows), `.claude/scripts/mutants/gates.json`

## What we set out to do
Close the shell-semantics bypasses the TASK-067 review deferred: a push or `rm` inside `"$(…)"` or backquotes,
a trailer split by quoting, `~` with HOME '' outside a push, a payload past ARG_MAX, and `git format-patch -o`.

## What we learned
- **shlex's output can't tell a single-quoted `$(…)` from a double-quoted one**, so walking every `$(` in a word
  would have refused ``git commit -m 'docs: `git push`'``. The double-quote and backquote cases are found in
  `preprocess`, which tracks quotes; each becomes a private-use mark plus an index into a `subs` list, so brace
  expansion and loop unrolling carry it, and `_walk` walks the body as a subshell (state saved and restored as
  for `bash -c`) before the command that holds it. (Evidence: rows `x="$(git push origin other2)"` block and
  ``git commit -m '… `git push origin other2`'`` allow.)
- **The body has to be read as bash reads it, quotes and heredocs included.** Before, preprocess kept its outer
  quote state through `"$(echo "a b")"` and split it into `$(echo a` and `b)`; `_substitution_end` reads nested
  quotes, `$(`, backquotes, comments and heredoc bodies, so the canonical `-m "$(cat <<'EOF' … a) b … EOF)"`
  ends at the right `)`. (Evidence: the two precision rows and their mutants.)
- **A second walk with HOME '' is cheap and needs no new rules**: every gate now walks a command with `~` or
  `$` twice, and enforce-pr-workflow's push-only re-read (`alt`) became the second pass. `cd ~` then stays put,
  as bash does with HOME ''. (Evidence: `cd ~ && rm -rf data`, `cd ~ && git commit -m x` on dev.)
- **Scanning the parsed words catches what the raw text hides**: `'Cl''aude'` and `$'\x43laude'` are one word
  once read; `expand_known` also puts in variables set earlier in the command.

- **Two bash shapes end a body somewhere a paren count doesn't**: a `case` pattern's `)` and `"$((cmd) )"`,
  which bash runs as a subshell inside a substitution, not arithmetic (review round 1: both let
  `git push origin HEAD:dev` through). The scanner counts `case`/`esac`, and a quoted `$((` is walked like `$(`:
  real arithmetic reads as harmless words. Only a `case` in command position counts (`echo use case` is a word:
  review round 2), and `bash -c`/`eval`/nested bodies share the walk's `subs` list (a mutant that dropped it
  survived every row until the round-2 rows).

## Dead ends — don't repeat these
- **A reviewer probing hooks with an inline heredoc ran the probes for real.** A qa-auditor piped its test
  commands through `<<EOF`, one test held an `EOF` line, the heredoc closed early and every later line ran in
  zsh (`cd ~ && rm -rf data` in the home folder). Write probe payloads to files with a tool, never into a shell
  heredoc, and tell every reviewer that touches hooks so.
- Walking substitution bodies after the whole command, with the caller's final state: a later `cd` or variable
  change would be applied to an earlier substitution (fail open). Walk them in place.
- Marking unquoted `$(…)` too: its parentheses already split it into commands, so it would be walked twice.

## Decisions (and what would change them)
- A command with `~` or `$` is read both ways in every gate. In the HOME '' reading a `cd ~/x` whose `/x` doesn't
  exist is a failed cd (the shell stays), not an unknown directory: a path at the root is one the command can't
  have made. Review round 2 caught the first version, which refused `cd ~/<worktree> && git commit` everywhere;
  if a real case needs it, track `mkdir` before treating a missing target as a failed cd.
- Without python3 the three Python gates refuse every Bash call (exit 127 → 2), unlike enforce-pr-workflow's
  text fallback: the repo needs python3 (uv) anyway.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — CLAUDE.md §Enforced gates; spec 08 §Hooks and §cmdparse; the
  no-ai-attribution skill; the hooks' headers; cmdparse's docstring; qa-auditor.md and security-reviewer.md (probe
  hooks with payloads in files, never a shell heredoc)
- Test or hook added? — `.claude/hooks/tests/test-openproceedings-gates.sh` and `test-enforce-pr-workflow.sh`
  TASK-156 rows; mutants in `.claude/scripts/mutants/gates.json`
