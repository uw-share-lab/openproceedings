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
#    no refspec is given, and every local branch for --all / --mirror; `--tags`, glob refspecs and the
#    matching refspec `:` / `+:` are refused outright; in the `--git-dir`/`GIT_DIR=` repo (an `export`ed or
#    `set -a` one too) when one is named. A refspec-less push whose `git -c` settings choose what is pushed
#    (remote.<name>.push or .mirror, push.default, remote.pushDefault, push.followTags), whose repo config
#    does (any remote.<name>.push, a true remote.<name>.mirror or push.followTags, push.default=matching:
#    read with `git config --get-regexp`), or under config this gate can't read (--config-env, -c
#    include.path, GIT_CONFIG_*, GIT_COMMON_DIR, HOME), is blocked. Aliases are expanded, braces and `$'…'`
#    decoded, and abbreviated options written out first (cmdparse); an alias under unreadable config, a git
#    command after a `git config` (or a write into a git config file) that sets an alias/include/push key or an
#    upstream in the same command, or an ambiguous abbreviation, is blocked. So is a push (or `gh pr create`)
#    after any git command in the same call other than one that moves no ref (status, log, diff, show,
#    rev-parse, add, push, config, a fetch without `<src>:<dst>`, …: REF_SAFE_GIT): a commit, checkout, reset,
#    `branch -f`, `fetch . +x:feat` or `worktree add -B` moves what is pushed after this gate read it. A remote
#    or refspec word it can't resolve (`$UNSET`, `$(…)`), or a push after a `cd` it couldn't follow, is blocked.
#    A push inside a command substitution (`x="$(git push …)"`) is checked like any other (TASK-156), and a
#    command with `~` or `$` is checked a second time with HOME/TMPDIR/USER read as '' (`cd ~` then stays put).
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
#    the file itself, so running it names no such path. Globs are expanded first (`cd .git/op-revie*`), and a
#    write is blocked when a `cd` or redirect target this gate can't read (`$…`, a glob) hints at a record
#    (`op-rev…`, `.git`, git-dir), or a word of a writing command does in one of its path components (`tee
#    "$(git rev-parse --git-common-dir)"/op-review?/<sha>`; not a commit message that mentions op-reviews),
#    or a variable is set to a path-shaped part of one (`d=op-reviews`, `d=reviews`; not
#    `f=$SCRATCH/x-reviews.md`). Written words are read with the variables this gate can resolve put in
#    (`d=op-; tee "$G/${d}reviews/x"`), a component mixing an unresolvable `$` with `op-`/`rev` is refused, and
#    the tail of an unquoted `$(…)/op-revie?s/x` counts; `$(git rev-parse --git-common-dir)` is resolved, so a
#    glob after it (`…/op-*`) expands, and an option's attached value (`--output=op-reviews/<sha>`) is a path.
#    Inline message values (-m/--message/--trailer for git commit/merge/tag/notes/revert/cherry-pick/stash,
#    --body/--title/--notes for gh pr/issue/release create/edit/comment/review; never a word starting with `-`)
#    are text, not paths: a commit message may mention `.git/op-reviews/<sha>`.
#
# An unparseable command that mentions a push, gh, or a review record is blocked (fail closed; line
# continuations joined first), and so is a push run by xargs, whose appended refspecs this gate can't see
# (TASK-067). A command this gate can't check at all (an internal error) is blocked: exit 2, never a crash's 1,
# which Claude Code would let through.
#
# Writing/deleting main or dev directly is enforce-pr-workflow.sh's job; this gate adds the review
# requirement on top. Guardrail, not a security boundary (see lib/cmdparse.py). Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# The program goes to Python as an argument and the payload on stdin, never in an environment variable: past
# ARG_MAX (about 1 MB) exec fails with 126, which Claude Code lets through. Any exit but 0 blocks (TASK-156).
IFS= read -r -d '' PROG <<'PY' || true
import glob, os, re, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (ASSIGNMENT, FailClosed, ParseError, expand_known, expand_word, gh_subcommand, git, git_anchored,
                      git_bool, git_config, git_config_opaque, git_dir, git_subcommand, opt_value, opt_values,
                      push_config, push_config_risk, read_payload, tokenize, walk, xargs_hides_args)
from cmdparse import payload as hook_payload

