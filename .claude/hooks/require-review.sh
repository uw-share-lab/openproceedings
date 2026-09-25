#!/usr/bin/env bash
# PreToolUse(Bash) review gate: nothing leaves this machine unreviewed, and no PR opens without a lesson.
#
# 1. `git push` of a branch (not a deletion) is blocked unless the commit being pushed has an APPROVE
#    review record at  $(git rev-parse --git-common-dir)/op-reviews/<sha>  — written ONLY by
#    `.claude/scripts/record-review.py` after `/review-gate` ran the reviewers on that exact commit and
#    every finding was dispositioned (fixed / task-NNN / rejected with a reason). A new commit after the
#    review has a new sha, so it needs a new review: the gate cannot be satisfied by an older approval.
# 2. `gh pr create` is blocked unless (1) holds for HEAD AND the branch adds a `.claude/learnings/`
#    entry relative to the PR base (default `dev`). Opt out only for a PR that genuinely taught nothing
#    (e.g. a typo fix) by passing `--label no-learning`; CI (pr-gates.yml) applies the same rule.
#
# Pushes/deletions that touch main/dev are enforce-pr-workflow.sh's job; this gate only adds the review
# requirement on top. Guardrail, not a security boundary (see lib/cmdparse.py). Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import ParseError, gh_subcommand, git, git_subcommand, opt_value, opt_values, read_payload, simple_commands

LEARNING_EXEMPT = {"README.md", "_TEMPLATE.md", "INDEX.md"}

def review_status(directory, sha):
    common = git(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common or not sha:
        return "missing"
    path = os.path.join(common, "op-reviews", sha)
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().strip()
    except OSError:
        return "missing"
    return "approved" if first == "APPROVE" else f"verdict {first or 'empty'}"

def block(lines):
    for line in lines:
        print(line, file=sys.stderr)
    sys.exit(2)

def need_review(directory, sha, what):
    status = review_status(directory, sha)
    if status != "approved":
        block([
            f"Review gate: {what} is blocked — commit {sha[:10] or '?'} has no approved review ({status}).",
            "Run /review-gate on this branch. It spawns the reviewers for the paths you changed, has you",
            "disposition every finding (fixed / task-NNN / rejected: reason), and records the approval with",
            "  python3 .claude/scripts/record-review.py APPROVE <dispositions.md>",
            "Any commit made after the review needs a fresh review — approvals are per-sha by design.",
        ])

cmd, cwd = read_payload()
if not cmd or not re.search(r"\b(git|gh)\b", cmd):
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
except ParseError:
    sys.exit(0)  # enforce-pr-workflow.sh already fails closed on unparseable git commands

for argv, d in commands:
    g = git_subcommand(argv, d)
    if g and g[0] == "push":
        _, args, eff = g
        flags = [a for a in args if a.startswith("-")]
        pos = [a for a in args if not a.startswith("-")]
        refspecs = pos[1:]
        if "--delete" in flags or "-d" in flags or any(r.lstrip("+").startswith(":") for r in refspecs):
            continue  # deleting a remote ref pushes no code
        if "--tags" in flags and not refspecs:
            continue
        sources = [r.lstrip("+").split(":", 1)[0] for r in refspecs] or ["HEAD"]
        for src in sources:
            sha = git(eff, "rev-parse", "--verify", f"{src}^{{commit}}")
            need_review(eff, sha, f"`git push` of {src}")
    h = gh_subcommand(argv)
    if h and h[0] == "pr" and h[1] == "create":
        args = h[2]
        head = opt_value(args, "--head", "-H")
        sha = git(d, "rev-parse", "--verify", f"{head or 'HEAD'}^{{commit}}")
        need_review(d, sha, "`gh pr create`")
        labels = ",".join(opt_values(args, "--label", "-l")).split(",")
        if "no-learning" in [l.strip() for l in labels]:
            continue
        base = opt_value(args, "--base", "-B") or "dev"
        git(d, "fetch", "--quiet", "origin", base)
        added = git(d, "diff", "--name-only", "--diff-filter=A", f"origin/{base}...{head or 'HEAD'}", "--", ".claude/learnings/")
        entries = [p for p in added.splitlines() if os.path.basename(p) not in LEARNING_EXEMPT]
        if not entries:
            block([
                f"Learnings gate: this branch adds no .claude/learnings/ entry relative to origin/{base}.",
                "Run /record-learnings (the learning-recorder agent) so the next session doesn't repeat",
                "this one's dead ends, commit the entry (plus the regenerated INDEX.md), re-run /review-gate,",
                "then open the PR. Only if the change taught nothing at all, add:  --label no-learning",
            ])
sys.exit(0)
PY
