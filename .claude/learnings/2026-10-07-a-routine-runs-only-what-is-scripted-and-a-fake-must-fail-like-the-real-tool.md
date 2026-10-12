# A routine runs only what is scripted, and a fake must fail the way the real tool does

**Key lesson:** Before handing a review to a scheduled routine, turn each judgement call into a script with an exit status (ok / FIX / PROBLEM / could-not-run) and test it against fakes that fail the way the real tool fails (npm and gh print a JSON error on stdout and exit non-zero), because a fake that only goes silent lets a "tool exit ignored" mutant survive.

- **Date:** 2026-10-07 · **Task:** task-211 · **Area:** tooling
- **Artifacts:** `.claude/commands/dependabot-review.md`, `.claude/scripts/dependabot/`, `.claude/scripts/tests/dependabot_cases.py`, `.claude/scripts/tests/dependabot_fake.py`, `.claude/scripts/mutants/dependabot.json`, `.github/dependabot.yml` (cooldown), `.githooks/pre-push`, `.claude/hooks/autofix.sh`, decision-048, PRs #123–#125 (review rounds here are numbered from the focused review as round 1; the commits number from the full gate)

## What we set out to do
Commit the procedure that merged Dependabot PRs #123–#125 as `/dependabot-review`, so a weekly cloud routine
with no context and no access to the owner's machine can run it, and script its checks.