ENTRY_NAME = re.compile(r"^\.claude/learnings/\d{4}-\d{2}-\d{2}-[a-z0-9-]+\.md$")  # same rule as learnings_index.py
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
# `git -c` keys (lower-cased) that decide what a refspec-less `git push` sends and where
PUSH_TARGET_CONFIG = re.compile(r"remote\..+\.push|remote\..+\.mirror|push\.default|remote\.pushdefault|push\.followtags")

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
# A `cd` or redirect target this gate can't read (`$…`, a glob) that hints at a record's directory, and a
# variable set to part of one (TASK-067 review gate: `cd "$(git rev-parse --git-common-dir)"/op-review? && …`,
# `d=op-reviews; printf APPROVE > ".git/$d/abc"`).
UNREAD = re.compile(r"[$`*?\[]")
RECORD_HINT = re.compile(r"op-?rev|\.git\b|git-(common-)?dir|GIT_(COMMON_)?DIR", re.IGNORECASE)
# a value that is part of a record's path: `op-rev…`, or a whole `reviews` path component (`d=reviews;
# .git/op-$d`); only path-shaped values (no spaces or braces) count, so `f=$SCRATCH/x-reviews.md` and a
# GraphQL `query="{ … reviews(first: 5) … }"` stay allowed (TASK-067 review gate round 2)
RECORD_PART = re.compile(r"op-?rev|(^|/)reviews(/|$)", re.IGNORECASE)
# a writing command's word hints at a record only in a path component (after `/` or at its start, no
# whitespace): `"$G"/op-revie?s/x` does, a `-m "$(cat <<'EOF' … the op-reviews gate …)"` message doesn't
RECORD_PATH_HINT = re.compile(r"(^|/)[^/\s]*(op-?rev|\.git\b|git-(common-)?dir|GIT_(COMMON_)?DIR)", re.IGNORECASE)
PATH_SHAPED = re.compile(r"[^\s{}()]*")
# a path component that mixes a `$` this gate can't resolve with a record-name fragment (`${e}reviews`, `op-$x`):
# what it writes can't be told, and it may be a record (review gate round 3)
UNREAD_FRAGMENT = re.compile(r"(^|/)[^/\s]*(\$[^/\s]*(op-|rev)|(op-|rev)[^/\s]*\$)", re.IGNORECASE)
# inline text values (a commit message, a PR body) are text, not paths: `git commit -m "… .git/op-reviews/<sha> …"`;
# only for the commands that take one (TASK-067 final review gate: `git log -m --output=.git/op-reviews/<sha>` read
# its --output as a message)
MESSAGE_OPTS = {"git": ("-m", "--message", "--trailer"), "gh": ("--body", "-b", "--title", "-t", "--notes", "-n")}
MESSAGE_GIT = {"commit", "merge", "tag", "notes", "revert", "cherry-pick", "stash"}
MESSAGE_GH = ({"pr", "issue", "release"}, {"create", "new", "edit", "comment", "review"})
# an option's attached value (`--output=<path>`): a path a written word may name
OPTION_VALUE = re.compile(r"--?[A-Za-z][\w-]*=(.+)", re.DOTALL)
# git commands that move no ref a push sends (a `git config` that steers a push is refused by cmdparse's walk:
# FailClosed): a push after any OTHER git command in the same call may push a ref this gate didn't read (review gate
# round 3: `git commit … && git push origin HEAD`; final review gate: `git branch -f feat other`, `git fetch .
# +other:feat`, `git worktree add … -B feat`). `fetch` counts only without a `<src>:<dst>` refspec or --stdin.
REF_SAFE_GIT = {"status", "log", "diff", "show", "rev-parse", "rev-list", "ls-files", "ls-tree", "ls-remote",
                "describe", "shortlog", "blame", "grep", "cat-file", "merge-base", "for-each-ref", "show-ref",
                "version", "help", "var", "add", "stage", "push", "fetch", "config"}

def moves_refs(g):
    """Can this git command (`git_subcommand`) move a ref that a later push in the same call sends?"""
    sub, args, _ = g
    if sub == "fetch":
        return "--stdin" in args or any(":" in a for a in args if not a.startswith("-"))
    return sub not in REF_SAFE_GIT

