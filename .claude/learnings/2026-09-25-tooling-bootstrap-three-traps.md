# A heredoc in a hook eats the payload, free private repos can't be protected, and /code-review is taken

**Key lesson:** In a hook, capture stdin with `input=$(cat)` before any `python3 - <<'PY'`, because the heredoc *is* Python's stdin. Check that GitHub can protect a branch before you design gates around it. Give project commands names that no built-in uses.

- **Date:** 2026-09-25 · **Task:** n/a (M0 tooling bootstrap, branch `chore/claude-tooling`) · **Area:** tooling
- **Artifacts:** `.claude/hooks/lib/cmdparse.py` (`read_payload`), `.claude/hooks/*.sh`,
  `.claude/commands/review-gate.md`, `docs/specs/08-ops-and-tooling.md` §Branch protection

## What we set out to do
Build the `.claude/` roster following the Kreate model, plus review gates, learnings enforcement,
Backlog.md, and branch protection on `dev` and `main`.

## What we learned
- **A `python3 - <<'PY'` heredoc replaces the hook's stdin.** The first draft of `block-ai-attribution.sh`
  called `json.load(sys.stdin)` inside the heredoc script, so it would have read its own source, never the
  tool payload, and allowed everything. Kreate's `enforce-pr-workflow.sh` avoids this with
  `input=$(cat)` + `HOOK_INPUT="$input"`. `cmdparse.read_payload()` now reads `$HOOK_INPUT` first.
  (Evidence: caught while reviewing the code, before the first run. All 39 cases in
  `test-openproceedings-gates.sh` now pass.)
- **GitHub free-plan orgs cannot protect branches on private repos.**
  `gh api repos/uw-share-lab/openproceedings/branches/main/protection` → 403 "Upgrade to GitHub Pro or make
  this repository public". This also applies to rulesets. The local hooks and the CI `pr-gates` job still
  work, but only GitHub can make CI checks *required*.
- **The name `/code-review` is taken** by a built-in skill and a plugin in this environment. A project
  command with the same name risks running the wrong review without anyone noticing. The gate is
  `/review-gate`.
- Kreate's hooks copied over cleanly: 105/105 PR-workflow cases and 28/28 backlog cases passed, once the
  test paths were re-pointed to this repo's layout. The only Kreate-specific parts were paths in the
  backlog test.

## Dead ends — don't repeat these
- Don't write a hook that reads `sys.stdin` inside a heredoc script. The trap is that it *passes* every
  "allow" test, so a test table with no "block" cases would never notice. Every gate's table needs at
  least one case that must block.

## Decisions (and what would change them)
- Approvals are **per-sha**, stored in `.git/op-reviews/` and never committed, and CI checks an
  attestation in the PR body → any new commit needs a new review. What would change it: if re-reviewing
  after trivial commits (for example, the learnings entry itself) turns out to cost too much. In that case,
  scope the re-review to the new commits rather than weakening the per-sha rule.
- One shared `.claude/` rather than Kreate's per-project layers: the parts share one query contract.

## Follow-ups
- [x] Branch protection for `dev` and `main`: resolved the same day by making the repo public (the code
      holds no corpus data; `data/` is never committed). Both branches now need a PR with the six CI checks
      green, with admins included; `main` also needs 1 approval. `dev` is the default branch.

## Propagated to
- Hook pattern → `.claude/hooks/lib/cmdparse.py` docstring, plus the "must-block" cases in
  `.claude/hooks/tests/test-openproceedings-gates.sh`.
- Command name → `.claude/skills/review-gates/SKILL.md`, `docs/specs/08-ops-and-tooling.md` §Commands.