## What we learned
- The checks that were judgement in the 2026-10-07 run all reduce to comparisons with a registry: uv.lock
  hashes against PyPI's JSON API, npm lock entries against `npm view <pkg>@<ver> --json` (integrity, tarball,
  dependencies, `os`/`cpu`/`libc`, `_npmUser`, `dist.attestations`), a docker tag against the registry's
  `Docker-Content-Digest` for the OCI-index `Accept` header. Run against the real #123–#125 diffs, the scripts
  pass the merged heads and catch the caret Dependabot wrote into #124's lock (evidence: `npm_lock.py --head
  34059c0f` prints the FIX; the merged head is clean).
- Comparing the lock's `libc` with the registry manifest catches a dropped `libc` on a bumped entry too, which
  a diff against the old entry can't (the old entry is another version).
- A `FIX` class matters: the caret and a dropped `libc` are repaired in the PR (a new Python release, first a
  FIX for `.python-version`, became a hard stop in review: decision-048),
  while a mismatch with the registry is a hard stop. One exit status for both would make the routine either
  leave fixable PRs open or merge suspicious ones.
- Three mutants survived the first table: a non-zero tool exit read as success, `http()` accepting a non-https
  URL, and `is_major` comparing two components. The fakes went silent on error, so the mutant failed for a
  different reason with the same exit; every clean row was a patch bump. Kills: the fake npm prints npm's JSON
  error object on stdout (as `npm view --json` does), the fake curl refuses a non-https URL as `--proto =https`
  does, an http token realm row checks the refusal message, and a clean minor-bump row.
- The focused review found what a diff-shaped check misses (review round 1): a lock entry that keeps its key
  but becomes another package (`"name": "evil"`, an npm alias) or a `link`, provenance read from one file
  while PyPI accepts files added to a release later, npm provenance checked for presence when trusted
  publishing makes `_npmUser` the same generic user for any repository, and `node_modules/` never reinstalled
  after switching to the PR, so the tests would have run dev's packages. Compare what an entry *is* (its
  registry name, every file's publisher, the provenance's source repository), not only what changed in it.
- The full review gate (round 2) found that an unattended reviewer of a bot's PR runs untrusted code: the
  checkers lived on the PR branch (a PR could rewrite them to pass), `make test` would run a `package.json`
  script or a `[build-system]` requirement the PR added, and a Dockerfile `RUN` line or a workflow
  `permissions:` would merge unread, because every check looked only at versions and pins. The fix is to trust
  only `dev`: run the checkers from `dev`'s copy, gate the PR (`prs.py check`: Dependabot-only verified commits,
  files by ecosystem from git, the head unchanged) before anything of it runs, reject any change beyond
  versions and pins, keep the token out of the tests' environment, and queue with `--match-head-commit`.
- "Run the dependencies without the token" has to cover every path that loads them, not just the commands the
  procedure names: rounds 3 and 4 found the pre-push hook's `make lint` and the autofix hook's ruff, prettier and
  eslint (both run after the PR's lock is installed). Both now strip the token, and a gates row with a recording
  fake pins it. A token scope is part of the same budget: `workflows` was dropped, so the owner queues
  github-actions PRs.
- A legitimate pipeline can publish a bad release that passes every provenance check; Dependabot's `cooldown`
  (7 days) plus a checker stop on a younger release is the cheap defence, and leaves security updates (which
  ignore cooldown) to the owner.
- Every outside call through a subprocess (`git`, `curl`, `npm`, `gh`) made the whole family testable with PATH
  fakes and no network, the same way `changelog.py` fakes `gh`.

## Dead ends — don't repeat these
- `make mutate-changed` with 62 new mutants at the default 8 jobs drove the machine's load past 300 alongside
  other sessions: each mutant runs every case table. Run a new family's mutants against its own table first
  (a scratch loop that copies only the scripts and the table), then the full `mutate.py` sharded, at fewer jobs.

## Decisions (and what would change them)
- Weekly routine over a `dependabot[bot]` exemption from the gates (decision-048) → none of the 2026-10-07
  findings fails a test, so an exemption would merge them → revisit if the routine merges something it
  shouldn't have.

## Follow-ups
- [ ] none.

## Propagated to
- Skill / agent / CLAUDE.md updated? — spec 08 §CI "Dependabot", `.claude/agents/ci-engineer.md`, `.claude/skills/pr-workflow/SKILL.md`, `.claude/skills/python-standards/SKILL.md`, `.claude/skills/autolint/SKILL.md`
- Config? — `.github/dependabot.yml` (7-day `cooldown`), `.githooks/pre-push` and `.claude/hooks/autofix.sh` (their tools run without the GitHub token)
- Test or hook added? — `.claude/scripts/tests/test-dependabot.sh` (in `make tooling`), mutants in `.claude/scripts/mutants/dependabot.json`, `mypy --strict` on the scripts in `make lint`; the token-stripping rows in `.claude/hooks/tests/test-openproceedings-gates.sh` with mutants in `.claude/scripts/mutants/gates.json`

## Addendum — 2026-10-08 (TASK-212: the manifest/lock check moved into `make tooling`)

- **A check that only the weekly routine runs catches a defect a week late, and only on Dependabot's PRs.** The
  caret Dependabot writes into the lock's `packages["frontend"]` (#124 `eslint-config-next`, #100 `vitest`) is a
  plain invariant of the checkout, so it now lives in `make tooling` (CI `claude-tooling`) as
  `.claude/scripts/dependabot/npm_specs.py`, and `npm_lock.py` imports its `mismatches()` instead of keeping a
  copy (evidence: `npm_specs.py --root` on detached checkouts of 34059c0f and 1e73d7d0 exits 1 naming the
  caret; on this branch it exits 0).
- **A script the routine runs from dev's copy needs `--root`.** The routine extracts dev's
  `.claude/scripts/dependabot/` into its scratch directory, so a script that finds the repo from `__file__`
  reads the scratch directory, which holds no `package.json`: "nothing to check" would pass every PR. `--root .`
  reads the PR checkout, and a checkout with neither file, or no directory, fails (QA and docs review: a silent
  "match" on nothing compared is the failure to design out; a first version failed only under an explicit
  `--root`, which a forgotten `--root` never reaches).
- **Compare JSON values with their type** (security review): in Python `1 == 1.0 == True`, so a spec of `1`
  matched a lock's `true`.
- **A row that expects only "non-zero" doesn't test what its label says** (focused review): an argparse error
  or a traceback passes it. Every failing row of the new check matches its own message (`expect_spec`).
- **Malformed is not fixable.** A section that isn't an object has nothing to copy across, so `npm_lock.py` now
  reports it as a PROBLEM, not a FIX; and a root `workspaces` naming a directory the check doesn't know fails,
  so a new workspace can't go unchecked.
- Dead end, again: `make mutate-changed` at the default jobs, beside other sessions, took the load past 200 and
  starved `make tooling` for over ten minutes; `mutate.py --changed --jobs 4` was then started and abandoned
  (about 12 mutants in 45 minutes at load 100-200). A scratch loop ran every mutant of the changed files (65)
  against only the two tables that exercise them, 4 at a time; `mutate.py` fails a mutant on any table, so its
  kills carry over. Such a loop must first check that the unmutated copy passes those tables, or every "killed"
  may be vacuous: this one didn't, and the pr-reviewer verified the baseline afterwards.
- Propagated to: spec 08 §Testing, §CI (`claude-tooling` row, "Dependabot"), `.claude/commands/dependabot-review.md`
  step 3, README §Tests and checks, `.claude/skills/pr-workflow/SKILL.md`, `.claude/agents/ci-engineer.md`; rows in
  `.claude/scripts/tests/test-tooling-scripts.sh` and `dependabot_cases.py`; mutants in
  `.claude/scripts/mutants/dependabot.json`.

## Addendum — 2026-10-11

- **Dependabot's docker `cooldown` holds only on Docker Hub.** dependabot-core's docker update checker
  (`registry_tag_release_date`) dates a tag from Docker Hub's API alone; for any other registry it logs "No
  verified registry publication date source", skips the cooldown, and the PR body says "Cooldown could not be
  applied". PR #132 (`ghcr.io/astral-sh/uv` 0.13.0, published 2026-10-09T19:49Z) arrived about 20 hours later
  despite `cooldown: { default-days: 7 }`, and the procedure's "for docker the hold is the `cooldown` alone" was
  wrong for it. Both #132 reviewers raised the age as a Must. `docker_digest.py` now dates a ghcr.io image by
  the earliest verified (Rekor or TSA) timestamp in `gh attestation verify --format json` and stops one under 7 days
  (evidence: run against #132's head it prints `PROBLEM … first attested 2.2 days ago`), and stops an image on
  any registry nothing dates. The attestation time is a verified lower bound on the image's age; an image
  config's `created` can be set to anything (reproducible builds set it to 1970), so it would fail open.
- **A config option that silently degrades is a check to script.** "Cooldown could not be applied" is a
  per-PR notice nobody reads; the hold had been assumed for every docker image since TASK-149. A Docker Hub
  lookup that fails (timeout, 429, 403) skips the cooldown with the same notice, so `prs.py check` now stops any PR
  whose body carries it (docs review).
- **An attestation dates an image only if it is the right publisher's.** `--owner astral-sh` accepts an
  attestation from any repository and workflow of the org (a PR preview build included), so the earliest
  timestamp of *any* attestation could make a new image look old (security review). The age now comes only from
  attestations whose source repository and signing workflow (its `@ref` aside) match the previous pin's, and a new
  publisher, or an unattested previous pin, is a PROBLEM.
- **Compare timestamps as times.** `min()` over ISO strings with different UTC offsets picks the wrong one;
  a row with `-04:00` and `Z` stamps whose text order differs from their time order kills that mutant.
- **A 0.x minor of uv is a breaking release** (0.13.0 had a "Breaking changes" section), but `is_major` only
  compares the first number, so the checkers passed it. `.github/dependabot.yml` now ignores `astral-sh/uv`
  `version-update:semver-minor`, and `docker_digest.py` stops a 0.x minor of any image too, so the hold doesn't
  rest on the ignore rule matching (code review). `is_major` itself is unchanged: uv and npm 0.x packages
  (ruff and others) still pass as minors there, an owner's call.
- **Docker images get no Dependabot alert or security update** (the Advisory Database has no docker ecosystem),
  so a uv minor ignored by config surfaces nowhere unless the routine looks: it now compares the pinned uv minor
  with the latest release and checks uv's advisories every run.
- Propagated to: `.github/dependabot.yml`, spec 08 §CI "Dependabot", `.claude/commands/dependabot-review.md`
  (hard stops, steps 1 and 2), `.claude/agents/ci-engineer.md`, decision-048 (amended), the `docker_digest.py` and
  `prs.py` docstrings; rows in `dependabot_cases.py` (and the fake `gh` in `dependabot_fake.py`), mutants in
  `.claude/scripts/mutants/dependabot.json`.
