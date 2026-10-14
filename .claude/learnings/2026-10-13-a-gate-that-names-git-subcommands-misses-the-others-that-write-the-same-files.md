# A gate that named `git rm` and `git mv` let `git restore` move a completed task back

**Key lesson:** A path gate must refuse every git command that writes those paths by pathspec (restore, checkout <commit> --, reset <commit> --, clean, stash push --, apply, am, merge-file, checkout-index, update-index, read-tree --prefix/-u, and rm/mv), and read the pathspec the way git does (`.`, `'*.md'` whose `*` crosses `/`, `:/` magic, `--pathspec-from-file`), not just name the two commands someone thought of.

- **Date:** 2026-10-13 · **Task:** task-244 · **Area:** tooling
- **Artifacts:** `.claude/hooks/protect-data-dir.sh` (`backlog_git_specs`, `backlog_spec`, `find_writes`), `.claude/hooks/lib/cmdparse.py` (`GIT_LONG_OPTS` for restore, rm, mv, apply, am, checkout-index, read-tree, rebase, difftool, grep), `.claude/hooks/tests/test-openproceedings-gates.sh` (the TASK-244 rows), `.claude/scripts/mutants/gates.json` ("pdd backlog git (TASK-244)" mutants), branch `fix/backlog-git-moves`; the incident: PR #146 and `2026-10-13-a-setup-chmod-hides-a-file-committed-without-its-mode.md`

## What we set out to do
Find why nothing stopped a subagent in PR #146 from putting a completed task back under `backlog/tasks/` with git,
three times, and close it.

## What we learned
- `git rm` and `git mv` of a named backlog file were already refused (probed through `probe_hook.py` as data:
  `git rm "backlog/completed/task-241 - ….md"` → block, from `-C`, `cd backlog` and with a glob too). The gap was
  every other git writer: `git restore --source=<sha> -- <task>`, `git checkout <sha> -- backlog/`, `git reset
  <sha> -- <task>`, `git restore .`, `--pathspec-from-file` and `git apply` all came back `allow`. One `git restore
  --source=<pre-completion sha> -- <tasks copy> <completed copy>` both recreates the old file and deletes the new
  one (the new one isn't in the source), so it is the whole move-back in one command.
- Pathspecs aren't paths. `git rm '*.md'` matches `backlog/tasks/x.md` because git's `*` crosses `/`; a filesystem
  glob from the root doesn't, so the old check read it as a file named `*.md`. `:/backlog` is a path the old check
  resolved as `./:/backlog`. Reading a glob by its fixed directory (the root reaches backlog/) and refusing any other
  `:` magic closes both.
- An exclude is case-exact even on APFS: `git checkout dev -- '*.md' ':^Backlog'` still restores `backlog/` files
  (git matches pathspecs case-sensitively without `:(icase)`), so an exclude only counts when it names `backlog`
  as written; positive paths stay case-blind.
- `git apply --numstat -z` names a rename by its new path only (evidence: a `rename from src/a.md` / `rename to
  backlog/tasks/a.md` patch printed `0\t0\tbacklog/tasks/a.md` and nothing for the old name), so the old name
  (deleted) is read from the patch's `rename from` lines. From a subdirectory git applies only the paths under it
  and prints them top-relative.
- What must stay allowed decided the shape: unstaging (`restore --staged`, `reset -- <path>`, or a reset to a tree
  equal to HEAD's) leaves the CLI's file on disk; branch and commit operations replay commits the CLI made; and a
  rebase or merge that stops on a task file has no other way to settle it (Edit is refused there), so a path every
  match of which is unmerged (`git ls-files --unmerged`) may take `checkout --theirs`, `restore --ours` or `rm`.

- The review round found the same shape again one level out, so a gate is only as complete as its list of
  writers: `git clean` (deletes the untracked file the CLI just wrote), `git am`, `git merge-file`, `read-tree -u`,
  `-p` with no path (the whole tree), `find -fprint`, BSD `find -f <path>`, `patch`, `tar -x`, `cp -R src .`
  landing at `./<name>`; and commands git runs from its own words (`-c core.pager=…`, `GIT_EDITOR`, `rebase
  --exec`, `bisect run`, `submodule foreach`, `filter-branch` filters), now re-checked as commands. A payload the
  hook couldn't read (invalid JSON, no command) was allowed; it is now refused.
- A word git can't resolve yet is not a path: `git fetch origin dev:t && git reset t <task>` was read as two
  pathspecs (`t` didn't exist when the hook ran). A word that is neither a commit nor a path is now a tree-ish.
- `git apply --numstat` under `-R` names the old side of a rename, so both `rename from` and `rename to` count; and
  a patch is read when the hook runs, so `git apply` in a call that writes the patch first is refused.
- Round 2 found a fail-open the round-1 fix made: a nested `-c` value that didn't parse took the old "parse error
  outside a repo with backlog/: exit 0" path and ended the whole check, so `git -C <repo> -c x="it's" rm -r backlog`
  passed from outside a repo. A parse failure now refuses everywhere, and only command settings' values (pager,
  editor, drivers, filters, aliases) are parsed at all, so `-c user.name="O'Brien"` stays allowed.
- The scope is a guard against mistakes, not a boundary (owner ruling via the coordinator, 2026-10-13):
  `git${IFS}rm`, a config or hook script written in an earlier call, and git behind a wrapper cmdparse doesn't
  strip can still get through; git history plus review is the backstop.

## Dead ends — don't repeat these
- Treating "the hook already refuses `git rm` under backlog/" as the whole rule: the reviewer's note was right
  about `git rm`, and the incident still got through with `git restore`.
- A first exclusion compare that lower-cased the path read `':^Backlog'` as excluding backlog/ when git doesn't.
- Waiting on `mutate.py` with `until ! pgrep -f "mutate.py --match …"`: the loop's own command line matches the
  pattern, so it never ends. Wait on the PID instead.
- Editing a hook while `mutate.py` runs: it copies the worktree for every mutant, so later mutants test the edit.
- Counting the worktree root as reaching backlog/ in every repository refused `git restore .` and
  `find . -delete` in repositories with no backlog/ at all; the root and magic count only where there is one.

## Decisions (and what would change them)
- Refuse whole-tree pathspecs (`git restore .`, `git checkout -- .`, `git rm -r --cached .`) in a repo with backlog/,
  with `':!backlog'` as the way out → they reach CLI files as surely as a named one → a CLI that could restore a
  task's earlier state would make the git route unnecessary rather than allowed.
- Leave commit-level operations alone (rebase, merge, cherry-pick, revert, `reset --hard <commit>`, `checkout
  <branch>`) → they replay CLI-written commits and the branch/merge-queue flow depends on them; reverting a
  completion commit is the same act in spirit and stays a convention → change if it is ever done.
- `find` from backlog/, a worktree root or above may list and `-exec` readers but not delete or run a writer
  (`-exec rm`, `-exec git restore`, `-exec sh`) → which files it picks can't be seen → a start path that leaves
  backlog/ out is the workaround.

## Follow-ups
- cmdparse's wrapper list lacks `xcrun`, `caffeinate`, `arch`, `doas`, `flock` and `unbuffer`, which every gate shares
  (security review nit): filed as a task at the end of the branch.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `CLAUDE.md` (hook table), `.claude/skills/task-hygiene/SKILL.md` (finalize only after the last review round; what to do when a completed task needs changes; what git may still do), `docs/specs/08-ops-and-tooling.md` (hook table), the hook's header comment
- Test or hook added? — `protect-data-dir.sh` rows in `test-openproceedings-gates.sh`, mutants in `gates.json`
