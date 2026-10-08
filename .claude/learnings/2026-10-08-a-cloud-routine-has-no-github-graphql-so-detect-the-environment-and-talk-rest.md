# A Claude Code cloud session has no GitHub GraphQL, so a routine detects where it runs and talks REST

**Key lesson:** Before handing a procedure to a cloud routine, run its every GitHub call in that environment: a Claude Code cloud session refuses all GraphQL (so every `gh pr` command) with a 403 that names the REST and CCR routes, and its token is a proxy-injected network secret, so use `gh api repos/...` everywhere, detect cloud by that 403 message, and replace any check that assumes the token sits in `GH_TOKEN`.

- **Date:** 2026-10-08 · **Task:** task-213 · **Area:** tooling
- **Artifacts:** `.claude/scripts/dependabot/prs.py` (`preflight`, `queue`, REST `list`/`check`/`watch`), `.claude/scripts/record-review.py` (`--attest --pr`), `.claude/scripts/tests/dependabot_fake.py` (cloud mode), `.claude/scripts/tests/dependabot_cases.py`, `.claude/commands/dependabot-review.md`, decision-048's addendum, spec 08 §CI "Dependabot"

## What we set out to do
Make `/dependabot-review` (TASK-211) run in the weekly routine's real environment, where the owner's live test
runs on 2026-10-08 showed it couldn't, without losing any of decision-048's safety properties.

## What we learned
- Every GraphQL call from a Claude Code cloud session answers HTTP 403, "GitHub GraphQL is not available from
  Claude Code sessions; use the REST API …", which also lists CCR routes for what only GraphQL did (review
  threads, auto-merge via `PUT`/`DELETE repos/<o>/<r>/pulls/<n>/ccr/auto_merge`, ready-for-review). So `gh pr
  list`, `view`, `checks` and `merge` all fail there, and `record-review.py --attest` (which finds the PR with
  `gh pr view`) failed *silently*: it read any `gh pr view` failure as "no PR yet" and exited 0. Evidence: the
  owner's runs; the CCR route is a 404 from a normal login (`gh api repos/uw-share-lab/openproceedings/pulls/1/ccr/review_threads`).
- The session's `GH_TOKEN`/`GITHUB_TOKEN` are placeholders and an egress proxy adds the real credential for
  api.github.com: `gh auth status` reports the token invalid while every `gh api` call succeeds. A check that the
  token "lives only in GH_TOKEN" can't pass, and the real property (no process can read the token) holds by
  construction; what is still checkable is that gh has no stored login and no variable holds a token-shaped value.
- REST covers everything the routine needs: open PRs (`pulls?state=open&base=dev`, filtered to
  `dependabot[bot]`), files and commits with `verification` (`pulls/<n>/files`, `pulls/<n>/commits`), the queue
  (a `gh-readonly-queue/dev/pr-<n>-<sha>` branch exists while the PR is in a queue build: `git/matching-refs`),
  check runs, merge-group runs, cancel/rerun, and the advisory database (`advisories?ecosystem=npm&affects=next`).
  Evidence: each call run against the repository on 2026-10-08.
- Detecting the environment by its behaviour (GraphQL's answer) beats guessing from variables: a wrong guess
  either way only picks a queue route that then fails, and any other GraphQL failure stops the run.
- The CCR auto-merge route has no `--match-head-commit`. Reading the head before and after the PUT, and turning
  auto-merge off on a move, narrows the race; the queue's `review-attested` build (the body must attest the exact
  head merged) is what closes it.
- Comparing GitHub's file list with git's found a gap in the TASK-211 check: `git diff --name-only` with rename
  detection lists only a rename's new path, so a file renamed onto an allowed name hid its old path. The check
  now runs `--no-renames` and adds GitHub's `previous_filename`.

## Dead ends — don't repeat these
- `gh auth status` as the auth check in a cloud session: it fails on the placeholder while auth works. Use a
  real call (`gh api user`).
- A fake that answers GraphQL in every mode: it let the TASK-211 scripts pass a table the real routine couldn't
  run. The fake now has a cloud mode, and every `prs.py` row runs in it unless it is about local.

## Decisions (and what would change them)
- REST everywhere, not REST only in the cloud → one code path, tested once → none expected.
- Cloud queueing through `PUT …/ccr/auto_merge` with any non-2xx left for the owner → its request shape isn't
  documented to us → a documented shape (or an expected-head parameter) would let the routine pass it.

## Follow-ups
- [ ] none (what needs a cloud run to confirm is listed in the PR for the owner's one-off probe).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/commands/dependabot-review.md`, spec 08 §CI "Dependabot", decision-048 (addendum), `.claude/skills/pr-workflow/SKILL.md` (`--attest --pr`), `.claude/agents/ci-engineer.md`
- Test or hook added? — the cloud mode of `.claude/scripts/tests/dependabot_fake.py` and its rows in `dependabot_cases.py`; the `--attest` rows in `.claude/hooks/tests/test-openproceedings-gates.sh`; mutants in `.claude/scripts/mutants/dependabot.json` and `gates.json`
