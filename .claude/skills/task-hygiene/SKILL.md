---
name: task-hygiene
description: The standing rule that Backlog tasks, docs, specs, READMEs and every other .md are updated continuously as work happens — not at the end — and that a finished task is moved to backlog/completed/ with `backlog task complete`. Covers what "update" means per artifact, when in the session each update happens, and the CI checks that enforce it. Use at the start, during, and at the close of any task, and whenever a reviewer asks whether docs are as-built.
---

# Task and docs hygiene (project rule, 2026-09-25)

**Rule:** the repo describes itself truthfully *at every commit*. Tasks, docs, specs, READMEs and `.md`
files change **in the same commit** as the behaviour they describe. Nothing is batched up for "later". And
a task that is Done does not stay in `backlog/tasks/`.

## Tasks (Backlog.md, CLI only)
| When | Do |
|---|---|
| Starting work | `backlog task edit <id> -s "In Progress" -a @<you>`; add a plan (`--plan`) |
| As you go | Tick acceptance criteria as each is met (`--check-ac <n>`); add notes (`--append-notes`; `--notes` replaces them) when you learn something that changes the plan; record any follow-up **when you find it** (in the notes), and file it as a task at the end, after rebasing (§Ids) |
| Scope changes | Edit the description/ACs so they match what you're actually doing; a stale AC is a lie |
| Adding a dependency | `--dep` **replaces** the whole list: pass the old ids plus the new (`--dep task-063,task-065,task-133`), then check the `dependencies:` diff |
| Done | **After the last review round** (a `/review-gate` round left nothing to fix): all ACs checked → `backlog task edit <id> -s Done --final-summary "…"` → **`backlog task complete <id>`**, which moves it into `backlog/completed/` |

`backlog task complete` is the only way a task leaves `backlog/tasks/`. Never move files by hand: editor
writes under `backlog/` are blocked by `enforce-backlog-cli.sh`; shell writes there (e.g. `mv`, `cp`, `rm`, `touch`,
redirects, a copy that lands there, `find -delete`/`-exec <writer>`/`-fprint` that can reach it), and every git command that writes its files by pathspec
(`git restore`, `git checkout <commit> -- <path>`, `git reset <commit> -- <path>`, `git rm`, `git mv`, `git clean`,
`git stash push -- <path>`, `git apply`, `git am`, `git merge-file`, `git checkout-index`, `git update-index`, `git
read-tree --prefix`/`-u`, `-p` with no path, a whole-tree pathspec such as `.`, `'*.md'` or `:/` included), `patch`, an archive
extracted where backlog/ is, and a git pager, editor or `--exec` command that does any of that, are blocked by
`protect-data-dir.sh` (TASK-244); and CI's
`check_backlog.py` catches a Done task left behind in `tasks/`. Git still may unstage there (`git restore
--staged`, `git reset -- <path>`), read (`log`, `show`, `diff`), dry-run (`git clean -n`, `git apply --check`; `git rm -n`/`git mv -n` there
stay refused), move whole branches and commits
(checkout/switch a branch, rebase, merge, cherry-pick, `reset --soft`/`--mixed` to a commit), and settle a file a
rebase or merge stopped on (`git checkout --theirs <path>`, or `git add -u <path>` to accept a deletion; `git rm`
there stays refused); a whole-tree restore can leave backlog/ out with
`':!backlog'`. `git reset --hard`/`--merge`/`--keep` are refused where backlog/ is; the whole-tree discards still allowed
(`git checkout -f`, `git switch --discard-changes`, `git stash`) undo an uncommitted CLI change like any other, so
commit what the CLI wrote right away. The hook is a guard against
mistakes, not a boundary: an obfuscated command may get past it, and git history plus review are the backstop.

**Finalize only after the last review round.** Backlog.md 1.53 can't edit a task once it is in `completed/`
("Task not found"), and nothing may move it back: so a task completed while review is still running can't take
the next round's notes or ticks. Finalizing is a commit of only the CLI's files, reviewed (`code-reviewer`,
`docs-reviewer`) and attested as a new head. If that round finds a Must or Should, fix it in a new commit and
re-review; never edit or reopen the completed task: record the change in the PR body and the learnings entry, and
file a follow-up task only for work that can't be done yet. If a task was completed early anyway, leave the completed file as it is and never put the
pre-completion copy back with git (PR #146 did, three times, and lost the plan once; that is what TASK-244
closed). Put what the later rounds changed in the PR body and the learnings entry; if they found more work, file
it as a follow-up task with `backlog task create` (at the end of the branch, §Ids) whose description names the
completed task. Only the owner reopens a completed task.

Archive (`backlog task archive`) is only for tasks that were dropped
unfinished. Give the reason in the notes first.
Backlog.md 1.53 reuses an archived task's id: the next `backlog task create` after an archive gets the
same number (task-075 twice, 2026-09-26). After archiving, say which task an id means in both tasks' notes,
or prefer finishing a task (Done + complete) with a "not reproduced" summary over archiving it.
Write `--final-summary` before `backlog task complete`: 1.53 can't edit a task once it is in `completed/` or
`archive/` ("Task not found"), and the files there are hand-edit-protected (M2 gate, 2026-09-26).

