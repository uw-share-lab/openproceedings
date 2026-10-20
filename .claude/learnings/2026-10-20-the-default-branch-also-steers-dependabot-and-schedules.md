# Switching the default branch also moves Dependabot and every scheduled workflow

**Key lesson:** Before changing a repo's default branch, land `target-branch:` in `.github/dependabot.yml` and an explicit checkout ref in every `schedule:` workflow on the branch that will become the default. GitHub reads both from the default branch, so a switch on its own sends Dependabot's PRs and the nightly to the new default.

- **Date:** 2026-10-20 · **Task:** TASK-271 · **Area:** ci, process
- **Artifacts:** `.github/dependabot.yml`, `.github/workflows/nightly.yml` (`resolve`), `.github/workflows/pr-gates.yml` (`pr-base`), `.claude/scripts/tests/test-default-branch.sh`, decision-052

## What we set out to do
Make `main` the default branch for the open-source repo, keep `dev` as the integration branch, and keep forks.

## What we learned
- **Dependabot follows the default branch.** It reads its config from the default branch and opens version
  updates against it unless `target-branch` names another. Security updates always target the default branch,
  whatever `target-branch` says (they are off here).
- **A schedule runs the default branch's copy.** It runs that copy of the workflow file, on that branch's head.
  A scheduled run that should test `dev` has to check out `dev` itself, and it is listed under the default
  branch's sha. An edit to the file reaches the schedule only once it is on the default branch.
- **Resolve the commit once, not per job.** A checkout of `ref: dev` in each job resolves `dev` when that job
  starts, and with 40 nightly jobs behind a 20-at-once limit, some start hours late. A merge in between would
  have jobs testing different commits. A first `resolve` job reads `dev`'s head once (`git ls-remote`) and
  every job checks out its output (code-reviewer, gate round 1).
- **Order matters.** Because both read the default branch, the fix has to be on `main` (a release) before the
  switch.
- **Forks open PRs against the default branch.** After the switch, a fork's PR goes to `main` unless the
  contributor picks `dev`. The `pr-base` check fails any PR into `main` except the same-repo promotion and says
  to retarget it.
- **The access was already in place.** Before the switch, only three accounts had write access and there
  were no outside collaborators. A public repo can't disable forking or hide a branch.
- **Ids from a stacked branch.** The CLI numbers a new task from the branch's own files. An unmerged PR's
  task-270 meant this branch would also get 270. Cherry-picking that PR's commit, creating the task (271) and
  dropping the commit with `git rebase --onto` gave the next free id within the backlog guard.

## Dead ends — don't repeat these
- Checking out `dev` by name in every nightly job (see above).
- `grep -x` to require one 40-hex sha: it matches line by line, so two shas on two lines pass. Use
  `[[ "$sha" =~ ^[0-9a-f]{40}$ ]]`.
- Switching the default branch first and fixing the config "at the next release": until then, Dependabot
  targets `main` past the merge queue, and the nightly tests `main`.