def message_values(argv):
    """The indices in `argv` of words that are the inline value of a message option (-m, --message, --trailer for
    git commit/merge/tag/notes/revert/cherry-pick/stash; --body/-b, --title/-t, --notes/-n for gh pr/issue/release
    create/edit/comment/review), attached (`-mx`, `--body=x`, `-qm x`'s next word) or not. A word that starts with
    `-` is never a message here."""
    g, h = git_subcommand(argv, "."), gh_subcommand(argv)
    if not ((g and g[0] in MESSAGE_GIT) or (h and h[0] in MESSAGE_GH[0] and h[1] in MESSAGE_GH[1])):
        return set()
    opts = MESSAGE_OPTS[argv[0]]
    out = set()
    for k, a in enumerate(argv[1:], start=1):
        if a in opts or (argv[0] == "git" and re.fullmatch(r"-[A-Za-z]*m", a)):
            if k + 1 < len(argv) and not argv[k + 1].startswith("-"):  # `-m --output=…` is no message here
                out.add(k + 1)
        elif any(a.startswith(o + "=") for o in opts if o.startswith("--")) or (
                any(a.startswith(o) for o in opts if not o.startswith("--")) and len(a) > 2
                and not a.startswith("--")) or (argv[0] == "git" and re.fullmatch(r"-[A-Za-z]*m.+", a)):
            out.add(k)
    return out

def named_paths(word, dirs):
    """The word, and every path it names with its globs expanded against each directory: the whole word, and
    its directory part (`.git/op-revie*/abc` writes a new file into a globbed directory)."""
    out = [word]
    if any(ch in word for ch in "*?["):
        for d in dirs:
            full = word if os.path.isabs(word) else os.path.join(d, word)
            head, tail = os.path.split(full)
            out += glob.glob(full) + [os.path.join(p, tail) for p in glob.glob(head)]
    return out

def forged_record_block():
    block(["Review gate: review records (<git-common-dir>/op-reviews/) are written only by",
           "  python3 .claude/scripts/record-review.py APPROVE <dispositions.md>",
           "after /review-gate. Don't write, copy, move or delete one by hand or with a file tool."])

