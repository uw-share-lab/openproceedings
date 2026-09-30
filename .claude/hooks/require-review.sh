#!/usr/bin/env bash
# PreToolUse(Bash; Write/Edit/MultiEdit/NotebookEdit for §4) review gate: nothing leaves this machine
# unreviewed, no PR opens without a lesson, and no review record is written by hand.
#
# 1. `git push` of any ref (not a pure deletion) is blocked unless every commit being pushed has an
#    APPROVE review record at  $(git rev-parse --git-common-dir)/op-reviews/<sha>  — written ONLY by
#    `.claude/scripts/record-review.py` after `/review-gate` ran the reviewers on that exact commit and
#    every finding was dispositioned (fixed / task-NNN / rejected with a reason). A new commit after the
#    review has a new sha, so it needs a new review: an older approval can never satisfy the gate.
#    Sources checked: each refspec's source (deletions `:dst` skipped, others still checked), HEAD when
#    no refspec is given, and every local branch for --all / --mirror; in the `--git-dir`/`GIT_DIR=` repo
#    when one is named. A refspec-less push whose `git -c` settings choose what is pushed (remote.<name>.push,
#    push.default, remote.pushDefault) is blocked. Aliases are expanded first (cmdparse).
# 2. `gh pr create` (and its alias `gh pr new`) is blocked unless (1) holds for the PR head AND the branch
#    adds or extends a `.claude/learnings/` entry relative to the PR base (default: the repo default
#    branch, `dev`). Opt out only for a PR that genuinely taught nothing by passing `--label no-learning`;
#    CI (pr-gates.yml) applies the same rule.
# 3. A dev → main promotion PR (`--base main --head dev`) is exempt from both checks, as in CI: its
#    constituent PRs were each reviewed and each carried a learning; main's own gate is a second
#    person's approval.
#
# 4. A review record is never written by hand: a Bash command that names an op-reviews/ path and writes (an
#    output redirect, or any command but a reader such as cat/ls), and a Write/Edit/MultiEdit/NotebookEdit
#    whose path (symlinks followed) is inside op-reviews/, are blocked (TASK-067: `printf 'APPROVE\n' >
#    "$(git rev-parse --git-common-dir)/op-reviews/<sha>"` forged an approval). record-review.py writes
#    the file itself, so running it names no such path.
#
# An unparseable command that looks like a push or a PR is blocked (fail closed), and so is a push run by
# xargs, whose appended refspecs this gate can't see (TASK-067).
#
# Writing/deleting main or dev directly is enforce-pr-workflow.sh's job; this gate adds the review
# requirement on top. Guardrail, not a security boundary (see lib/cmdparse.py). Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import json, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (ParseError, gh_subcommand, git, git_config, git_dir, git_subcommand, opt_value, opt_values,
                      read_payload, redirect_targets, simple_commands, tokenize, xargs_hides_args)

ENTRY_NAME = re.compile(r"^\.claude/learnings/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")  # same rule as learnings_index.py
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
# `git -c` keys (lower-cased) that decide what a refspec-less `git push` sends and where
PUSH_TARGET_CONFIG = re.compile(r"remote\..+\.push|push\.default|remote\.pushdefault")

