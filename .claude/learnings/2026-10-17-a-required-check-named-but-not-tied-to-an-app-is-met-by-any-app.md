# A required check named but not tied to an app is met by any app's check run, and a version CI doesn't name floats past the cooldown

**Key lesson:** Pin a branch's required checks to the app that produces them (`PATCH …/protection/required_status_checks` with `checks: [{context, app_id}]`) only after reading `commits/<sha>/check-runs` and `commits/<sha>/status` on both a queue commit and a PR head, and pin every CI tool version to the one an image already reviews, with a `make tooling` check that fails when they differ, because a name-only check and an unpinned `setup-uv` both accept whatever arrives first.

- **Date:** 2026-10-17 · **Task:** task-251, task-252, task-256 · **Area:** tooling | ops
- **Artifacts:** `backlog/decisions/decision-027 - …` (2026-10-17 addendum), `.claude/scripts/check_uv_pin.py`, `.claude/scripts/tests/test-tooling-scripts.sh` (check_uv_pin rows), `.claude/scripts/mutants/gates.json` (`uvpin:` mutants), `docs/specs/08-ops-and-tooling.md` (§Branch protection, §CI "Dependabot", §Deploy)

## Supersedes
- `2026-10-13-a-check-written-for-the-cloud-must-be-one-the-cloud-can-answer.md` said `dev`'s required checks were
  `app_id: null` and pinning them was the owner's call: since 2026-10-17 they are pinned (TASK-251).
- `2026-10-07-a-routine-runs-only-what-is-scripted-and-a-fake-must-fail-like-the-real-tool.md` said CI's `setup-uv` runs the newest uv: since 2026-10-17
  every step names the api image's uv (TASK-252).

## What we set out to do
Carry out three owner decisions in one PR: tie `dev`'s six required checks to GitHub Actions (TASK-251), pin CI's uv
to the api image's (TASK-252), and record where the per-client proxy cap will live (TASK-256).

## What we learned
- `dev`'s required checks live in one place only. Ruleset 24351281 has a single `merge_queue` rule, and
  `rules/branches/dev` lists only that, so the classic protection's `required_status_checks` was the one thing to
  change (evidence: the saved `rulesets/24351281` JSON; `gh api repos/…/rules/branches/dev`).
- Verify the source before pinning, on both kinds of commit: a queue commit (`dev`'s tip, `a49a7cba`) and a PR head
  (`de03b796`). All six were check runs from `github-actions` (app 15368) and `commits/<sha>/status` held none of
  them. A `claude` check suite sat on both commits with no runs, which is exactly the app the pin shuts out
  (evidence: `gh api …/commits/<sha>/check-runs --jq '.check_runs[] | [.name, .app.id]'`).
- `PATCH …/required_status_checks` with a `checks` array (and `strict`) changes only that object; the rest of the
  protection compared equal field by field before and after. The queue rollback's `-F strict=true` alone keeps the
  pins.
- A rollback to "any app" must send `app_id: -1`, not `null`. GitHub's REST docs for `checks[].app_id`: "Omit this
  field to automatically select the GitHub App that has recently provided this check … Pass -1 to explicitly allow
  any app". A `null` read back from the API means "any app", but sending it may count as omitting it, which would
  pin GitHub Actions again, the very state the rollback undoes (found by the security review; the docs read
  2026-10-17).
- The pin doesn't cover workflows themselves: a workflow's `GITHUB_TOKEN` writes check runs as GitHub Actions, so a
  changed workflow is still bounded by review.
- `setup-uv` with no `version` installs uv's newest release with no 7-day hold. On 2026-10-16 CI ran uv 0.13.1 (two
  days old) while the image pinned 0.13.0 (TASK-252's description). Now every step names the image's release.
- A Dependabot docker PR that moves the uv tag can't carry the matching workflow edits: `prs.py check` allows a
  docker PR only Dockerfiles, and every commit must be Dependabot's. Pairing the two therefore means a hand PR.
  Such a PR now fails `claude-tooling`, and every `ghcr.io` uv PR already stops on the cooldown notice. A digest-only
  bump keeps the tag and passes.

## Dead ends — don't repeat these
- PyYAML exists on the Mac's python3, but no tooling script imports it, and `make tooling` runs on bare `python3`.
  The check reads the workflows by indentation and refuses any form it can't read: a flow-style step, prettier's
  multi-line `{ … }`, anchors, aliases, block scalars and expressions. It never guesses.
- Prettier isn't run on `.github/` (`make lint` runs it in `frontend/` only, and so does autofix). The one-line
  `with: { version: "…" } # …` survives it anyway when run by hand. A future prettier pass that expands it would make
  the check fail loudly, not pass.

## Decisions (and what would change them)
- The required checks are pinned to GitHub Actions → another app's check run of the same name no longer counts →
  reversed by moving a required workflow to another app; the rollback is in decision-027's addendum.
- CI's uv equals the image's uv, enforced in `make tooling` → one reviewed uv under one hold → reversed if the image
  dropped its uv stage (the check then fails: no uv stage).
- The proxy cap will be a per-source connection limit at the host (nftables `connlimit` on 443), with no custom
  Caddy build → set once TASK-064 picks a host → reversed only if the host can't do it.

## Follow-ups
- [ ] none filed by this branch (TASK-256 AC #2 stays open on TASK-064)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/pr-workflow/SKILL.md` (branch protection, the claude-tooling row), `.claude/agents/ci-engineer.md`, `.claude/commands/dependabot-review.md` (step 0, the stop list), spec 08, `deploy/README.md`
- Test or hook added? — `.claude/scripts/check_uv_pin.py` in `make tooling`, with its rows in `test-tooling-scripts.sh` and its `uvpin:` mutants