## Ids
The CLI numbers a new task or decision from the files in the branch's own checkout. `dev` merges through
a queue that doesn't require a PR to be up to date (decision-027), so two PRs that each create task-162
write different filenames, git sees no conflict, and both would merge with one id. So:
- **The branch's own task** is created (or picked) on a freshly pulled `dev` before branching, as
  CONTRIBUTING.md §Flow says; if another PR takes its id first, the check below catches it.
- **Ids created during the work are created last**: follow-up tasks, `task-NNN` dispositions and decision
  records. Run `backlog task create` / `backlog decision create` after rebasing onto the latest `dev`, at the
  end of the branch's work and before the final `/review-gate` (whose dispositions cite the new ids), in a
  commit that holds only the CLI's files and the edits that name the new ids. Until then, keep each follow-up
  in the current task's notes (`--append-notes`), or, with no current task, in the PR draft. A deferral
  raised in the final review round is filed the same way, then reviewed and attested as a new head.
- **`check_backlog.py` enforces uniqueness**, in `claude-tooling` on the PR (whose merge ref already holds
  `dev`) and again in every queue build (`merge_group`), where two PRs that raced first meet. It fails, naming
  the files, when two files in `tasks/` + `completed/` share a task id, or two in `decisions/` share a decision
  id. The id is the frontmatter `id:`, compared by number (`TASK-075` = `task-75`; a subtask `12.1` is not
  `12`). A file fails too if it has no frontmatter, an indented line before its first key, a top-level
  frontmatter line that isn't a plain `key:`, a `- ` item or a comment (`{…}`, `? id`, `<<:`, a tag, anchor
  or escaped key), no `id:` (Backlog.md doesn't read the filename; the filename prefix is still compared),
  an unreadable id, two `id:` fields, or a frontmatter id that disagrees with its filename; so does a missing
  `tasks/` or `completed/`. `archive/` is not compared (the 1.53 reuse above). Rows:
  `.claude/scripts/tests/test-tooling-scripts.sh`; mutants: `.claude/scripts/mutants/backlog.json`.
- **On a clash**, the PR that hasn't merged renumbers: rebase onto `dev`, drop the commit that created the id,
  create it again with the CLI (it gets the next free id), update whatever named the old one, then re-review
  and re-attest the new head.

## Docs, specs, READMEs, every `.md`
| You changed… | Update in the same commit |
|---|---|
| Behaviour, a CLI flag, an endpoint, a file layout | The spec section that defines it (`docs/specs/`), plus any README or skill that describes it |
| A convention or gate | `CLAUDE.md`, `CONTRIBUTING.md`, the owning skill, and the hook's comment and case table |
| An agent, skill or command | Its frontmatter, then `python3 .claude/scripts/roster_index.py` (regenerates `.claude/README.md`) |
| Anything a new contributor would trip on | `README.md` / `CONTRIBUTING.md` |
| A milestone's feature, or an `op` command, flag, default, port, env var, `make` target or setup step | `README.md` §Status and §Quickstart (every step there was run when written; re-run the ones you changed) |
| A lesson | `.claude/learnings/` via `/record-learnings` |

README.md is the doc most likely to drift, because no diff touches it by accident: `docs-reviewer` checks
its Status and Quickstart on **every** diff (TASK-120).

"As-built" means grep-verifiable: every path, command, flag and name a doc mentions exists and behaves as
described. `docs-reviewer` is routed on **every** diff (`.claude/skills/review-gates/SKILL.md`) to check
exactly this, and a stale doc is a **Should** at minimum (**Must** if it would send someone the wrong way).

## Enforcement
- **CI `claude-tooling`:**
  - fails if any task file in `backlog/tasks/` has `status: Done` (it should have been completed;
    `.claude/scripts/check_backlog.py`);
  - fails if two task files (`tasks/` + `completed/`) or two decision files share an id (§Ids; same script);
  - fails if `.claude/README.md` or `.claude/learnings/INDEX.md` is stale;
  - fails if the roster lint finds any reference to a missing agent, skill or command.
- **`/review-gate`:** `docs-reviewer` always runs.
- **Closing workflow** (`CLAUDE.md`): ACs, notes (step 2) and docs (step 3) come before the learning and the
  review; `backlog task complete` comes after the last review round, as its own reviewed head (step 5).

## Anti-patterns
- "I'll update the docs in a follow-up PR." No. The PR that changes behaviour changes its docs.
- Leaving a task In Progress after the PR merges. Complete it after the last review round and before the PR
  is opened; the completion commit is reviewed and attested as a new head, so its final summary is reviewed too.
- A Done task left in `tasks/`. CI rejects it. Run `backlog task complete <id>`.
