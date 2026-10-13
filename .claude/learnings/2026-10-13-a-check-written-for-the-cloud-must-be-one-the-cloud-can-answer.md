# A check written for the cloud must be one the cloud can answer

**Key lesson:** Before a routine's gate relies on an API call from a Claude Code cloud session, probe that exact call there: the session's proxy refuses every path outside `repos/<this repo>/...` with its own 403, so check what the proxy enforces (its refusals, word for word) rather than an API it will never answer.

- **Date:** 2026-10-13 · **Task:** task-243 · **Area:** tooling
- **Artifacts:** `.claude/scripts/dependabot/prs.py` (`preflight`, `uv-release`), `.claude/scripts/dependabot/_common.py`
  (`refusal`, `detect_mode`), `.claude/scripts/dependabot/docker_digest.py`, `.claude/scripts/tests/dependabot_fake.py`,
  `.claude/scripts/tests/dependabot_cases.py`, `.claude/scripts/mutants/dependabot.json`,
  `.claude/commands/dependabot-review.md` step 0, spec 08 §CI "Dependabot", decision-048 (TASK-243 AC3/AC6 addendum)

## What we set out to do
Make `/dependabot-review` step 0 pass in a cloud session, where the read-only probe of 2026-10-13 (session
cse_01Q24cxnP5Nu3yXGC2FKjWqW) showed its installation check, its uv release call and Sigstore can't work.

## What we learned
- The step 0 installation check (`gh api user/installations`, then `installation/repositories`) had been written,
  reviewed and merged for the cloud without anyone running it there; both calls answer HTTP 403 "This GitHub API path
  is not available: sessions are bound to their configured repositories". Every cloud run would have stopped at step
  0 with every PR "not reviewed". (Evidence: the probe; the earlier learning's round-2 note that "an
  installation-token call alone would always fail there" guessed the wrong failure.)
- The proxy itself is the bound worth checking: another repository answers HTTP 403 "GitHub access to this
  repository is not enabled for this session". Requiring both refusals, each message matched exactly, is a check the
  cloud can answer, and a 200 (the binding gone) stops the run. The installation's repository selection moves to the
  local run, which has an org owner's credential (`orgs/uw-share-lab/installations`).
- `gh auth status` fails and `gh api user` may fail in a session whose token is a placeholder behind the proxy; a
  repository-scoped call (`gh api repos/<this repo>`) is the auth check that holds in both modes.
- Sigstore is closed off in two places at once (the TUF hosts are Forbidden at the proxy, and another org's
  attestation API is refused by the binding), so there is no offline route; the honest fix is a PROBLEM line that
  says why, not a retry.
- A fake that only knows fixtures can't fail like the proxy. The fake `gh` now refuses, in cloud mode, every path
  outside `repos/` and every other repository with the proxy's two messages, and fails `gh attestation verify`
  whatever the fixtures say; a row that wants another answer names that exact key. Rows that would have passed
  with any 403 (wrong message, right message with a 404, a connection error) pin the word-for-word match.

## Dead ends — don't repeat these
- `gh api user/installations/<id>/repositories` with a `gh` login, locally: HTTP 403 "You must authenticate with an
  access token authorized to a GitHub App". The selected repository list isn't readable that way; the selection is.
- `uw-share-lab/.github` as the "another repository" for the binding check: it doesn't exist (404 locally).
  `astral-sh/uv` is public, stable and the repository the probe saw refused.

## Decisions (and what would change them)
- Session binding in the cloud, installation selection locally (decision-048 addendum) → the proxy answers only
  repository-scoped calls → revisit if the proxy starts answering the installation API.

## Follow-ups
- [ ] task-247 — the Advisory Database calls (`gh api advisories?…`, steps 0 and 2) are outside `repos/`, so the
  proxy may refuse them; no cloud session has made one yet.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/commands/dependabot-review.md` (§Where it runs, step 0, the summary),
  spec 08 §CI "Dependabot", decision-048
- Test or hook added? — rows in `.claude/scripts/tests/dependabot_cases.py` (the fake `gh` in `dependabot_fake.py`
  fails like the proxy), mutants in `.claude/scripts/mutants/dependabot.json`