def review_status(directory, sha):
    common = git(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common or not sha:
        return "missing"
    try:
        with open(os.path.join(common, "op-reviews", sha), encoding="utf-8") as fh:
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

def push_positionals(args):
    """Positional args of `git push`, skipping the values of options that take one."""
    pos, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a in PUSH_VALUE_OPTS:
            skip = True
            continue
        if a.startswith("-"):
            continue
        pos.append(a)
    return pos

def strip_owner(ref):
    return ref.split(":", 1)[1] if ref and ":" in ref else ref

def safe_branch(name, what):
    """A --base/--head value becomes a git argument, so it must be a plain branch name. A value such as
    `--upload-pack=<cmd>` would otherwise be read by `git fetch` as an option and run a command inside this
    hook (security review round 2)."""
    if name is None:
        return None
    ok = (not name.startswith("-")) and git(".", "check-ref-format", "--branch", name) != ""
    if not ok:
        block([f"Review gate: {what} {name!r} is not a valid branch name — refusing to pass it to git."])
    return name

# §4: the records themselves. A word naming an op-reviews/ path (any case: APFS folds it), in a command
# that writes (an output redirect, or any command but a reader), is a forged or deleted record.
RECORD_WORD = re.compile(r"(^|/)op-reviews(/|$)", re.IGNORECASE)
RECORD_READERS = {"cat", "ls", "head", "tail", "less", "more", "grep", "wc", "stat", "file", "test", "["}
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

def forged_record_block():
    block(["Review gate: review records (<git-common-dir>/op-reviews/) are written only by",
           "  python3 .claude/scripts/record-review.py APPROVE <dispositions.md>",
           "after /review-gate. Don't write, copy, move or delete one by hand or with a file tool."])

try:
    payload = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except ValueError:
    payload = {}
if payload.get("tool_name") in FILE_TOOLS:
    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    full = os.path.join(payload.get("cwd") or os.getcwd(), target)
    # the path as written and with symlinks followed (a link into op-reviews/ writes a record too)
    if target and any(RECORD_WORD.search(p) for p in (os.path.normpath(full), os.path.realpath(full))):
        forged_record_block()
    sys.exit(0)

cmd, cwd = read_payload()
if not cmd:  # no raw-text prefilter: `gi\<newline>t push` only becomes `git` after parsing (review round 6)
    sys.exit(0)
try:
    commands = list(simple_commands(cmd, cwd))
except ParseError:
    # Fail CLOSED (review round 3): a command the parser can't read may still be a push or a PR.
    if re.search(r"\bgit\b[^\n]*\bpush\b|\bgh\b[^\n]*\bpr\b|op-reviews", cmd, re.IGNORECASE):
        block(["Review gate: this command could not be parsed (unbalanced quotes?) and appears to push, open",
               "a PR or touch a review record — refusing rather than letting it through unexamined. Fix the",
               "quoting and retry."])
    sys.exit(0)

if any(RECORD_WORD.search(w) for w in tokenize(cmd)):
    writes = any(">" in op and not (op.endswith("&") and target.isdigit()) and target != "/dev/null"
                 for op, target, _ in redirect_targets(cmd, cwd))
    if writes or any(argv and argv[0] not in RECORD_READERS for argv, _ in commands):
        forged_record_block()

for argv, d in commands:
    g = git_subcommand(argv, d)
    if g and g[0] == "push":
        _, args, eff = g
        gd = git_dir(argv, d)  # `git --git-dir=<other>/.git push origin HEAD` pushes the other worktree's HEAD
        repo = ["--git-dir", gd] if gd else []
        if xargs_hides_args(argv, d):
            block(["Review gate: `xargs git push` is blocked — xargs appends refspecs this gate cannot see, so it",
                   "cannot tell which commits are pushed. Name the refspecs on the command line instead."])
        flags = [a for a in args if a.startswith("-")]
        if "--delete" in flags or "-d" in flags:
            continue  # every named ref is deleted; no code is pushed
        if "--all" in flags or "--mirror" in flags or "--branches" in flags:
            heads = git(eff, *repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
            for line in heads.splitlines():
                name, sha = line.rsplit(" ", 1)
                need_review(eff, sha, f"`git push --all` (branch {name})")
            continue
        refspecs = push_positionals(args)[1:]
        pushed = [r.lstrip("+").split(":", 1)[0] for r in refspecs if not r.lstrip("+").startswith(":")]
        if not refspecs:
            if any(PUSH_TARGET_CONFIG.fullmatch(k) for k in git_config(argv)):
                # `git -c remote.origin.push=other:other push origin` pushes `other`, not HEAD (TASK-067)
                block(["Review gate: this `git push` names no refspec, and its `git -c` settings choose what is",
                       "pushed (remote.<name>.push / push.default / remote.pushDefault). Name the refspec instead."])
            pushed = ["HEAD"]
        if not pushed and ("--tags" in flags or "--follow-tags" in flags):
            continue
        for src in pushed:
            sha = git(eff, *repo, "rev-parse", "--verify", "--quiet", f"{src}^{{commit}}")
            need_review(eff, sha, f"`git push` of {src}")
    h = gh_subcommand(argv)
    if h and h[0] == "pr" and h[1] == "create":
        args = h[2]
        raw_head = opt_value(args, "--head", "-H")
        head = safe_branch(strip_owner(raw_head), "--head")
        base = safe_branch(opt_value(args, "--base", "-B"), "--base") or "dev"
        other_repo = any(a in ("-R", "--repo") or a.startswith("--repo=") for a in argv)
        if base == "main" and raw_head == "dev" and not other_repo:
            continue  # promotion of THIS repo's dev (not owner:dev, not --repo other): see header §3
        head_ref = head or "HEAD"
        sha = git(d, "rev-parse", "--verify", "--quiet", f"{head_ref}^{{commit}}")
        need_review(d, sha, "`gh pr create`")
        labels = [l.strip() for v in opt_values(args, "--label", "-l") for l in v.split(",")]
        if "no-learning" in labels:
            continue
        git(d, "fetch", "--quiet", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}")
        # Added, modified or renamed entries count only if they add lines (a chmod-only or delete-only
        # change is not a lesson). --numstat gives "<added>\t<deleted>\t<path>"; renames print "old => new".
        numstat = git(d, "diff", "--numstat", "--find-renames", "--diff-filter=AMR", f"origin/{base}...{head_ref}", "--", ".claude/learnings/")
        entries = []
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].isdigit() and int(parts[0]) > 0:
                path = re.sub(r"\{[^{}]* => ([^{}]*)\}", r"\1", parts[2]).split(" => ")[-1]
                if ENTRY_NAME.match(path):
                    entries.append(path)
        if not entries:
            block([
                f"Learnings gate: this branch neither adds nor extends a .claude/learnings/ entry vs origin/{base}.",
                "Run /record-learnings (the learning-recorder agent) so the next session doesn't repeat this",
                "one's dead ends — it writes a new entry or appends a dated addendum to an existing one. Commit it",
                "(plus the regenerated INDEX.md), re-run /review-gate, then open the PR.",
                "Only if the change taught nothing at all, add:  --label no-learning",
            ])
sys.exit(0)
PY
