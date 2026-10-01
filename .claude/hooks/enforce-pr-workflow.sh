#!/usr/bin/env bash
# PreToolUse(Bash) review gate: the PROTECTED branches ('main' and 'dev') are protected — all changes
# land through a pull request. The team flow is feature -> PR -> dev (integration) -> PR -> main (prod).
#
# Blocks, from ANY branch, any git command that would write or delete a remote PROTECTED ref
# ('main'/'dev', or a glob refspec that can name one) or move a local one (`git update-ref`, `branch -f`/
# `-M`/`-C`, `checkout -B`, `switch -C`, `worktree add -B`, or a fetch or pull into it other than
# `fetch origin dev:dev`), and blocks `git commit` (and the other ways to
# make a commit: cherry-pick, revert, am, rebase, commit-tree), `git merge`, `git pull --no-ff`, a
# `git reset` to anything but HEAD or the upstream, and non-deletion `git push` while checked out on a
# protected branch — the branch of the `--git-dir`/`GIT_DIR=` repository when the command names one, and the
# one a `git checkout`/`git switch` earlier in the same command left checked out (`git checkout main && git
# commit`). The matching refspec `:` / `+:` is refused like `--all`.
# Deleting a remote *feature* branch is allowed (it cannot rewrite a protected
# branch's history); read-only plumbing that merely contains "merge"/"push" as a substring (e.g.
# `git merge-base`) is allowed. Everywhere below, "main" in the older prose means "a protected branch".
#
# Sync carve-out (fast-forwarding local main from origin): `git pull` is always allowed, on any
# branch, unconditionally — it fetches + integrates into the LOCAL ref only, never pushes, so it
# cannot change origin/main; and because this gate already blocks `git commit` on main, local main
# can never hold divergent commits, so the integration `pull` performs is always a fast-forward
# (or a no-op). `git merge --ff-only <ref>` while on main is likewise allowed: `--ff-only` makes git
# refuse to create a merge commit — if the merge can't fast-forward, git errors out before anything is
# written. A later `--no-ff`/`--ff` OVERRIDES `--ff-only` and would create a merge commit, so the allow
# also requires that neither is present — `--ff-only` alone is not trusted if `--no-ff`/`--ff` follows.
# A `git merge` on main WITHOUT a clean `--ff-only` remains blocked (it could create a real merge
# commit, i.e. a commit on main) and the block message suggests `--ff-only` for a plain sync. This carve-out
# is scoped to the `pull`/`merge` subcommands only: `--ff-only` appearing on a `git push` (which has
# no such flag) does not and cannot flip a push verdict — push is classified by `push_verdict()`,
# which never inspects `--ff-only`.
#
# The decision reads the command with the shared cmdparse walk and parses each git subcommand and its push
# refspecs — it does not substring-match the raw text — and it recurses into `bash -c "..."`/`sh -lc '...'`
# wrappers (with the assignments before them) and `eval "..."`; `cd`/`pushd`/`popd` are followed as the other
# gates follow them, and every word is resolved (`B=dev; git push origin HEAD:$B`). A commit, merge, reset or
# push whose directory, -C, --git-dir/GIT_DIR, refspec or checked-out branch can't be resolved (a `cd "$X"`,
# a `$UNSET` refspec, a `cd` to a directory that doesn't exist) is refused as "opaque". A checkout/switch
# earlier in the command is read with its redirects apart, `--track <remote>/<b>` checks out <b>, `checkout
# -p` stays put, and repositories are told apart by their absolute git dir (`GIT_DIR=.git git checkout main`).
# Git aliases are expanded first (cmdparse.expand_git_alias), abbreviated long options are
# written out in full (`--al` is --all), `git-<sub>` programs are `git <sub>`, and `export`ed variables reach
# later commands (every assignment while `set -a` is on); braces and `$'…'` are decoded as bash does. A
# refspec-less push whose `git -c` settings choose the destination (remote.<name>.push or .mirror,
# push.default, remote.pushDefault) is refused, and so is one whose repo config does (any remote.<name>.push,
# a true .mirror, push.default=matching, or push.default=upstream to a protected upstream), one or an alias
# under config this gate can't read (--config-env, -c include.path, GIT_CONFIG_*, GIT_COMMON_DIR, HOME), a git
# command after a `git config` that writes an alias, include or push key in the same command, and an
# ambiguous abbreviated option. Exit 2 blocks the call and feeds stderr back to the agent.
#
# Branch/worktree awareness: the "current branch" is resolved against the ACTUAL target of the git
# operation, not a bare `git rev-parse` in the hook subprocess's own ambient CWD. That ambient CWD is
# unreliable — e.g. a subagent's working directory can be pinned to the superproject root while the
# git command it runs actually targets a worktree checked out on a different branch. Resolution
# order per git invocation: an explicit `-C <dir>` on that git call > the working directory tracked
# via a preceding `cd <dir> &&`/`cd <dir>;` in the same command > the tool call's own `cwd` (read
# from the hook's JSON payload) > the hook subprocess's ambient CWD (last-resort fallback, matching
# the old behavior for callers that supply neither).
#
# Anti-evasion (script-file wrappers): `bash -c "git commit ..."` is parsed (git tokens are visible
# in the command string), but `bash script.sh` / `sh script.sh` / `. script.sh` / `source script.sh`
# / `zsh script.sh` invocations hide the git call inside a file this parser cannot read. Running such
# a wrapper is NOT silently allowed: if it happens while the resolved branch is 'main', the gate
# prints a loud warning naming the opaque wrapper (a hidden commit/push/merge to main would not have
# been checked) and asks for the git operation to be run directly. This does not block the call —
# blanket-blocking script execution would break legitimate non-git scripts (build steps, this repo's
# own test suites) that are routinely run via `bash <file>`.
#
# Threat model: this is a GUARDRAIL against honest mistakes (a stray push while on main), not an
# adversarial control. A static parser cannot expand what only the shell knows at runtime, so a git
# command hidden behind `$(...)`, a `$var`, a here-string, a pipe into `bash`, or a script
# file whose contents are never shown to this hook is NOT fully closed off — the opaque-script check
# above only WARNS, it cannot prove the script is safe. A determined actor can still evade a
# command-string parser. Do not mistake this hook for a hard security boundary; it exists to catch
# accidental/automated main-mutations, not to stop someone who deliberately routes around it.
# (A git push/add/commit/rm/mv run by `xargs` is refused outright: the words it appends are unseen.)
# If python3 is unavailable, or the command can't be parsed, the fail-closed fallback below still catches the
# plain-text `git push`/`commit`/`merge` forms (using the same cwd-aware branch resolution, best-effort), and
# refuses any of them in a command with `-C`, `cd`, `pushd`, `--git-dir`/`GIT_DIR` or `--work-tree`, whose
# branch it can't place.
input=$(cat)

