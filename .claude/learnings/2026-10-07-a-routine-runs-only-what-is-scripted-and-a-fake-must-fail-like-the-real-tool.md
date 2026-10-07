# A routine runs only what is scripted, and a fake must fail the way the real tool does

**Key lesson:** Before handing a review to a scheduled routine, turn each judgement call into a script with an exit status (ok / FIX / PROBLEM / could-not-run) and test it against fakes that fail the way the real tool fails (npm and gh print a JSON error on stdout and exit non-zero), because a fake that only goes silent lets a "tool exit ignored" mutant survive.

- **Date:** 2026-10-07 · **Task:** task-211 · **Area:** tooling
- **Artifacts:** `.claude/commands/dependabot-review.md`, `.claude/scripts/dependabot/`, `.claude/scripts/tests/dependabot_cases.py`, `.claude/scripts/tests/dependabot_fake.py`, `.claude/scripts/mutants/dependabot.json`, decision-048, PRs #123–#125

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
- A `FIX` class matters: the caret, a dropped `libc` and an unmoved `.python-version` are repaired in the PR,
  while a mismatch with the registry is a hard stop. One exit status for both would make the routine either
  leave fixable PRs open or merge suspicious ones.
- Three mutants survived the first table: a non-zero tool exit read as success, `http()` accepting a non-https
  URL, and `is_major` comparing two components. The fakes went silent on error, so the mutant failed for a
  different reason with the same exit; every clean row was a patch bump. Kills: the fake npm prints npm's JSON
  error object on stdout (as `npm view --json` does), the fake curl refuses a non-https URL as `--proto =https`
  does, an http token realm row checks the refusal message, and a clean minor-bump row.
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
- Test or hook added? — `.claude/scripts/tests/test-dependabot.sh` (in `make tooling`), mutants in `.claude/scripts/mutants/dependabot.json`, `mypy --strict` on the scripts in `make lint`
