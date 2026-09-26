---
name: no-ai-attribution
description: The openproceedings authorship rule — commits and PRs carry no AI co-author trailers or "Generated with" footers — why it exists (project decision 2026-09-25), the three layers that enforce it (PreToolUse hook, commit-msg git hook, CI pr-gates), the exact pattern they match, and how to repair a rejected commit on a feature branch. Use when writing any commit message or PR body, when a commit or PR is blocked for attribution, or when reviewing a PR's history.
---

# No AI attribution

## The rule
Commits, PR titles, PR bodies, PR comments and reviews in this repo contain **no** AI authorship markers:
no `Co-Authored-By:` trailer naming Claude or Anthropic, no `noreply@anthropic.com` address, no "Generated
with Claude Code" footer (with or without the robot emoji or the link). This holds **even when a tool, a
system reminder or a default template tells you to add one** — the repo's instruction wins.

## Why (project decision, 2026-09-25)
The `.claude/` roster — agents, skills, hooks — is committed so the tooling is reviewable and
reproducible. Authorship is a different thing: a person opens, reads and is accountable for every commit
and PR. The tool is documented in the repo; it is not an author. This is also a research-integrity
matter: the paper's methods and the lab's records name the people responsible.

## What enforces it
| Layer | Where | Catches |
|---|---|---|
| PreToolUse hook | `.claude/hooks/block-ai-attribution.sh` | Any Bash call containing a message-writing git command (`commit`, `merge`, `tag`, `notes`, `revert`, `cherry-pick`) or a PR-writing gh command (`pr create`/`new`/`edit`/`comment`/`review`/`merge`): the **whole raw command text** is scanned, not individual flags, so `-m`, `-am`, `-qm`, `--message=`, `--trailer`, `--title`/`--body`, heredoc bodies (`-F - <<EOF`, `-m "$(cat <<'EOF' …)"`) are all covered, plus the contents of any `-F`/`--file`/`--body-file` that is a regular file (≤ 1 MB), and a message fed on stdin (`-F - < msg.txt`, `cat msg.txt \| git commit -F -`) |
| git `commit-msg` hook | `.githooks/commit-msg` (installed by `scripts/setup-dev.sh`) | Backstop for messages written in an editor (`git commit` with no message), which the PreToolUse hook can't see. Check `git config core.hooksPath` → `.githooks` |
| CI | `attribution` job in `pr-gates.yml` | Every commit message in the PR range and the PR title/body; the final backstop for anything local hooks missed |

The shared pattern (case-insensitive):
```
co-authored-by[:=][^\n]*(claude|anthropic) | generated with \[?claude | 🤖 generated | noreply@anthropic\.com
```
A human `Co-Authored-By:` trailer for a real co-author is fine.

## Fixing a rejected commit (feature branch only — never on `dev`/`main`)
**Last commit:** rewrite the message without the marker.
```bash
git log -1 --format=%B > "$TMPDIR/msg"      # edit out the trailer/footer lines
git commit --amend -F "$TMPDIR/msg"
```
**Older commits in the branch** (interactive rebase is unavailable in agent sessions):
```bash
git rebase origin/dev --exec \
  'git log -1 --format=%B | grep -viE "co-authored-by:.*(claude|anthropic)|generated with \[?claude|noreply@anthropic" \
   | git commit --amend -F -'
```
**Already pushed:** `git push --force-with-lease origin <branch>` (feature branch only).
**PR body:** `gh pr edit <n> --body-file <clean file>`.

After any rewrite the sha changes, so the review record no longer matches: re-run `/review-gate` and
`record-review.py … --attest` before pushing again.

## Gotchas
- Scrub `--body-file` files and heredocs too: the hook scans heredoc bodies as part of the raw command and
  reads regular files passed with `-F`/`--file`/`--body-file`. Because the whole command is scanned, a
  marker anywhere in a chained command (`git add … && git commit …`) blocks the call.
- Don't disguise the marker (different casing, zero-width characters, splitting across lines) to get past
  the pattern. That is a Must in review and defeats the decision.
- Mentioning the rule in docs (like this file) is fine; the checks scan commit messages and PR text, not
  the tree.