# The tool call's own working directory, as reported in the hook's JSON payload — NOT necessarily
# the hook subprocess's ambient $PWD (see header). Falls back to ambient $PWD when absent, which
# preserves prior behavior for any caller (including this test suite) that doesn't supply it.
hook_cwd=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("cwd") or "")
except Exception:
    print("")
' 2>/dev/null)
[ -n "$hook_cwd" ] || hook_cwd="$PWD"
branch=$(git -C "$hook_cwd" rev-parse --abbrev-ref HEAD 2>/dev/null)

verdict=$(HOOK_INPUT="$input" HOOK_CWD="$hook_cwd" HOOK_LIB="$(cd "$(dirname "$0")" && pwd)/lib" python3 <<'PY' 2>/dev/null
import json, os, re, shlex, subprocess, sys

# openproceedings: the command is read by the shared cmdparse walk, as the other gates read it (review gate round
# 3): separators with or without spaces, redirects apart from the words (`git checkout main 2>/dev/null`),
# `cd`/`pushd`/`popd` (a target it can't resolve leaves the directory unknown), `$` words, exports and the
# assignments before `bash -c`, `bash -c`/`eval`, git aliases, and command names by basename (`/usr/bin/git`).
sys.path.insert(0, os.environ.get("HOOK_LIB", ""))
from cmdparse import (Argv, FailClosed, ParseError, base as _base, expand_git_alias, expand_word, git as _git,
                      git_anchored, git_config, git_config_opaque, git_dir, git_subcommand, push_config,
                      push_config_risk, walk, xargs_hides_args)

HOOK_CWD = os.environ.get("HOOK_CWD") or os.getcwd()

try:
    cmd = json.loads(os.environ.get("HOOK_INPUT", "")).get("tool_input", {}).get("command", "")
except Exception:
    cmd = ""

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SOURCE_CMDS = {".", "source"}  # always run a file; no -c-string form exists for these
PROTECTED = {"main", "dev"}    # branches that only a merged PR may write; extend here to add more
# Subcommands that make a commit on the checked-out branch, like `git commit` (TASK-067)
COMMIT_MAKERS = {"commit", "cherry-pick", "revert", "am", "rebase", "commit-tree"}
RESET_MODES = {"--hard", "--soft", "--mixed", "--keep", "--merge"}
# `git -c` keys (lower-cased) that decide what a refspec-less `git push` sends and where
PUSH_TARGET_CONFIG = re.compile(r"remote\..+\.push|remote\..+\.mirror|push\.default|remote\.pushdefault")
# `git fetch`/`git pull` options whose value is the next word (so it is no remote or refspec)
FETCH_VALUE_OPTS = {"--upload-pack", "--depth", "--shallow-since", "--shallow-exclude", "--deepen", "--refmap",
                    "--server-option", "-o", "--negotiation-tip", "--filter", "--jobs", "-j",
                    "--recurse-submodules-default", "--submodule-prefix", "-s", "--strategy", "-X",
                    "--strategy-option"}

_branch_cache = {}
# A word this gate can't resolve (`$UNSET`, `$(…)`) is kept with this mark in front, and a branch it can't tell
# (a `cd` it couldn't follow, a checkout of such a word) is UNKNOWN: either fails closed as "opaque".
UNRESOLVED = "\ue010"  # a private-use character: never in a word bash makes (a NUL can be: `$'dev\0x'` is cut)
UNKNOWN = UNRESOLVED + "unknown"


def get_branch(directory, gitdir=None):
    """Resolve the checked-out branch of `directory` via a real `git -C`, memoized — of the `gitdir`
    repository when the git command names one (`--git-dir`, `GIT_DIR=`; TASK-067). Returns ''
    (never matches a protected branch) if the directory doesn't exist or isn't inside a git worktree — in
    that case the git call being analyzed would itself fail at runtime, so under-blocking here is
    harmless. (HEAD is per worktree, in the git dir: a `GIT_COMMON_DIR=` doesn't change it.)"""
    d = directory or HOOK_CWD
    key = (d, gitdir)
    if key not in _branch_cache:
        try:
            r = subprocess.run(
                ["git", "-C", d, *(["--git-dir", gitdir] if gitdir else []), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            _branch_cache[key] = r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            _branch_cache[key] = ""
    return _branch_cache[key]


def resolve_dir(candidate, base):
    if not candidate:
        return base
    return candidate if os.path.isabs(candidate) else os.path.normpath(os.path.join(base, candidate))


_gitdir_cache = {}


def repo_key(directory, gitdir):
    """The absolute git dir a command in `directory` (with `gitdir`, from --git-dir/GIT_DIR) runs against: one
    key per repository however it is spelled (review gate round 3: `GIT_DIR=.git git checkout main && git commit`
    named the same repo two ways)."""
    key = (directory, gitdir)
    if key not in _gitdir_cache:
        found = _git(directory, *(["--git-dir", gitdir] if gitdir else []), "rev-parse", "--absolute-git-dir")
        _gitdir_cache[key] = os.path.realpath(found) if found else (gitdir or directory)
    return _gitdir_cache[key]


def dest_protected(refspec):
    """True if this push refspec's DESTINATION ref is a protected branch (any branch can name it)."""
    s = refspec.lstrip("+")  # a leading '+' is a force marker, not part of the ref
    dst = s.split(":", 1)[1] if ":" in s else s
    # git reads `refs/heads/dev`, `heads/dev` and `dev` as the same branch (TASK-067: `HEAD:heads/dev`
    # passed); `refs/heads/feature/dev` is another branch. A glob (`refs/heads/*`, `*`) can name either.
    dst = dst.removeprefix("refs/").removeprefix("heads/")
    return dst in PROTECTED or "*" in dst


def push_verdict(args, directory, config, gitdir=None, opaque=False, branch="", repo_config=None):
    """Classify the args following `git push`, using `branch`, the one checked out in `directory` (or
    `gitdir`), the `git -c` settings in `config`, and `repo_config()`, the repo's push config (cmdparse
    `push_config`, read only for a refspec-less push); `opaque`: git also reads config this gate can't."""
    flags = [a for a in args if a.startswith("-")]
    positionals = [a for a in args if not a.startswith("-")]
    refspecs = positionals[1:]  # positionals[0] is the remote
    if any(UNRESOLVED in p for p in positionals):
        return "opaque"  # `git push origin HEAD:$B`, `git push origin $UNSET`: what and where can't be told

    # --mirror/--all can create or delete a protected branch without ever naming it; so can the matching
    # refspec `:` / `+:` (every branch that exists on both sides: TASK-067 review gate round 2).
    if any(f in ("--mirror", "--all") for f in flags) or any(r.lstrip("+") == ":" for r in refspecs):
        return "protected-ref"
    # With no refspec, `-c remote.<name>.push` / `.mirror` / `push.default` / `remote.pushDefault` decide what
    # is pushed where (`git -c remote.origin.push=HEAD:refs/heads/dev push origin`), and so may config this
    # gate can't read (`GIT_CONFIG_*`, `--config-env`, `include.path`, `GIT_COMMON_DIR`): refuse to guess.
    if not refspecs and (opaque or any(PUSH_TARGET_CONFIG.fullmatch(k) for k in config)):
        return "protected-ref"
    # ... and so does the repo's own config (review gate round 2: `git config remote.origin.push
    # HEAD:refs/heads/dev`, then `git push origin`): any remote.<name>.push, a true .mirror,
    # push.default=matching; push.default=upstream sends the branch to its upstream, which may be protected.
    if not refspecs and repo_config is not None:
        cfg = repo_config()
        if push_config_risk(cfg):
            return "protected-ref"
        if cfg.get("push.default", "").strip().lower() in ("upstream", "tracking") and dest_protected(
            _git(directory, *(["--git-dir", gitdir] if gitdir else []), "config", "--get", f"branch.{branch}.merge")
        ):
            return "protected-ref"

    # Any refspec whose destination is protected — update OR delete — is refused from anywhere.
    if any(dest_protected(r) for r in refspecs):
        return "protected-ref"

    flag_delete = any(f in ("--delete", "-d") for f in flags)
    empty_src = any(r.lstrip("+").startswith(":") for r in refspecs)  # ':ref' / '+:ref' = delete
    deletion = flag_delete or empty_src

    if flag_delete and not refspecs:
        return "protected-ref"  # `--delete` with no ref named: refuse to guess
    if deletion:
        return "allow"     # deleting a remote feature ref — cannot touch a protected branch
    if branch in PROTECTED or branch == UNKNOWN:
        return "protected"  # ordinary push while standing on a protected branch (or one this gate can't tell)
    return "allow"


def git_verdict(argv, directory, state=None):
    """`classify`, with a verdict that rests on a branch this gate couldn't tell made "opaque"."""
    tracked = state.setdefault("branches", {}) if state is not None else {}
    v, branch = classify(argv, directory, state, tracked)
    if branch == UNKNOWN and v in ("protected", "protected-merge"):
        return "opaque"
    return v


def classify(argv, directory, state, tracked):
    """Classify one `git …` argv (aliases already expanded), run from `directory`. `state["branches"]` holds
    the branch a `git checkout`/`git switch` earlier in the command left checked out, per repository."""
    # git_subcommand skips git's global options to reach the subcommand, CHAINING every `-C <dir>` the
    # way git itself does (git's own semantics, and this takes priority over any `cd`): multiple `-C`
    # flags compose left-to-right — each relative `-C` is resolved against the directory the
    # PRECEDING `-C` established, an absolute `-C` resets the base. Keeping only the last value
    # and resolving it against the outer dir would mis-resolve `-C a -C ../b` and let a
    # main-worktree target slip through. The chain starts at `state["dir"]` (the `cd`/cwd base).
    g = git_subcommand(argv, directory)
    if g is None:
        return "allow", ""
    sub, args, effective_dir = g
    gitdir = git_dir(argv, directory)
    # `git checkout main && git commit` commits on main: the branch is the one an earlier checkout/switch in
    # this command left, else the repository's own (TASK-067 review gate round 2). Where it runs can't be told
    # after a `cd` this gate couldn't follow (unless git is pointed somewhere absolute), or when -C, --git-dir or
    # GIT_DIR= is a word it can't resolve: UNKNOWN (review gate round 3).
    placed = not (getattr(argv, "dir_unknown", False) and not git_anchored(argv)) and UNRESOLVED not in (
        effective_dir + (gitdir or ""))
    key = repo_key(effective_dir, gitdir)
    if not placed:
        branch = UNKNOWN
    else:
        branch = tracked[key] if key in tracked else get_branch(effective_dir, gitdir)
    on_protected = branch in PROTECTED or branch == UNKNOWN

    if xargs_hides_args(argv, effective_dir):
        return "xargs", branch  # it appends refspecs/paths from stdin that this gate cannot see
    if sub == "push":
        return push_verdict(args, effective_dir, git_config(argv), gitdir, git_config_opaque(argv), branch,
                            lambda: push_config(argv, directory)), branch
    v = other_verdict(sub, args, argv, effective_dir, gitdir, state, tracked, key, branch, on_protected)
    return v, branch


def other_verdict(sub, args, argv, effective_dir, gitdir, state, tracked, repo_key, branch, on_protected):
    """The verdict on a git subcommand other than push (`classify`)."""
    if sub == "update-ref":
        return update_ref_verdict(args, on_protected)
    # A protected local branch moved without update-ref (TASK-067 review gate): `branch -f main`, `-M x main`,
    # `checkout -B main`, `switch -C main`, `worktree add -B main`, `fetch . feature:dev`. From any branch.
    if sub == "branch" and branch_moves_protected(args):
        return "protected-update-ref"
    if (sub == "checkout" and dest_protected(short_value(args, "B") or "")) or (
        sub == "worktree" and args[:1] == ["add"] and dest_protected(short_value(args, "B") or "")
    ):
        return "protected-update-ref"
    if sub == "switch" and dest_protected(short_value(args, "C", "--force-create") or ""):
        return "protected-update-ref"
    if sub in ("checkout", "switch") and state is not None:
        now = switched_to(sub, args, effective_dir, gitdir, state.setdefault("previous", {}).get(repo_key))
        if now is not None:
            state["previous"][repo_key] = branch
            tracked[repo_key] = now
    if sub in ("fetch", "pull") and fetch_moves_protected(args):
        return "protected-update-ref"
    if sub == "pull":
        # sync carve-out: fetch + integrate into LOCAL main only; see header rationale. `--no-ff` makes a
        # merge commit even when a fast-forward is possible.
        return "protected-merge" if on_protected and "--no-ff" in args else "allow"
    if sub == "merge":
        # sync carve-out: a fast-forward-only merge creates no merge commit, so it's allowed on a
        # protected branch. Require --ff-only AND reject --no-ff/--ff — those OVERRIDE --ff-only and
        # would still make a merge commit (a commit on the protected branch). A plain merge is
        # likewise a commit and blocked.
        ff_sync = "--ff-only" in args and not ({"--no-ff", "--ff"} & set(args))
        if on_protected and not ff_sync:
            return "protected-merge"
    elif sub in COMMIT_MAKERS and on_protected:
        return "protected"
    elif sub == "reset" and on_protected and reset_moves_branch(args, branch, effective_dir):
        return "protected"
    return "allow"


SWITCH_VALUE_OPTS = {"-c", "-C", "-b", "-B", "--create", "--force-create", "--orphan", "--conflict"}


def switched_to(sub, args, directory, gitdir, previous):
    """The branch a `git switch`/`git checkout` leaves checked out ('' when it detaches HEAD), or None when it
    changes no branch (`checkout <tree-ish> -- <paths>`, `checkout -p`, a path) or can't be told. `previous`: the
    branch an earlier switch in the command left (`git switch -`). UNKNOWN for a target this gate can't resolve."""
    if "--" in args:
        if sub == "checkout":
            return None  # `checkout [<tree-ish>] -- <paths>` restores files
        args = args[: args.index("--")]
    if sub == "checkout" and any(a in ("-p", "--patch") for a in args):
        return None  # patches files in; HEAD stays (review gate round 3)
    for letter, long_name in (("c", "--create"), ("C", "--force-create")) if sub == "switch" else (("b", None), ("B", None)):
        created = short_value(args, letter, long_name)
        if created:
            return UNKNOWN if UNRESOLVED in created else created.removeprefix("refs/").removeprefix("heads/")
    for k, a in enumerate(args):  # `--orphan <new>`: a new, unborn branch
        if a == "--orphan" and k + 1 < len(args):
            return args[k + 1]
        if a.startswith("--orphan="):
            return a.partition("=")[2]
    if "--detach" in args or (sub == "switch" and any(a.startswith("-") and not a.startswith("--") and "d" in a for a in args)):
        return ""
    positionals, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in SWITCH_VALUE_OPTS:
            skip = True
        elif a == "-" or not a.startswith("-"):
            positionals.append(a)
    if not positionals or (sub == "checkout" and len(positionals) > 1):
        return None  # `git checkout` alone changes nothing; `checkout <tree-ish> <paths>` restores files
    target = positionals[0]
    if UNRESOLVED in target:
        return UNKNOWN
    if any(a in ("-t", "--track") or a.startswith("--track=") for a in args):
        # `--track origin/main` (no -b/-c) makes and checks out `main`: the name less refs/remotes/ and the remote
        # (review gate round 3)
        name = target.removeprefix("refs/").removeprefix("remotes/")
        return name.partition("/")[2] or name
    repo = ["--git-dir", gitdir] if gitdir else []
    if target in ("-", "@{-1}"):
        return previous if previous is not None else (_git(directory, *repo, "rev-parse", "--abbrev-ref", "@{-1}") or None)
    if target in ("HEAD", "@"):
        return None  # stays on the branch
    name = target.removeprefix("refs/").removeprefix("heads/")
    if sub == "switch" or _git(directory, *repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
        return name
    if _git(directory, *repo, "rev-parse", "--verify", "--quiet", f"{target}^{{commit}}"):
        return ""  # a commit: detached HEAD
    if os.path.exists(resolve_dir(target, directory)):
        return None  # a path
    return name  # no such branch here: git creates it from origin/<name>


def update_ref_verdict(args, on_protected):
    """`git update-ref [-m msg] [-d] [--no-deref] <ref> …` writes a ref directly: refuse a protected one, from
    any branch; HEAD while a protected branch is checked out (it moves that branch); or refs read from
    --stdin, which this gate can't see."""
    if "--stdin" in args:
        return "protected-update-ref"
    positionals, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a == "-m":
            skip = True
        elif not a.startswith("-"):
            positionals.append(a)
    if not positionals:
        return "allow"
    ref = positionals[0]
    if dest_protected(ref) or (ref in ("HEAD", "@") and on_protected and "--no-deref" not in args):
        return "protected-update-ref"
    return "allow"


def short_value(args, letter, long_name=None):
    """The value of `-<letter>` (`-B main`, `-Bmain`, `-qB main`) or `--long=v` / `--long v` in `args`, else None."""
    for k, a in enumerate(args):
        if a == "--":
            break
        if long_name and (a == long_name or a.startswith(long_name + "=")):
            return a.partition("=")[2] if "=" in a else (args[k + 1] if k + 1 < len(args) else None)
        if a.startswith("-") and not a.startswith("--") and letter in a[1:]:
            rest = a[a.index(letter, 1) + 1 :]
            return rest or (args[k + 1] if k + 1 < len(args) else None)
    return None


def branch_moves_protected(args):
    """Does this `git branch` point a protected branch at another commit? `-f`/`--force <name> [<start>]`
    resets <name>; `-m`/`-M`/`-c`/`-C`/`--move`/`--copy` write the last name given. (An option's value, such as
    `-u <upstream>`, only counts as a name next to -f/-m/-c, which no real command combines it with.)"""
    force = move = False
    positionals = []
    for a in args:
        if a.startswith("--"):
            name = a.partition("=")[0]
            force = force or name == "--force"
            move = move or name in ("--move", "--copy")
        elif a.startswith("-") and len(a) > 1:
            force = force or any(c in "fMC" for c in a[1:])
            move = move or any(c in "mMcC" for c in a[1:])
        else:
            positionals.append(a)
    if not positionals or not (force or move):
        return False
    return dest_protected(positionals[-1] if move else positionals[0])


def fetch_moves_protected(args):
    """Does this `git fetch`/`git pull` write a protected local branch (`fetch . feature:dev`, `fetch origin
    +x:main`, a `refs/heads/*` glob, or refspecs read from --stdin)? `fetch origin dev:dev` (no force) is a
    sync, like `git pull`."""
    if "--stdin" in args:
        return True
    positionals, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a in FETCH_VALUE_OPTS:
            skip = True
        elif not a.startswith("-"):
            positionals.append(a)
    if not positionals or "--multiple" in args or "--all" in args:
        return False
    forced = "--force" in args or any(a.startswith("-") and not a.startswith("--") and "f" in a for a in args)
    remote = positionals[0]
    for r in positionals[1:]:
        src, colon, dst = r.lstrip("+").partition(":")
        if not colon or not dst or not dest_protected(dst):
            continue
        same = src.removeprefix("refs/").removeprefix("heads/") == dst.removeprefix("refs/").removeprefix("heads/")
        if not (remote == "origin" and same and not r.startswith("+") and not forced and "*" not in dst):
            return True
    return False


def reset_moves_branch(args, branch, directory):
    """True if this `git reset` points the checked-out branch at another commit. Resetting to HEAD (no
    target) or to the branch's own upstream is a sync; `git reset <path>` / `git reset -- <path>` unstages."""
    if "--" in args:
        args = args[: args.index("--")]
    positionals = [a for a in args if not a.startswith("-")]
    if not positionals:
        return False
    target = positionals[0]
    if not RESET_MODES & set(args) and os.path.exists(resolve_dir(target, directory)):
        return False  # a path: unstaging moves nothing
    return target not in {"HEAD", "@", "@{u}", "@{upstream}", f"origin/{branch}", f"{branch}@{{u}}", f"{branch}@{{upstream}}"}


warnings = []  # opaque-script wrappers seen along the way; only surfaced if nothing else blocks


def resolved(argv, directory):
    """`argv` with each word, and each assignment before it, through cmdparse.expand_word (`B=dev; git push origin
    HEAD:$B`); a word it can't resolve is kept with UNRESOLVED in front (review gate round 3)."""
    d = None if argv.dir_unknown else directory

    def one(w):
        r = expand_word(w, d, argv.shell_vars, argv.olddir)
        return UNRESOLVED + w if r is None else r

    out = Argv([argv[0], *(one(w) for w in argv[1:])], argv.via_xargs, {n: one(v) for n, v in argv.assigns.items()})
    out.shell_vars, out.olddir, out.dir_unknown = argv.shell_vars, argv.olddir, argv.dir_unknown
    return out


def git_calls(argv, directory):
    """The git commands `argv` runs: itself (aliases already expanded by the walk), or, for any other command, a
    `git`/`git-<sub>` word inside it read as git from there on (`caffeinate -i git-push …`, behind a wrapper the
    walk doesn't know; `echo git commit` is read as git too: over-blocking a lookalike is the safe side)."""
    if argv[0] == "git":
        return [(argv, directory)]
    for k, w in enumerate(argv[1:], start=1):
        prog = _base(w)
        if prog == "git" or (prog.startswith("git-") and len(prog) > 4):
            inner = Argv(["git", *([prog[4:]] if prog != "git" else []), *argv[k + 1 :]], argv.via_xargs,
                         argv.assigns)
            inner.shell_vars, inner.olddir, inner.dir_unknown = argv.shell_vars, argv.olddir, argv.dir_unknown
            return expand_git_alias(inner, directory)
    return []


def analyze(cmd, cwd):
    """Walk the command (cmdparse.walk); return the first blocking verdict, else 'allow'."""
    state = {}
    try:
        for argv, d, _ in walk(cmd, cwd):
            if not argv:
                continue
            if (_base(argv[0]) in SHELLS or argv[0] in SOURCE_CMDS) and any(not a.startswith("-") for a in argv[1:]):
                # bash/sh/zsh/dash/ksh/./source <file ...> (no -c): an opaque script this parser cannot see
                # inside. Only worth flagging where a hidden commit/push/merge would matter.
                if get_branch(d) in PROTECTED:
                    first = next(a for a in argv[1:] if not a.startswith("-"))
                    warnings.append(f"{argv[0]} {first}")
                continue
            for call, cd_ in git_calls(argv, d):
                v = git_verdict(resolved(call, cd_), cd_, state)
                if v != "allow":
                    return v
    except FailClosed:
        return "unreadable"  # an ambiguous option, an alias set where this gate can't read it, a config write
    except ParseError:
        return "parse-fail"
    return "allow"


if not cmd:
    print("allow")
else:
    result = analyze(cmd, HOOK_CWD)
    if result == "allow" and warnings:
        print("warn:" + "|".join(warnings))
    else:
        print(result)
PY
)

# Fail closed: if python3 is unavailable or the parse failed, fall back to the old conservative
# substring check rather than allowing the command through unexamined. This intentionally
# over-blocks in degraded mode (e.g. `git push origin feature/main-fix`, `git merge-base`) — the
# normal python path allows those; the fallback only runs when the parser cannot.
if [ -z "$verdict" ] || [ "$verdict" = "parse-fail" ]; then
  case "$branch" in main|dev) on_protected=1 ;; *) on_protected=0 ;; esac
  # A `-C`, `cd`, `pushd`/`popd`, `--git-dir`/`GIT_DIR` or `--work-tree` may run git in another worktree, whose
  # branch this text check can't place (review gate round 3: `git -C ../<main> commit -m …` fell through).
  case "$input" in
    *"-C "*|*"cd "*|*pushd*|*popd*|*GIT_DIR*|*--git-dir*|*--work-tree*) elsewhere=1 ;;
    *) elsewhere=0 ;;
  esac
  # Evaluate push FIRST and independently of commit/merge (review round 3: `git commit …; git push origin
  # HEAD:dev` matched the commit arm and was allowed).
  verdict="allow"
  case "$input" in
    *"git push"*)
      case "$input" in
        *" main"*|*":main"*|*"/main"*|*" dev"*|*":dev"*|*"/dev"*) verdict="protected-ref" ;;
        *) [ "$on_protected" = 1 ] && verdict="protected" ;;
      esac ;;
  esac
  if [ "$verdict" = "allow" ]; then
    case "$input" in
      *"git commit"*|*"git merge"*|*"git cherry-pick"*|*"git revert"*|*"git am "*|*"git rebase"*|*"git reset"*)
        [ "$on_protected" = 1 ] && verdict="protected" ;;
    esac
  fi
  if [ "$verdict" = "allow" ] && [ "$elsewhere" = 1 ]; then
    case "$input" in
      *git*commit*|*git*merge*|*git*cherry-pick*|*git*revert*|*git*" am "*|*git*rebase*|*git*reset*|*git*push*)
        verdict="opaque" ;;
    esac
  fi
