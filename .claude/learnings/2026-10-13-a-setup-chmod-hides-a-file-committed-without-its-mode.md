# A setup script's chmod hid four tooling files committed 100644 until a fresh clone showed the diff

**Key lesson:** A script added under a glob `setup-dev.sh` makes executable must be committed 100755 (`git add --chmod=+x`); `make tooling` now refuses one that isn't (`check_file_modes.py`), because the chmod only surfaces as a mode change on a fresh clone, where it dirties the tree and `record-review.py` refuses to attest.

- **Date:** 2026-10-13 · **Task:** task-241 · **Area:** tooling
- **Artifacts:** `scripts/setup-dev.sh`, `.claude/scripts/check_file_modes.py`, `.claude/scripts/tests/test-tooling-scripts.sh` (check_file_modes rows), `.claude/scripts/mutants/gates.json` ("modes:" mutants), branch `fix/setup-dev-file-modes`

## What we set out to do
The weekly Dependabot cloud routine found a fresh clone dirty after `scripts/setup-dev.sh`, and had to set
`core.fileMode=false` to get past `record-review.py`'s clean-tree check. Fix the four files and stop it recurring.

## What we learned
- The cause was `chmod +x .githooks/* .claude/hooks/*.sh .claude/hooks/tests/*.sh .claude/scripts/*.py` in
  `setup-dev.sh` against four files committed 100644: `test-parser-boundaries.sh`, `check_digest_pins.py`,
  `lint_probes.py`, `probe_hook.py` (evidence: `git ls-files -s` showed 100644 for them and 100755 for all 22
  siblings; the new check listed exactly those four before the fix).
- They were meant to be executable: each has a shebang and every sibling in the same glob is 100755. They were
  created by a file tool (mode 644 on disk) on checkouts where the setup script had run long before they
  existed, so disk and index agreed at 644 and nothing local ever showed a diff; only a fresh clone followed by
  the setup script does (they are always run as `python3 <file>` / `bash <file>`, so nothing failed either).
- Reading the index (`git ls-files -s`), not the disk, is what makes the check right: a disk mode can differ from
  the committed one, and the committed one is what a clone gets. The case-table rows give every file the
  opposite mode on disk, so a check that read the disk would flip every verdict.

## Dead ends — don't repeat these
- `core.fileMode=false` hides the symptom on one machine and leaves every other clone dirty; it isn't a fix.
- Completing the task before the last review round. Write `--final-summary` and run `backlog task complete` only
  after the final round (task-hygiene says so): Backlog 1.53 can't edit a task in `completed/` ("Task not
  found"), and files under `backlog/` are not moved by hand. Here the pre-completion copy was restored with git
  three times to re-finalize through the CLI; the first restore used a commit without the Implementation Plan and lost
  it. If it has to be done, restore from the last pre-completion commit that still has the plan, and treat it as
  needing the owner's approval rather than as a recipe.

## Decisions (and what would change them)
- Commit the files 100755 and keep the chmod (a safety net for copies without modes, e.g. a source archive)
  → the check ties the two together → drop the chmod only if nothing outside git ever runs the tooling.
- The check reads `chmod` from the setup script itself rather than repeating its globs, and refuses any chmod
  it can't read (octal, `u+x`, by path, a variable or brace in a glob, `[^...]` and any `[[` form, which fnmatch
  reads differently from bash, a continued line with a `#` in it, a chmod after a `#`, quotes, backslashes or a
  redirection on a chmod line, and `shopt`, `GLOBIGNORE`, `pushd`, `popd` or a `cd` off the repo root anywhere
  on a line). It joins backslash-newline
  continuations and starts a comment only at a word that begins with `#`, as bash does, and fails when the setup
  script is missing, so the list can't drift and moving the script can't switch it off (review rounds 1-3).
  shlex's defaults differ from bash in both of those (a mid-word `#` is a comment to shlex), so a shell-parsing
  check needs `commenters = ""` and its own rules.

## Follow-ups
- none.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `CONTRIBUTING.md` (Setup), `README.md`, `.claude/agents/ci-engineer.md`, spec 08 §CI table and §Testing, `.claude/skills/pr-workflow/SKILL.md`, `make help`
- Test or hook added? — `.claude/scripts/check_file_modes.py` in `make tooling`, rows in `test-tooling-scripts.sh`, mutants in `gates.json`
