# A merge queue without the up-to-date rule lets two PRs merge one Backlog id

**Key lesson:** Once `dev` merges through a queue with strict up-to-date off, anything a branch numbers from its own checkout (Backlog task and decision ids) can collide with no git conflict, so create those ids last, after rebasing onto `dev`, and let `check_backlog.py` in `claude-tooling` (which also runs on `merge_group`) fail on any id used twice.

- **Date:** 2026-10-02 · **Task:** task-161 (follow-up) · **Area:** tooling
- **Artifacts:** `.claude/scripts/check_backlog.py`, `.claude/scripts/tests/test-tooling-scripts.sh`, `.claude/scripts/mutants/backlog.json`, `.claude/skills/task-hygiene/SKILL.md` §Ids, spec 08 §Merge queue, decision-027 §Verified live

## What we set out to do
Close the gap decision-027 opened: the CLI names a new task `task-162 - <title-slug>.md`, so two PRs that each
create task-162 write different paths. Git merges both, and the queue no longer forces the second PR to
rebase onto the first. It had already happened once: #81 and #82 both created decision-028, and #82 had to
renumber its record to decision-029 by hand (commit 26f660d1 on `dev`).

## What we learned
- The only shared key is inside the file (frontmatter `id:`) or in the filename's prefix, never the whole
  path, so a uniqueness check has to parse the id, not compare paths. Ids are compared by number, because
  `TASK-075`, `task-75` and `'task-075'` all name one task to the CLI.
- dev already holds one legitimate duplicate: TASK-075 in `completed/` and in `archive/tasks/`. Backlog.md
  1.53 gives an archived task's id to the next `backlog task create` (reproduced in a mktemp sandbox:
  create 1, create 2, archive 2, create → task-2 again). Nothing in a PR can renumber an archived file, so
  the check compares `tasks/` + `completed/` and `decisions/` only.
- A case table row that checks only "exit 1" can pass on an unrelated error (an unreadable id fails closed
  too). Every err row greps for its own `backlog: …` line, so each one proves its own path; with exit-only
  rows, two mutants (the BOM strip and `fullmatch` → `match`) survived.
- "Frontmatter id, else filename" alone lets a hand edit hide a duplicate: a file named `task-6` with an
  `id:` the regex misses (`"id": TASK-5`, `--- ` with a trailing space, two `id:` lines) falls back to 6.
  Reading the key leniently, checking the value in Python (so `'TASK-5' # moved` fails instead of skipping
  the line), failing when the frontmatter id and the filename disagree, and refusing any top-level
  frontmatter line that isn't a plain `key:`, a `- ` item or a comment closes that. A denylist of YAML forms
  kept leaking: after `{id: …}` and `? id` came `<<: {id: …}`, an anchor merged by alias, and an escaped
  `"i\x64"` key, each of which Backlog.md 1.53 reads as a second TASK-5. An allowlist of what the CLI writes
  (every file on `dev` passes it; indented lines are lists and folded-title continuations) holds. The check
  is not a YAML parser; it refuses what it can't read.
- `mutate.py` copies the whole repo and runs every case table per mutant, which takes over half an hour for
  one script's mutants on a loaded machine. To iterate, run the mutants against only the table that covers
  the script (a mktemp copy of `.claude/` per mutant), then leave the full run to CI's nightly.
- PR #81's queue build: a single entry's `base_sha` is `dev`'s tip, and the PR's `merge_commit_sha` is the
  `gh-readonly-queue` head itself (`8980b29`), so what merged is what was tested.

## Dead ends — don't repeat these
- None.

## Decisions (and what would change them)
- `archive/` is not compared. If Backlog.md stops reusing archived ids, add `archive/tasks/` to the task group
  and grandfather TASK-075.

## Follow-ups
- [ ] TASK-162..169: the deferred follow-ups from decision-029 (TASK-159), TASK-156, TASK-088, TASK-076, TASK-155 and the 2026-10-02 hook-probe incident.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `task-hygiene` §Ids, CLAUDE.md §Keep everything current, CONTRIBUTING.md §Flow, spec 08 §Merge queue and §Git and PR rules, `/review-gate` and `/record-learnings`, `project-manager`, `learning-recorder`, `docs-reviewer`, `ci-engineer`, `pr-workflow`
- Test or hook added? — 36 new rows in `.claude/scripts/tests/test-tooling-scripts.sh`, 32 mutants in `.claude/scripts/mutants/backlog.json`