fi

case "$verdict" in
  protected)
    echo "Review gate: protected branches (main, dev) take no direct commits/pushes/merges. Open a PR:" >&2
    echo "  git switch -c <branch>" >&2
    echo "  git commit ...   then, in its own call:   git push -u origin <branch>" >&2
    echo "  gh pr create --base dev --fill   &&   gh pr merge --squash --delete-branch   # feature -> dev" >&2
    echo "  (promote to prod separately: gh pr create --base main --head dev)" >&2
    echo "Review is not required (you may merge your own PR once checks pass) — but the PR is mandatory." >&2
    echo "(Deleting a remote feature branch is allowed — it cannot rewrite a protected branch's history.)" >&2
    echo "(Syncing a local protected branch with origin is fine: 'git pull' or 'git merge --ff-only <ref>'.)" >&2
    exit 2
    ;;
  protected-merge)
    echo "Review gate: a protected branch (main/dev) is checked out — this merge isn't guaranteed to be a" >&2
    echo "fast-forward, so it could create a merge commit. If you're just syncing with origin, use:" >&2
    echo "  git merge --ff-only <ref>        (or: git pull)" >&2
    echo "For an actual change, open a pull request instead:" >&2
    echo "  git switch -c <branch>" >&2
    echo "  git commit ...   then, in its own call:   git push -u origin <branch>" >&2
    echo "  gh pr create --base dev --fill   &&   gh pr merge --squash --delete-branch" >&2
    exit 2
    ;;
  protected-update-ref)
    echo "Refusing: this command would move or delete a protected branch (main/dev) directly: update-ref," >&2
    echo "branch -f/-M/-C, checkout -B, switch -C, worktree add -B, or a fetch into it (or it reads the refs" >&2
    echo "to write from --stdin, which this gate can't see). Only a merged pull request changes them;" >&2
    echo "to sync a local protected branch use 'git pull' or 'git merge --ff-only <ref>'." >&2
    exit 2
    ;;
  unreadable)
    echo "Refusing: this git command can't be read reliably: an abbreviated option that is ambiguous (write it" >&2
    echo "out in full), a subcommand that may be an alias set where this gate can't read it (--config-env," >&2
    echo "-c include.path, GIT_CONFIG_*, GIT_COMMON_DIR, HOME), or one after a \`git config\` that sets an alias," >&2
    echo "include or push target in the same command. Run the git subcommand itself, by its own name, and" >&2
    echo "run \`git config\` in its own call." >&2
    exit 2
    ;;
  protected-ref)
    echo "Refusing: this command would write or delete a protected remote ref (main/dev) directly." >&2
    echo "Changes reach a protected branch only through a merged pull request (gh pr merge)." >&2
    exit 2
    ;;
  opaque)
    echo "Refusing: this commit, merge, reset or push runs somewhere, or names a ref, this gate can't resolve:" >&2
    echo "a \`cd\`/\`pushd\`/\`git -C\` to a \`\$…\`/\`\$(…)\` path, a directory that doesn't exist, a \`\$VAR\` refspec or" >&2
    echo "branch it can't read, or a command it couldn't parse. Write the path and the refs out plainly (an" >&2
    echo "absolute \`git -C <dir>\` works), or run the \`cd\` in its own call." >&2
    exit 2
    ;;
  xargs)
    echo "Refusing: xargs runs a git push/add/commit/rm/mv here, and the refspecs or paths it appends come from" >&2
    echo "stdin, which this gate cannot see. Run the git command with its arguments written out." >&2
    exit 2
    ;;
  warn:*)
    detail="${verdict#warn:}"
    echo "Review gate warning: this command runs an opaque script wrapper (${detail//|/, }) while on a" >&2
    echo "protected branch (main/dev). This gate cannot see inside a script file — if it contains a git" >&2
    echo "commit/push/merge to a protected branch, it was NOT checked. Prefer running the git command" >&2
    echo "directly (not via a script wrapper) so the gate can see it. Not blocking this call." >&2
    exit 0
    ;;
esac
exit 0
