---
id: decision-048
title: >-
  A weekly Claude routine reviews and queues Dependabot PRs; the PR gates stay
  on for them
date: '2026-10-07 20:54'
status: accepted
---
## Context

Dependabot (`.github/dependabot.yml`, weekly; spec 08 §CI "Dependabot") opens about one grouped PR a week
per ecosystem into `dev` (github-actions, uv, npm, docker), plus one PR per docker digest bump. Every PR into
`dev` must pass the six required checks, two of which a bot's PR can't pass alone: `learnings` (an entry or the
`no-learning` label) and `review-attested` (the body attests an APPROVE record for the head, which only `record-review.py` writes
after a review). Until 2026-10-07 the owner's session reviewed each PR by hand. The run that merged #123–#125
on 2026-10-07 found real work in them: a caret Dependabot wrote into the lock's workspace entry (#124), `libc`
fields an older local npm dropped, seven Next.js advisories `npm audit` didn't show, two older high advisories
with lockfile-only fixes, and a docs version to move.

Options considered:
1. **Exempt `dependabot[bot]` from `learnings` and `review-attested`**, and let a green PR merge unreviewed.
   Rejected by the owner (2026-10-07): CI would pass every finding above, because none of them fails a test
   (`npm ci` accepts the caret; a dropped `libc` installs on the runner; advisories are not test failures). It
   would also be the first author-based exemption in the gates, which the attestation's honesty check
   (spec 08 §CI) was built not to have.
2. **The owner reviews each PR by hand** (the practice so far). It works, but takes a session a week and
   depends on the procedure being remembered.
3. **A weekly scheduled Claude routine runs a committed procedure** (`/dependabot-review`): a cloud Claude
   Code session on a fresh clone, with no access to the owner's machine, reviews each open Dependabot PR
   through the same gates as any PR, fixes what is needed, attests and queues it, and leaves anything
   suspicious open with a comment.

## Decision