def main():
    payload = hook_payload()
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
        walked = list(walk(cmd, cwd))
        # and with HOME/TMPDIR/USER read as '', which the agent's shell may have: `cd ~` then stays put (TASK-156)
        passes = [walked, list(walk(cmd, cwd, env_empty=True))] if "~" in cmd or "$" in cmd else [walked]
    except FailClosed as exc:
        block([f"Review gate: this git command can't be read reliably ({exc}). Write abbreviated options out in",
               "full, and run the git subcommand by its own name rather than an alias set by --config-env,",
               "-c include.path or GIT_CONFIG_*, and run `git config` (or an edit of a git config file) in its",
               "own call; refusing rather than guessing what it pushes."])
    except ParseError:
        # Fail CLOSED (review round 3): a command the parser can't read may still be a push or a PR; the text is
        # searched with its line continuations joined (`gi\<newline>t pu\<newline>sh`: review gate round 3)
        if re.search(r"push|\bgh\b|op-?rev|review", cmd.replace("\\\n", ""), re.IGNORECASE):
            block(["Review gate: this command could not be parsed (unbalanced quotes?) and may push, open a PR or",
                   "touch a review record — refusing rather than letting it through unexamined. Fix the quoting, or",
                   "write the command more plainly, and retry."])
        sys.exit(0)
    commands = [(argv, d) for p in passes for argv, d, _ in p if argv]

    def text_words(argv):
        """The words of `argv` that may name a path: the command word as written, then every argument but an inline
        message (`message_values`)."""
        skip = message_values(argv)
        words = [w for k, w in enumerate(argv[1:], start=1) if k not in skip]
        # an option's attached value is a path too (`--output=op-reviews/<sha>` from inside .git)
        return [argv.head_word or argv[0], *words, *(m.group(1) for w in words if (m := OPTION_VALUE.match(w)))]

    def readings(word, argv, d):
        """`word` as written and with the variables this gate can resolve put in (`d=op-; "$G/${d}reviews"`)."""
        return {word, expand_known(word, argv, d)}

    words = tokenize(cmd)
    dirs = {cwd, *(d for _, d in commands)}
    touched = any(RECORD_WORD.search(p) for argv, d in commands for w in text_words(argv)
                  for x in readings(w, argv, d) for p in named_paths(x, dirs))
    targets = [words[k + 1] for k in range(len(words) - 1) if words[k] in ("cd", "pushd")]
    redirects = [(op, x) for p in passes for argv, d, rs in p for op, t in rs for x in readings(t, argv, d)]
    targets += [t for op, t in redirects if ">" in op]
    touched = touched or any(RECORD_WORD.search(t) for t in targets)
    # and every word of a writing command (`tee "$(git rev-parse --git-common-dir)"/op-revie?s/<sha>`), the command
    # word too: an unquoted `$(…)/op-revie?s/<sha>` is split by the parser, and its tail read as a command
    written = [x for argv, d in commands if argv[0] not in RECORD_READERS
               for w in text_words(argv) for x in readings(w, argv, d)]
    unread = any(UNREAD.search(t) and RECORD_HINT.search(t) for t in targets) or any(
        (UNREAD.search(w) and RECORD_PATH_HINT.search(w)) or UNREAD_FRAGMENT.search(w) for w in written) or any(
        ASSIGNMENT.match(w) and PATH_SHAPED.fullmatch(v := w.partition("=")[2]) and RECORD_PART.search(v) for w in words)
    if touched or unread:
        writes = any(">" in op and not (op.endswith("&") and target.isdigit()) and target != "/dev/null"
                     for op, target in redirects)
        if writes or any(argv[0] not in RECORD_READERS for argv, _ in commands):
            forged_record_block()

    moved = None  # a git command earlier in this call that may move a ref (`moves_refs`)
    # each pass's commands in turn (None starts a pass: what an earlier pass moved doesn't count)
    for argv, d in [x for p in passes for x in [(None, None), *((a, d_) for a, d_, _ in p if a)]]:
        if argv is None:
            moved = None
            continue
        g = git_subcommand(argv, d)
        pushes = (g and g[0] == "push") or ((h := gh_subcommand(argv)) and h[:2] == ("pr", "create"))
        if pushes and moved:
            block([f"Review gate: this call runs `git {moved}` and then pushes or opens a PR: it may move the ref pushed",
                   "after this gate read it. Run the push (or `gh pr create`) in its own call; only read-only git",
                   "commands (status, log, diff, show, rev-parse, fetch, add, …) may come before it."])
        if g and moves_refs(g):
            moved = g[0]
        if pushes and argv.dir_unknown and not git_anchored(argv):
            block(["Review gate: a `cd`/`pushd` before this push or PR went somewhere this gate can't tell, so it",
                   "can't tell which commit is pushed. Run it from the repository, or with `git -C <absolute path>`."])
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
            if "--tags" in flags:
                # every tag, whatever commit it names, and main's merge commits have no record (spec 08 §Release)
                block(["Review gate: `git push --tags` pushes every tag without checking what it points at. Push a tag",
                       "by name (`git push origin <tag>`, its commit needs a record), or let `gh release create` make it."])
            positionals = [expand_word(w, d, argv.shell_vars, argv.olddir) for w in push_positionals(args)]
            if None in positionals:
                block(["Review gate: this `git push` names a remote or refspec this gate can't resolve (a `$…` or",
                       "`$(…)` word), so it can't tell what is pushed. Write the refspec out."])
            refspecs = positionals[1:]
            if any(r.lstrip("+") == ":" for r in refspecs):
                # the matching refspec: every branch that exists on both sides, like --all (TASK-067 review gate)
                block(["Review gate: the refspec `:` pushes every local branch that also exists on the remote,",
                       "unchecked. Push each reviewed branch by name."])
            pushed = [r.lstrip("+").split(":", 1)[0] for r in refspecs if not r.lstrip("+").startswith(":")]
            if any("*" in r for r in refspecs):
                block(["Review gate: a glob refspec (`refs/heads/*:refs/heads/*`) pushes every branch it matches,",
                       "unchecked. Push each reviewed branch by name."])
            if not refspecs:
                # `git -c remote.origin.push=other:other push origin` pushes `other`, not HEAD (TASK-067), and so
                # does the same setting in the repo's config (review gate round 2)
                repo_cfg = push_config(argv, d)
                if (git_config_opaque(argv) or any(PUSH_TARGET_CONFIG.fullmatch(k) for k in git_config(argv))
                        or push_config_risk(repo_cfg) or git_bool(repo_cfg.get("push.followtags", "false"))):
                    block(["Review gate: this `git push` names no refspec, and its config chooses what is pushed",
                           "(remote.<name>.push / .mirror, push.default=matching, push.followTags, a `git -c` push",
                           "setting, or settings this gate can't read: GIT_CONFIG_*, GIT_COMMON_DIR, --config-env,",
                           "include.path). Name the refspec."])
                pushed = ["HEAD"]
            if not pushed and "--follow-tags" in flags:
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

try:
    main()
except Exception as exc:  # a crash exits 1, which Claude Code lets through: block instead (TASK-067 final review gate)
    block([f"Review gate: this command could not be checked ({type(exc).__name__}); refusing rather than letting it",
           "through unexamined. Write it more plainly (no deep nesting, no undecodable characters) and retry."])
PY
python3 -c "$PROG" "$HOOK_DIR"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "Blocked: require-review.sh could not run its check (exit $rc); refusing rather than letting the command through." >&2
fi
[ "$rc" -eq 0 ] || exit 2