We adopt option 3 (owner's decision, 2026-10-07). A weekly routine runs `/dependabot-review`
(`.claude/commands/dependabot-review.md`) with the scripted checks in `.claude/scripts/dependabot/`. It may
merge, through the merge queue only, a Dependabot PR that passes the supply-chain scripts, the release-note
review, the tests, the reviewers and every required check. It never merges, and leaves open with a comment
for the owner, a PR with a commit that isn't Dependabot's (signed and verified), a file outside its
ecosystem or a change beyond dependency versions and pins, an integrity or URL mismatch, a new publisher or lost
provenance, a new install script, a new package, a uv or npm release younger than 7 days (amended
2026-10-11: or a ghcr.io image first attested under 7 days ago by the previous pin's publisher, or without such an
attestation, an image on a registry other than Docker Hub and ghcr.io, a 0.x minor of an image, or a PR whose body
says Dependabot couldn't apply its cooldown), a digest that
doesn't resolve or a failed attestation, a red required check it can't fix, a Must it can't fix, any semver-major, anything
touching `tantivy`, or a new Python release (patch or minor). The gates stay on for Dependabot PRs.

The review gate of TASK-211 shaped three parts of this:
- **The routine runs untrusted code, so it trusts only `dev`.** It runs the checkers from `dev`'s copy, gates
  each PR with `prs.py check` before anything of the PR runs, rejects any change beyond versions and pins (a
  `package.json` script, a `[build-system]` requirement, a Dockerfile `RUN` line or a workflow `permissions:`
  would otherwise run in `make test` or merge unread), and queues with `--match-head-commit`.
- **A legitimate pipeline can still publish a bad release**, so Dependabot's `cooldown` holds every version
  update back 7 days (a compromised release is most often pulled within days), and the uv and npm checkers stop
  a younger one, which then can only be a security update: the owner decides. For actions and docker images
  the hold is the `cooldown` alone (no checker reads their age). *Amended 2026-10-11:* Dependabot dates a docker
  tag only on Docker Hub and skips the `cooldown` for other registries (PR #132, uv 0.13.0 on ghcr.io, came about
  20 hours after its release), so `docker_digest.py` now stops a ghcr.io image first attested under 7 days ago
  (by the previous pin's publisher) and an image on any other registry, and `prs.py check` stops a PR whose body
  carries Dependabot's "Cooldown could not be applied" notice (a failed Docker Hub lookup skips it too;
  Dependabot gives no date for any ghcr.io update, so every ghcr.io PR carries it and the attestation age is the
  owner's evidence); for actions and Docker Hub images the hold is otherwise the `cooldown` alone.
- **A new Python patch is the owner's.** Spec 08's "Python pin" says extracted text can depend on the release;
  TASK-208 proved 3.12.9 → 3.12.15 changed nothing by replaying the whole crawl cache, which needs `data/`, which
  the routine doesn't have. A new digest for the same tag carries no parser change and is merged like any other.

## Consequences

- Spec 08 §CI "Dependabot" states the routine, what it may merge and what it leaves open; `ci-engineer`
  points to the command. The procedure changes only by PR, reviewed like any other, so the routine runs
  what was reviewed (TASK-211).
- The checks that were judgement in the 2026-10-07 run are now scripts with a case table
  (`.claude/scripts/tests/test-dependabot.sh`, in `make tooling`) and mutants
  (`.claude/scripts/mutants/dependabot.json`), so a regression in a check fails CI.
- The routine needs, in its cloud environment: `gh` authenticated with a **fine-grained token for this
  repository only, with `contents`, `pull requests`, `issues` and `actions` read and write, and nothing
  else** (no `administration`, so it can't touch the rulesets; no `workflows`, because with it a leaked token
  could push a workflow that runs with the repository's secrets), held in `GH_TOKEN` only. So the routine
  reviews and attests a github-actions PR but doesn't queue it (queueing a change to `.github/workflows/` may
  need `workflows`): its summary asks the owner to run `gh pr merge <n> --auto --match-head-commit <sha>`. It also needs Node 22, npm,
  uv 0.12.22 or later, Python 3.11 or later, shellcheck; Playwright's Chromium and Docker when available. Where `make e2e` or
  `deploy/smoke-test.sh` can't run, the PR names the CI check that stands in (`playwright`, `web-image`). The
  tests, the reviewers' runs, the pre-push hook's `make lint` and `make tooling`, and the autofix hook's ruff,
  prettier and eslint run without the token in their environment. What the cloud environment gives every process (a git credential helper, a proxy) stays
  reachable by dependency code; the shape checks (only registry-verified versions run) are what bound that.
  Its commits carry the git identity the environment
  configures, which must name a person (the command stops on an empty one or one naming an AI), and no AI
  attribution (the hooks and CI's `attribution` check refuse it).
- The attestation stays an honesty check, not an access control (spec 08 §CI): the token can edit any PR body.
  The fine-grained scope and the merge queue's required checks bound what a leaked token could do; the
  owner's review of `main` promotions stays the access control for releases.
- Review records are per clone (`.git/op-reviews/`), so the routine records, pushes and attests in one
  session; nothing it records survives to the next run.
- What would change this: the routine merging something a later review shows it shouldn't have (tighten
  the scripts or the hard stops, or go back to option 2), or GitHub offering a reviewed-bot path that keeps
  the attestation meaningful.
- The routine changes no rule about matching, `index_version` or search records. A dependency it merges can
  change behaviour exactly as a hand-merged one could; CI's golden, contract and differential suites guard
  that, and the Python release, the one bump known to change ingest output, stays with the owner.

## Addendum (2026-10-08, TASK-213: the cloud session has no GraphQL, and its token is a network secret)

Test runs of the routine in its real cloud environment on 2026-10-08 found two assumptions above wrong:

- **GraphQL is refused.** A Claude Code cloud session answers every GitHub GraphQL call with HTTP 403 ("GitHub
  GraphQL is not available from Claude Code sessions; use the REST API …"), so `gh pr list`, `view`, `checks`
  and `merge` fail, and with them `prs.py list`, `check` and `watch`, `gh pr merge --auto --match-head-commit`
  and `record-review.py --attest`. REST works, and the session offers CCR routes for what only GraphQL did,
  among them `PUT` and `DELETE repos/<repo>/pulls/<n>/ccr/auto_merge`.
- **The token is not in `GH_TOKEN`.** `GH_TOKEN` and `GITHUB_TOKEN` hold placeholders (`gh auth status` calls
  the token invalid) and an egress proxy adds the real credential to requests for api.github.com. The
  "held in `GH_TOKEN` only" rule above, and step 0's `gh auth status` check, can't be met there.

We keep every safety property above and change only how it is reached:

- Everything the procedure asks GitHub goes through REST (`gh api repos/<repo>/...`), in both environments:
  `prs.py list`, `check` (now also comparing GitHub's file and commit lists with git's), `watch` (the PR's
  `merged` and `auto_merge`, the timeline's latest merge-queue event, the queue's build branch, the check runs;
  a hung queue build is cancelled and rerun through the Actions REST endpoints), the advisory lookup, and
  `record-review.py --attest --pr <n> --repo <owner>/<name>`, which also refuses a PR whose head isn't the
  reviewed HEAD (and runs from `dev`'s copy, like the checkers: a PR branch may carry an older recorder).
- **The environment is detected, not assumed.** `prs.py` asks GraphQL for the viewer: the session's 403
  message is **cloud**, an answer is **local** (a maintainer's clone with a real `gh` login), anything else
  stops the run. Step 0 checks auth with a real call (`gh api user`).
- **What "the token can't leak to dependency code" means now.** In the cloud no process holds the token, so
  none can read or send it elsewhere; `prs.py preflight` checks what is checkable: no real token in `GH_TOKEN`
  or `GITHUB_TOKEN` (one there is reported; step 5 strips it), and no stored `gh` login (a file dependency code
  could read, which step 5 can't strip: a stop). Any process can still make requests through the proxy while
  the session lives, the same class as the git credential helper this record already names; the token's
  narrow scope and the shape checks bound it. Locally a maintainer's stored login is accepted: it is their own
  machine, where `make test` already runs with it.
- **Queueing.** Locally `prs.py queue` runs `gh pr merge <n> --auto --match-head-commit <sha>`, as before. In
  the cloud it uses `PUT …/ccr/auto_merge`, whose request shape isn't documented to us, so any non-2xx leaves
  the PR open for the owner. There is no `--match-head-commit` there: `queue` reads the PR immediately before
  and after the PUT. A PR GitHub already shows set to merge is not touched (a re-queue). If the head moved, a
  failed call left the PR set to merge, or GitHub accepted the call but shows nothing set to merge, it
  sends `DELETE …/ccr/auto_merge`, reads the PR back and leaves it open; a PR that closed meanwhile is left
  alone; a PUT that times out, or a read after it that fails, is undone the same way. If the DELETE fails, or GitHub still
  shows the PR set to merge (turning auto-merge off doesn't take an entry out of the queue), it says auto-merge
  may still be on or the PR may still be queued, for the owner. (Superseded 2026-10-16: the cloud is notify-only and
  doesn't queue; `prs.py` no longer has the CCR route. See the last addendum.)
- **The residual race.** A push that lands after `queue`'s second read but before GitHub acts on the PUT is
  not caught by the script. The merge queue closes it: its build runs `review-attested` for each queued PR
  (`merge_group_gate.py`), which requires the PR's current body to attest the exact head the queue merges,
  and the routine attested only the head it reviewed, so a moved head fails the build and nothing merges.
  The attestation is an honesty check (above), so someone holding a writer's token who also rewrites the
  body defeats it, as they could defeat `--match-head-commit` by enabling auto-merge themselves, and could
  then land code on `dev`; the owner's review of `main` promotions stays the access control for releases. In
  the cloud, dependency code still running in the session could do both through the proxy. The procedure looks
  for leftover processes from the PR's dependencies before it queues (step 5), which catches accidents such
  as a dev server left running but can't rule out code that hides itself (a renamed process, a file it wrote
  that runs later); what bounds that is the rule above that only registry-verified versions run, and the
  token's narrow scope. (Superseded 2026-10-16: the cloud no longer queues, and locally `--match-head-commit`
  applies; see the last addendum.)
- **Options.** The alternative to the CCR route was to attest in the cloud and leave every queueing to the
  owner, as for github-actions PRs: no undocumented route and no race, at the cost of a manual step each week
  for every PR, which is most of what decision-048 set out to remove. We take the CCR route, with every
  failure leaving the PR open; if it proves unreliable, that alternative is the fallback. (Superseded 2026-10-16: the cloud is notify-only; see the last addendum.)
- **Not yet exercised from a cloud session** (as of 2026-10-08): the CCR `PUT`/`DELETE`, the job-log download
  (a redirect to a storage host the egress proxy may not allow) and `gh attestation verify` (sigstore hosts).
  The `PUT`, the log download and the attestation fail closed (the PR stays open). A failing `DELETE` does
  not: auto-merge may stay on (`queue` exits 2 and says so, first in the run's "for the owner"), and then only
  `review-attested` stops a moved head. TASK-213 stays open until a cloud run confirms them. (Superseded
  2026-10-13: TASK-213 is closed, and what is still unconfirmed moved to TASK-243; see the addendum below.)
- What would change this: a documented CCR request with an expected head sha (then pass it), or GraphQL
  returning to cloud sessions (then use `--match-head-commit` there too).

## Addendum (2026-10-13, TASK-242: a red test on a stale base)

The hard stop "a red required check it can't fix" covers CI's checks; the procedure's step 5 also stopped on any
red local test the bump didn't cause. PR #143 (hypothesis 6.168.3 → 6.168.4, `uv.lock` only) showed a case
neither covered: `make test` on its head failed `test_verification_scale.py`'s `width_is_free`, a wall-time
check, on a loaded machine. PR #144 had already moved that check to CPU time on `dev` (`7df168d3`), but #143's
base predated #144. CI's `test` on the head was green, and `make test` on `dev` with #143's `uv.lock`, the
tree the merge queue builds, passed in full. The reviewer queued the PR on that evidence, which the procedure
didn't name.

We keep the hard stop and name the one exception, checked in the routine's own run: the base is behind `dev`; `dev`
hasn't changed the PR's files since the base (so `dev` with those files is the tree the queue builds; otherwise the
routine asks Dependabot to rebase); `make test` passes in full on that tree, in a separate worktree, without the
GitHub credential; a named commit on `dev` that isn't in the PR's head fixes that failure (it changes the test or
the code it checks, and it or its PR, opened by a person, names the test); every other red test on the head is
resolved; and CI's `test` on the head the routine queues is green. The PR body records all of it, and the summary
lists the waiver for the owner. A red test with no identified fix (a flaky test, an unfixed failure) stays a hard
stop even if the merged tree passes. The merge queue still runs `test` on the merged tree before anything merges.
No script encodes the rule: it compares test runs and commits, which the routine judges, as it judges a red check.
What would change this: a waived test that later proves to have been the bump's doing (then drop the exception and
request a rebase instead).

## Addendum (2026-10-13, TASK-213 closed: what the first cloud runs showed)

- **Cloud writes go through the Claude GitHub App, not a fine-grained token.** The first scheduled run (2026-10-13,
  session cse_01CgK2U5uwNVM1qnbnWBXb4u) reviewed #142 and #143 over REST, but every write answered 403 "Resource
  not accessible by integration": the Claude GitHub App wasn't installed on `uw-share-lab`. The owner installed it
  that day (about 15:55Z). A manual run (session cse_01WYQw7QfZwJp36tz47nWjhR) then posted #142's hard-stop comment
  at 17:04:05Z, which GitHub records as `performed_via_github_app: claude`. So the credential depends on where the
  routine runs. Locally it is the maintainer's own `gh` login (the TASK-213 addendum). In the cloud it is the App's
  installation, whose repository selection and permissions take the place of the fine-grained token named above.
  The App sets its own permissions. Read with `gh api orgs/uw-share-lab/installations` on 2026-10-13, they are
  actions, checks, contents, discussions, issues, pull requests, repository hooks and `workflows` write, plus
  administration, members and merge queues read, and the installation covered all of `uw-share-lab`'s repositories.
  That is wider than this record's bound in two ways. The repository selection is the owner's to narrow; the
  command's step 0 now checks, in the cloud, every Claude installation the user can reach (another account's
  included: `gh api user/installations/<id>/repositories`, or `installation/repositories`), and stops the run
  unless together they list only this repository, or when the fallback call fails too. `workflows` and
  repository-hooks write can't be removed (the App sets them; a webhook is a channel out of the repository).
  Whether the routine should run dependency code in a session holding them is an open question for the owner
  (TASK-243).
- **`gh attestation verify` doesn't run in the cloud.** It failed with "error creating Sigstore verifier: no
  valid Sigstore verifiers could be initialized". `docker_digest.py` stopped the image (fail closed, as
  designed), so every ghcr.io PR goes to the owner until it runs there.
- **The posted comment ended with a "Generated by Claude Code" footer**, which the procedure forbids in PR
  comments. Neither the routine's text nor a hook put it there; it was removed at 17:06:30Z. The
  committed `.claude/settings.json` now sets Claude Code's `attribution` (`commit` and `pr` empty, `sessionUrl`
  false), which a single-repo cloud session reads. Its docs name commits and PR descriptions only, so
  `/dependabot-review` now reads back every comment and PR body it writes and removes anything added. TASK-243
  confirms both on the next cloud run.
- **Until the owner narrows the installation (and any other account's), every cloud run stops at step 0** with
  "limit the Claude App installation to openproceedings" first under "for the owner". That is by design: the run
  executes dependency code, which can use the session's credential through the proxy.
- **Still unconfirmed from the cloud (TASK-243):** step 0's installation calls, the CCR auto-merge `PUT` and
  `DELETE`, the job-log download, a push, `gh attestation verify` (see above), and whether the `attribution`
  setting holds there. (Superseded 2026-10-16: the setting doesn't hold for a cloud write, and with the cloud
  notify-only the write paths are moot; see the last addendum.)

## Addendum (2026-10-13, TASK-243: a cloud run executes none of a PR's dependency code)

The owner limited the Claude GitHub App installation to `uw-share-lab/openproceedings` on 2026-10-13. Its
`workflows`, `contents` and repository-hooks write can't be dropped (the App defines them), and dependency code a
cloud session runs (`make test`, `make lint`, e2e, the smoke test, anything that executes the PR's dependencies)
could use that credential through the session's proxy. The open question above is answered.

**Decision (owner, 2026-10-13): in the cloud the routine runs none of the PR's dependency code.** It keeps
everything that doesn't execute it: `dev`'s checkers from `.claude/scripts/dependabot/` (standard-library Python
calling `git`, `curl`, `npm view` and `gh`; none imports a project dependency), the registry, provenance and
advisory checks, `npm audit --package-lock-only`, the release notes, the reviewers reading diffs, the docs checks,
and `make tooling` and `make mutate-changed`, which run the repo's own scripts (a PR can't change them: `prs.py
check`) with the environment step 0 installs from `dev` before any PR is fetched. For test, lint and e2e evidence
it relies on CI's results for the PR head, which GitHub Actions runs without the App's credential: `prs.py ci <n>
--head <sha>` reads them over REST and requires the latest GitHub Actions run of `lint`, `test`, `claude-tooling`,
`playwright` and `bench` (and `web-image` when the PR touches its paths) to be `success`, waiting up to an hour
while one runs (9 minutes per call, which exits 4 to be called again on the same head). A check run written by another app doesn't count, since the App has `checks` write. A red or
missing check is a hard stop left for the owner, never rerun in the cloud. The routine reads CI before writing the
PR body and again just before `prs.py queue` (superseded 2026-10-16: the cloud reads CI once per PR and reports;
see the last addendum). Locally (a maintainer's machine) nothing changes: the routine runs
`make test` and the rest as before.

What follows from it:
- **No PR dependency is installed in the cloud.** No `uv sync`/`uv run`/`make sync` of the PR's `uv.lock`, no
  `npm ci`, `npm install` or `npm update` of its lock, and so no `npm audit signatures` (it checks an installed
  tree); `npm_lock.py`'s integrity, publisher and provenance checks against the registry stand in, and the PR body
  says signatures weren't checked. An advisory fix that would take `npm update` is left for the owner. The step-5
  waiver for a red test on a stale base (the TASK-242 addendum) is local only, since it runs `make test` on the
  merged tree; in the cloud a red CI `test` is a hard stop.
- **A scripted guard, not only a rule.** In the cloud `prs.py preflight` writes `op-no-dep-code` in the clone's
  git common directory. While it is there, the Makefile's `dep-code-allowed` makes `make sync`, `fmt`, `lint`,
  `test`, `e2e` and `openapi` refuse, `scripts/setup-dev.sh` skips its `uv sync`, and `.githooks/pre-push` skips
  its `make lint` (`uv run --locked` would sync the PR's `uv.lock` and run its ruff and mypy) and still runs
  `make tooling`; CI's `lint` on the pushed head stands in (superseded 2026-10-16: the pre-push hook refuses every
  push while the marker is there; see the last addendum). Locally `preflight` removes a marker it finds. Rows:
  `.claude/scripts/tests/test-no-dep-code.sh` and `dependabot_cases.py`; mutants in `gates.json` and
  `dependabot.json`. The guard lives in the checked-out tree, and a Dependabot PR based on an older `dev` carries
  unguarded copies, so in the cloud `core.hooksPath` points at `dev`'s hooks extracted into the run directory
  (`setup-dev.sh` leaves it alone while the marker is there) and
  `prs.py check` stops a head whose `Makefile`, pre-push hook or `setup-dev.sh` lacks the guard (the routine
  comments `@dependabot rebase`; superseded 2026-10-16: the cloud summary lists it as rebase needed). If `git
  rev-parse` fails, the Makefile's guarded targets and the pre-push hook refuse. Commands typed directly (`uv run`,
  `npm ci`, `npx`, the smoke test) have no guard: the
  procedure, and a verbatim instruction in every cloud reviewer prompt, keep them out.
- **What it doesn't close.** The session still holds the App's credential behind the proxy, and `dev`'s own
  environment still runs in it (`make tooling`'s three pytest tables, the autofix hook's ruff, prettier and
  eslint); that is code already reviewed onto `dev`. A PR's dependencies first run in the cloud session only after
  they are merged, as part of `dev`.
- Options considered: running the tests in the cloud as before, bounded by the shape checks and the narrowed
  installation (rejected: the App's `workflows` and repository-hooks write can't be removed, so a compromised
  dependency could reach them); leaving every cloud PR to the owner (rejected: CI already runs the same suites
  on the head, without that credential).
- What would change this: GitHub letting the App drop `workflows` and repository-hooks write, or a cloud session
  that can run code without the credential reachable (then the cloud may run the tests again).

## Addendum (2026-10-13, TASK-243 AC3 and AC6: what the cloud can check, and what it can't)

A read-only cloud probe ran on 2026-10-13 at 23:25Z (session cse_01Q24cxnP5Nu3yXGC2FKjWqW, Claude Code 2.1.296,
gh 2.89.0) in the routine's environment. `gh auth status` exits 1 ("The token in GH_TOKEN is invalid"), yet `gh api
repos/uw-share-lab/openproceedings` answers 200. `gh api user/installations` and `gh api installation/repositories`
both answer HTTP 403 "This GitHub API path is not available: sessions are bound to their configured repositories. Use
repository-scoped endpoints (repos/{owner}/{repo}/...)". Any other repository (the astral-sh/uv attestations API, for
one) answers HTTP 403 "GitHub access to this repository is not enabled for this session. Use add_repo to request
access…". `gh attestation verify`, `trusted-root` and `download` all fail: the proxy answers Forbidden for
`tuf-repo-cdn.sigstore.dev` and `tuf-repo.github.com`, and another organisation's attestation API is refused as
above, so no offline route exists. So the step 0 installation check this record's earlier addenda describe could
never pass in the cloud, and `docker_digest.py` stops every ghcr.io image there. The exact calls step 0 now makes to
another repository (`repos/astral-sh/uv` and `repos/astral-sh/uv/releases/latest`) were not themselves probed; the
probe's refusal of another of that repository's endpoints says they will be, and a different answer fails closed (a
200 to the binding call stops the run; an answer to the release call is used as locally).

**Decisions (owner, 2026-10-13):**
- **AC6, the credential's reach.** In the cloud, step 0 checks the **session binding** instead of the installation:
  `prs.py preflight` requires `gh api user/installations` to be refused with the "sessions are bound to their
  configured repositories" 403, and `gh api repos/astral-sh/uv` (a stable public repository the session isn't
  bound to) with the "not enabled for this session" 403, each message matched word for word. Any other outcome, a
  200 included, stops the run as before. The reason: the proxy confines the session's credential to this
  repository whatever the installation covers, and since the addendum above the cloud runs none of a PR's
  dependency code anyway. The auth gate is a repository-scoped call (`gh api repos/uw-share-lab/openproceedings`)
  in both modes; `gh api user` is no longer called (the proxy may refuse it). The App installation's repository
  selection (selected, openproceedings only, set by the owner on 2026-10-13) is checked **locally**: `prs.py
  preflight` reads `gh api orgs/uw-share-lab/installations` with the owner's credential, prints the Claude
  installation's `repository_selection` and permissions, and stops on any selection but `selected`, or when no
  `claude` installation is listed (a list whose length isn't its `total_count` is exit 2). The selected repository
  list itself can't be read with a `gh` login (it needs a GitHub App user token).
- **AC3, Sigstore.** In the cloud it can't work, so every ghcr.io PR stays the owner's there, for the reason above;
  `docker_digest.py`'s PROBLEM line now says so when it runs in a cloud session. Locally nothing changes.
- **uv's release.** In the cloud, a refused `repos/astral-sh/uv/releases/latest` call is not a stop: the new `prs.py
  uv-release` prints "check uv's latest release by hand" as an `OWNER` line for the summary. Locally it compares the
  pinned minor with the latest release as the procedure did by hand.

Options considered:
- Keep the installation API check (rejected: the proxy refuses it, so every cloud run would stop at step 0).
- Tell the environment apart by GraphQL alone and skip any reach check in the cloud (rejected: the mode says nothing
  about what the credential reaches; the binding refusals do).
- Add `astral-sh/uv` to the session so the release call answers (rejected: it widens the session for an
  informational check, and it is the repository the binding check relies on being refused).
- Use another `uw-share-lab` repository as the binding check's witness (rejected: `uw-share-lab/.github` doesn't
  exist, and a sibling repository could one day be added to the session; `astral-sh/uv` is public, stable and the
  repository whose refusal the probe saw).
- Make Sigstore work in the cloud (rejected for now: the TUF hosts are blocked at the proxy and there is no offline
  route; the cooldown notice leaves every ghcr.io PR to the owner anyway).

Consequences:
- Rows in `.claude/scripts/tests/dependabot_cases.py`, whose fake `gh` (`dependabot_fake.py`) now fails in cloud mode
  exactly as the probe's proxy did (the same two messages, and `gh attestation verify` failing); mutants in
  `.claude/scripts/mutants/dependabot.json`. Procedure: `.claude/commands/dependabot-review.md` §Where it runs and
  step 0; spec 08 §CI "Dependabot".
- The same binding refuses `actions_pins.py`'s tag lookups (`repos/<owner>/<repo>/git/ref/tags/<tag>`, another
  repository), so in the cloud a github-actions PR with a new pin is the owner's, and the checker's PROBLEM line says
  why (review round 1); the routine never queued those PRs anyway (the owner does).
- Adding `astral-sh/uv` to the routine's repositories would make the second refusal fail and stop every run; that
  is the intended reading (the binding moved), not a fault to work around.
- Not decided here: the GitHub Advisory Database calls (`gh api advisories?…`, step 0's uv query and step 2's
  per-package queries) are a path outside `repos/`, so the proxy may refuse them too; no cloud session has made
  one yet (TASK-247). Until it is decided, the procedure fails closed: a refused step 2 query is a check that
  couldn't run (a hard stop for that PR), and a refused step 0 uv query goes under "for the owner". (Decided
  2026-10-16: the proxy refuses them, and with the cloud notify-only a refused query is reported, not a stop; see
  the last addendum.)
- What would change this: the proxy answering the installation API (then check the installation's repository list
  in the cloud again), or Sigstore's TUF hosts becoming reachable from a session.

## Addendum (2026-10-16, TASK-243 and TASK-247: the cloud routine is notify-only)

The scheduled run on 2026-10-16 (session cse_014uvWwXsnPaQKx5UQf2fD6u, 15:02 to 15:05Z) reviewed PR #142 and left it
for the owner. It showed two things:

- **The footer comes from the cloud session's write path** (TASK-243 AC1). The comment it posted with `gh api -X POST
  repos/uw-share-lab/openproceedings/issues/142/comments -F body=@file` came back with "\n\n---\n_Generated by
  [Claude Code](https://claude.ai/code)_" appended on the server side, which the file didn't have; a cloud `PATCH -F
  body=@file` of the same comment kept it. A `PATCH` from the owner's machine (the local `gh` login) removed it
  (comment 6218376786, about 15:10Z). So neither the routine's text, the attribution hook nor `.claude/settings.json`'s
  `attribution` setting can keep the footer off a write the cloud session makes.
- **The Advisory Database is refused in the cloud** (TASK-247). `gh api
  'advisories?ecosystem=pip&affects=uv&per_page=100'` answered HTTP 403 {"message": "This GitHub API path is not
  available: sessions are bound to their configured repositories", …}, the session binding's refusal of a path
  outside `repos/`, as step 0's check expects.

The cloud's other write paths (the CCR auto-merge `PUT`/`DELETE` and a push), and the job-log download (a read, local
only now), were never exercised from a cloud session (TASK-243 AC2).

**Decision (owner, 2026-10-16): the weekly cloud routine is notify-only.** In cloud mode `/dependabot-review` reviews
each PR as far as a cloud session can (the session binding, `prs.py check`, the supply-chain checkers that answer
there, the release notes, CI's results through `prs.py ci`, the reviewers reading diffs) and reports through its run
summary, which the routine's push notification carries. It makes **no GitHub write**: no comment (a hard stop's or
`@dependabot rebase`), no label, no PR-body edit or attestation, no queueing or auto-merge, no push, no rerun or
cancel of a workflow run, no close or reopen.
Merging is always a local `/dependabot-review` run from a maintainer's clone, which runs the procedure in full,
including the checks the cloud can't (Sigstore, the advisory queries, the tag lookups, the tests) and every write. The
routine itself on claude.ai is unchanged (its prompt stays `/dependabot-review`); the behaviour lives in the committed
procedure.

What follows from it:
- **Scripts refuse what they can.** `prs.py queue` refuses in a cloud session before any call (a PROBLEM, exit 1); its
  CCR route is removed, and locally it runs `gh pr merge --auto --match-head-commit` as before. `record-review.py
  --attest` refuses in a clone holding `prs.py preflight`'s cloud marker (`op-no-dep-code`), and `.githooks/pre-push`
  refuses every push while that marker is there (it used to skip `make lint`). The `gh api` writes the procedure names
  (comments, labels, the body `PATCH`, step 9's close/reopen and run cancel/rerun) have no script of their own; the
  procedure keeps them out of a cloud run.
  `record-review.py --attest --pr` also refuses wherever GraphQL is refused the way a cloud session refuses it, so
  the one attest path a cloud session has is closed even in a clone without the marker. Rows: `dependabot_cases.py`
  (queue), `test-no-dep-code.sh` (pre-push), `test-openproceedings-gates.sh` (record-review); mutants in
  `dependabot.json` and `gates.json`.
- **What the guards don't do.** They stop an honest run's mistakes, not a run something has steered (a prompt in a
  PR's text or release notes, which the procedure treats as data): the session still holds the App's credential,
  with pull-request, contents, checks and workflows write, and could call `gh api` itself (`git push --no-verify`
  skips the hook). Neither the attestation nor the required checks bound that: the App can write the `op-review`
  marker into a body, and `dev`'s six required checks aren't tied to an app (`app_id: null` in the branch
  protection, read 2026-10-16), so a check run the App writes under one of those names would count. Only the
  installation's scope (this repository) bounds a steered run. That is no regression, since the cloud could write
  before. "Notify-only" is the routine's behaviour, not a security property to relax another gate on. Pinning the
  required checks to GitHub Actions would close the check half (the owner's call, in the branch protection).
- **TASK-243 AC2 is moot**: with no cloud write, the CCR route, the job-log download and a cloud push have nothing left
  to confirm. The CCR route is gone from `prs.py`; the fake `gh` still answers it in cloud mode, and a row checks
  `queue` never calls it.
- **TASK-247**: a refused per-package advisory query is listed as "checked only locally" on that PR's line, and
  doesn't keep it from the cloud summary's "ready for a local run" list; a refused step 0 uv query goes under "for
  the owner". The local run that merges a PR makes the queries itself. No hard stop is needed in the cloud, since
  nothing merges there.
- **github-actions PRs**: the reason they aren't queued by the command is no longer the routine's credential (the
  cloud doesn't queue, and a local run holds the maintainer's login): a workflow change runs with the repository's
  secrets once it merges, so the owner queues it by hand after reading it; `prs.py queue` still refuses one.
- **The cloud summary** lists the PRs ready for a local run (with any fix the local run must make), the hard stops with
  their evidence, the PRs not reviewed (a rebase needed, for one) and what is for the owner. A local run's summary is
  unchanged.
- **A local run still reads back every comment and PR body it writes** and removes anything added: cheap, though no
  write from the owner's machine has gained a footer.
- Options considered: keep the cloud writes and strip the footer afterwards (rejected: a cloud `PATCH` keeps it, so it
  can only be removed from a maintainer's machine, which is a local run anyway); comment from the cloud and queue
  locally (rejected: the comment carries the footer); write nothing from the cloud (taken).
- What would change this: a cloud write path that leaves the text as sent, confirmed by a read-back from a cloud run
  (then comments, and perhaps attestation and queueing, could return to the cloud, with TASK-243 AC2's paths exercised
  first).

## Addendum (2026-10-17, TASK-251: the check half is closed on `dev`)

The owner pinned `dev`'s six required checks to GitHub Actions (app_id 15368) on 2026-10-17; decision-027's
addendum of that date has the evidence, the commands and the rollback. A check run the Claude GitHub App writes
under a required name no longer counts on `dev`. `main`'s six required checks were pinned the same way later that
day (TASK-258, same addendum), so such a check run doesn't count on a PR into `main` either. What stays open: the
attestation marker in a PR body, and a workflow pushed to a branch, whose check runs come from GitHub Actions; the
latter is bounded by review, as before.
