#!/usr/bin/env bash
# PreToolUse(Write|Edit|MultiEdit|NotebookEdit|Bash) guard for the repo's data/ (specs 01 §Snapshot, 03 §Versioning).
#
# - Snapshots (data/snapshots/) and indexes (data/indexes/) are IMMUTABLE: a search record's
#   reproducibility claim is only as good as the bytes under its index_version. Build a new one
#   (`op snapshot build`, `op index build`); never edit, overwrite, move or delete an existing one.
#   Blocked: editor writes into them; and in Bash, rm/unlink/mv/cp/tee/dd/rsync/truncate/shred/find -delete|
#   -exec|-ok/sed -i/perl -i/ruby -i/awk -i inplace and >/>> redirects that target them, `rsync
#   --remove-s…` (`--remove-source-files`, `--remove-sent-files`) from them — or that target data/, data/snapshots or
#   data/indexes themselves (`rm -rf data` destroys every snapshot), or a directory above them (`rm -rf .`,
#   `rm -rf ../<repo>`, `find . -delete`, `rsync --delete … ./`: anything with a data/snapshots or data/indexes
#   under it, or an ancestor of the repo). Repo paths compare case-blind: APFS folds `Data` into data/.
# - data/ is gitignored and never committed (corpus licensing is unresolved; spec 00). `git add -f` of
#   anything under the repo-root data/ is refused, and so is any forced add that git's own dry run (`git add
#   --dry-run --ignore-missing`, same pathspecs) says would stage data/ or a takedowns/ path (`-fA`, `-f .`,
#   `':/data'`, `'*.jsonl'`); a forced add of the whole tree (no path, a `:` magic pathspec) in a repo with
#   data/, a forced `--pathspec-from-file`, and a forced add git won't dry-run are refused outright. `git add`
#   (forced or not) of any path with a `takedowns` directory in it is refused wherever it sits: the takedown
#   list and log (TASK-136, decision-022) live in a data directory, and the log holds requesters' details.
#   `git update-index --add` (it ignores .gitignore) of those paths, `--add --stdin` and `--index-info` too.
#   The dry run runs with core.fsmonitor, core.hooksPath and the untracked cache off: the repo it reads may be
#   one the command names, and its config must not start a program inside this hook. Abbreviated options
#   (`--forc`, `stash --al`) are read as git reads them (cmdparse); an ambiguous one, or a git alias under
#   config the parser can't read (--config-env, include.path, GIT_CONFIG_*), is refused.
# - backlog/ is CLI-managed (task-hygiene skill): only the `backlog` CLI moves a task (e.g. `backlog task
#   complete` into backlog/completed/). Bash mv / git mv / cp / rm / unlink / tee / dd of= / redirects that target
#   files under backlog/, and sed -i / perl -i / ruby -i / awk -i inplace edits of them (decision bodies excepted, as in
#   enforce-backlog-cli.sh), are refused here; enforce-backlog-cli.sh covers editor writes. So are touch/sponge there,
#   a cp -R/rsync/ditto whose copy lands there (dest/<name>, or each entry of a `src/`), patch(1) (not --dry-run),
#   tar -x/unzip into backlog/, a worktree root or above, find -fprint/-fls into it, and a find that deletes or runs
#   anything but a reader (`-exec grep`; `rg --pre` is no reader) from backlog/, a worktree root or above (BSD
#   `find -f <path>` starts too). And every git command that writes backlog/ files in the worktree or the index by
#   pathspec (TASK-244: PR #146 put a completed task back with `git restore`): restore (not `--staged` alone:
#   unstaging), checkout [<commit>] --, reset <commit> -- (a tree that isn't HEAD's; a word that is no commit and no
#   path is a tree-ish), `-p` with no path (the whole tree), rm, mv (not -n), clean (not -n; `-e backlog` keeps it
#   unless a `!` pattern follows), stash push --, apply and am (paths from `git apply --numstat`, both sides of each
#   rename, C-unquoted; in a call of their own), merge-file (its first file), checkout-index, update-index (not
#   flag-only forms), read-tree --prefix or -u; the same pathspecs into data/snapshots or data/indexes. A pathspec
#   reaches backlog/ when it is in it, is the worktree root, is a git glob from either (`'*.md'`: git's `*` crosses
#   `/`) or `:` magic, unless an exclude names backlog itself (`':!backlog'`, case-exact as git reads it; never under
#   literal pathspecs); --pathspec-from-file, stdin, an unresolvable pathspec, -C, work tree or path-valued option
#   (`--prefix=$P`), and a built pathspec after a `cd` it couldn't follow are refused in a repo with backlog/. A
#   command git runs from its own words (every `-c` value, GIT_PAGER/PAGER/GIT_EDITOR/…, rebase --exec, bisect run,
#   submodule foreach, grep -O<cmd>, difftool -x, filter-branch filters, a `git config <key> <value>` value) is
#   checked as a command, up to four levels. Allowed: branch and commit operations (checkout/switch a branch, rebase,
#   merge, cherry-pick, reset without paths, `git stash` without a path), reads, dry runs, and settling a path every
#   match of which is in conflict (`checkout --theirs`, `restore --ours`, `rm`; not when git is pointed at another
#   repository), since an editor write there is refused.
# - A payload this hook can't read (not a JSON object, a tool it isn't wired to, no command or file path) is refused.
# - Known limitation: this is a best-effort guard against agent mistakes, not a security boundary. Obfuscated commands
#   may bypass it (`git${IFS}rm`, a config or hook script written in an earlier call, git behind a wrapper cmdparse
#   doesn't strip); the backstop is git history plus review (TASK-244).
# - `git clean -x/-X` (unless a dry run, `-e data`, or pathspecs outside data/) and `git stash push|save --all`
#   (`-a` in any short cluster: `-qa`, `-ua`) are refused: they remove gitignored files, which is all of data/.
# - Every path word is resolved first (cmdparse.expand_word): `~`, `~+`, `~-`, `$PWD`, `$(pwd)`, `$(git rev-parse
#   --show-toplevel|--git-common-dir|--git-dir)`, `$(mktemp [-d] [-t p])` (a path in the temp dir; unknown when the
#   command sets or unsets TMPDIR), a `for v in …` loop's `$v` (each of its words; unknown when the body can
#   exit early), `$HOME`, and variables set (or `unset`: empty) earlier in the command, else
#   HOME, TMPDIR or USER from this hook's environment (unset there: ''; `~` with HOME unset is the passwd
#   home, as in bash, and unknown after `unset HOME`), each checked both as set and as '' (`rm -f "$TMPDIR/x"` is
#   allowed, `rm -rf "${TMPDIR}data"` is not; read as '', `"$TMPDIR"/*` is not globbed as `/*`); `cd`/`pushd`/
#   `popd` are followed, and a command with `~` or `$` is read both ways (`cd ~` with HOME '' stays put:
#   TASK-156). A `git log`/`diff`/`format-patch` `--output <file>` is a write like a redirect, and so is each
#   patch `git format-patch` writes into `-o`/`--output-directory`, format.outputDirectory or the directory it
#   runs in (TASK-156). A command substitution's body (`x="$(rm -rf …)"`, backquotes) is checked like any
#   command (cmdparse). A path that decides a check and can't be
#   resolved (an unset variable, a relative path after a `cd` that couldn't be followed or went to a directory
#   that doesn't exist, a redirect target such as `"$(echo data)/…"`) is refused where data/ is: in this worktree,
#   the call's own, or their repository's MAIN worktree (a linked worktree has none of its own). Each target is
#   judged against the worktree that contains it, case-blind, not the one the command runs in (`rm -rf
#   ../<main>/data/snapshots`, or `../<MAIN>/data`, from a worktree).
# - xargs appends words this guard can't see: rm/unlink/mv/cp/…, sed -i/perl -i and git add and the backlog git writers above
#   run through xargs are refused in a repo with data/ or backlog/ (cmdparse's `Argv.via_xargs`).
# Globs are expanded against the filesystem (`rm -rf data*`, `*`, `../*`), braces and `$'…'` decoded as bash
# does (`rm -rf data{,}`, cmdparse); rsync's long options are read by unique prefix (`--rem`, `--del`), as
# macOS's openrsync reads them. Any command this guard can't parse is refused (fail closed) where the main
# worktree has data/ or the repo has backlog/, and so is any command this guard can't check at all (an internal
# error exits 2, never 1: Claude Code lets a crash through). Paths are resolved against the repo root, so
# frontend/src/data/… is unaffected. Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
# The program goes to Python as an argument and the payload on stdin, never in an environment variable: past
# ARG_MAX (about 1 MB) exec fails with 126, which Claude Code lets through. Any exit but 0 blocks (TASK-156).
IFS= read -r -d '' PROG <<'PY' || true
import functools, glob, os, re, shlex, subprocess, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (GIT_VALUE_OPTS, Argv, FailClosed, ParseError, expand_word, git, git_config, git_config_opaque,
                      git_dir, git_subcommand, read_payload, repo_root, walk)
from cmdparse import payload as hook_payload

payload = hook_payload()
tool = payload.get("tool_name", "")
ti = payload.get("tool_input") or {}
cwd = payload.get("cwd") or os.getcwd()

# Paths read literally, never globbed: in the second pass (HOME/TMPDIR/USER read as ''), a word that starts with one
# of them (`"$TMPDIR"/*` is `/*`) is not expanded against the root (TASK-067 final review gate: it refused `rm -rf
# "$TMPDIR"/*` everywhere; the first pass reads the variable as set)
NO_GLOB = set()
ENV_LEAD = re.compile(r"\$(?:\{(HOME|TMPDIR|USER)\}|(HOME|TMPDIR|USER)\b)")

def expand(path, base):
    """Every path a shell word can name: a glob is expanded against the real filesystem, so `data*`,
    `dat?`, `*` and `../*` are judged by what they match (review round 3). A glob that matches nothing
    deletes nothing, so its literal text is checked only as a path."""
    if path in NO_GLOB or not any(ch in path for ch in "*?["):
        return [path]
    full = path if os.path.isabs(path) else os.path.join(base, path)
    return [*glob.glob(full), path]

@functools.lru_cache(maxsize=256)
def toplevel(directory):
    """The top of the git worktree holding `directory` (or its nearest existing ancestor), or None outside one."""
    d = directory
    while not os.path.isdir(d) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    top = git(d, "rev-parse", "--show-toplevel")
    return os.path.realpath(top) if top else None

@functools.lru_cache(maxsize=64)
def main_worktree(directory):
    """The main worktree of the repository holding `directory` (the parent of its common git dir), or None. A
    linked worktree has no data/ of its own; the main one has (review gate round 3)."""
    common = git(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.dirname(os.path.realpath(common)) if common else None

def data_in(directory):
    """Is there a data/ in the worktree holding `directory`, or in its repository's main worktree?"""
    return any(r and os.path.isdir(os.path.join(r, "data")) for r in (repo_root(directory), main_worktree(directory)))

def rel(path, base):
    """Path relative to the root of the worktree that CONTAINS it (not the one the command runs in: review gate
    round 3, `rm -rf ../<main>/data/snapshots` from a worktree), with forward slashes; None outside any."""
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    root = toplevel(os.path.dirname(full) if not os.path.isdir(full) else full)
    if root is None:
        return None
    # compared case-blind: APFS folds case, so `../PRIM/data` from a sibling worktree is the main worktree's data/,
    # while git prints the root as it is on disk (TASK-067 final review gate)
    if full.lower() == root.lower():
        return "."
    if not full.lower().startswith(root.lower().rstrip("/") + "/"):
        return None
    return full[len(root.rstrip("/")) + 1 :].replace("\\", "/")

def any_rel(pred, path, base):
    return any(pred(rel(p, base)) for p in expand(path, base))

def resolve(word, argv, d):
    """The path a shell word names (cmdparse.expand_word: `~`, `~+`, `~-`, `$PWD`, `$(pwd)`, `$HOME`, variables
    set earlier in the command or in this hook's environment), or None when it can't be told: a variable this
    hook can't see, or a relative path after a `cd`/`pushd`/`popd` it couldn't follow (TASK-067 review gate)."""
    unknown = getattr(argv, "dir_unknown", False)
    r = expand_word(word, None if unknown else d, getattr(argv, "shell_vars", {}), getattr(argv, "olddir", None),
                    env_empty=getattr(argv, "env_empty", False))
    return None if r is None or (unknown and not os.path.isabs(r)) else r

# the heavy trees a forced `git add <dir>` walk never enters (none holds a takedowns/ directory of ours)
WALK_SKIP = {".git", "node_modules", ".venv", ".next", "cache", "snapshots", "indexes", "records", "embeddings"}

def holds_takedowns(directory):
    """Is there a `takedowns` directory (any case) anywhere under `directory`? The heavy trees are skipped."""
    for _root, dirs, _files in os.walk(directory):
        if any(d.lower() == "takedowns" for d in dirs):
            return True
        dirs[:] = [d for d in dirs if d not in WALK_SKIP]
    return False

def through_takedowns(path, base, forced):
    """Would `git add [-f] path` reach a takedowns/ directory? Any path component named `takedowns` (any
    case: APFS folds it), a glob that matches one, and, for a forced add of a directory (`.` included), a
    `takedowns` directory anywhere under it (git -f stages ignored files too)."""
    for p in expand(path, base) if forced else [path]:  # unforced, git leaves ignored files out of a glob
        full = os.path.normpath(p if os.path.isabs(p) else os.path.join(base, p))
        parts = [c.lower() for c in full.split(os.sep)]
        if "takedowns" in parts:
            return True
        if forced and os.path.isdir(full) and holds_takedowns(full):
            return True
    # forced, a glob (`takedown[s]`, `*.jsonl`: git's `*` crosses `/`) is walked from its fixed prefix; unforced,
    # git itself leaves ignored files out, so `git add 'src/*'` stays allowed
    if forced and any(ch in path for ch in "*?["):
        fixed = path.split("*")[0].split("?")[0].split("[")[0]
        start = os.path.dirname(os.path.join(base, fixed)) or base
        if os.path.isdir(start) and holds_takedowns(start):
            return True
    return False

def whole_tree(args):
    """A forced `git add` that may stage the whole work tree: no path argument (`-f`, `-fA`) or a `:` magic
    pathspec (`:/`). A forced `--pathspec-from-file` is refused before this is asked."""
    paths = [x for x in args if not x.startswith("-")]
    return not paths or any(x.startswith(":") for x in paths)

# Repo-relative paths are compared lower-cased: APFS folds case, so `Data/Snapshots` IS data/snapshots
# (TASK-067 security review).
def inside_immutable(r):
    return r is not None and (r.lower().startswith("data/snapshots/") or r.lower().startswith("data/indexes/"))

def is_or_contains_immutable(r):
    return r is not None and (inside_immutable(r) or r.lower() in ("data", "data/snapshots", "data/indexes"))

def in_backlog(r):
    return r is not None and (r.lower() == "backlog" or r.lower().startswith("backlog/"))

def in_decisions(r):
    """A decision file: its body is edited by hand (the CLI can't write it; enforce-backlog-cli.sh)."""
    return r is not None and r.lower().startswith("backlog/decisions/")

def is_data(r):
    return r is not None and (r.lower() == "data" or r.lower().startswith("data/"))

def has_takedowns(path):
    return "takedowns" in path.lower().replace("\\", "/").split("/")

def holds_immutable(full):
    """Is there a data/snapshots or data/indexes on disk under the directory `full`?"""
    return any(os.path.isdir(os.path.join(full, "data", t)) for t in ("snapshots", "indexes"))

def covers_immutable(path, base):
    """Would deleting or moving `path` take a snapshot or index with it? It is, or is inside, data/,
    data/snapshots or data/indexes; or it is a directory ABOVE them: one with a data/snapshots or data/indexes
    under it (`rm -rf .`, `rm -rf ../<repo>`, `find . -delete`), or an ancestor of this repo, which has one.
    A worktree has no data/, so removing a worktree stays allowed; a directory above the main worktree is not.
    """
    roots = {os.path.realpath(r) for r in (repo_root(base), main_worktree(base)) if r}
    for p in expand(path, base):
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))
        if is_or_contains_immutable(rel(p, base)) or holds_immutable(full):
            return True
        if any(os.path.commonpath([full, root]) == full and holds_immutable(root) for root in roots):
            return True
    return False

# git's global options a dry run keeps: never `-c`/`--config-env` (a value can name a program git runs, e.g.
# core.fsmonitor, and the hook must not run it) nor `--exec-path`; -C becomes the dry run's working dir
DRY_RUN_DROP = {"-C", "-c", "--config-env", "--exec-path"}
DRY_RUN_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
               "GIT_ICASE_PATHSPECS")

def dry_run_add(argv, sub_args, directory):
    """The paths a forced `git add` would stage, repo-root relative, as git itself answers (`git add --dry-run
    --ignore-missing`): pathspec magic (`:/data`, `:(glob)`), git's own globs (`*.jsonl`, `d*`, whose `*`
    crosses `/`) and case folding are all git's to resolve. None when git refuses the dry run (fail closed)."""
    j = len(argv) - len(sub_args) - 1  # index of the subcommand
    keep, k = [], 1
    while k < j:
        opt = argv[k].partition("=")[0] if argv[k].startswith("--") else argv[k]
        takes = opt in GIT_VALUE_OPTS and "=" not in argv[k]
        if opt not in DRY_RUN_DROP:
            keep += argv[k : k + (2 if takes else 1)]
        k += 2 if takes else 1
    env = {**os.environ, **{n: v for n, v in getattr(argv, "assigns", {}).items() if n in DRY_RUN_ENV}}
    # `add` refreshes the index, which starts the repo's core.fsmonitor program (the repo may be one the command
    # names: --git-dir, GIT_DIR): never run it, nor a hook or the untracked cache, inside this hook
    safe = ["-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.untrackedCache=false"]
    try:
        r = subprocess.run(["git", *keep, *safe, "-c", "core.quotepath=false", "add", "--dry-run", "--ignore-missing",
                            *sub_args], cwd=directory, env=env, capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return [line[5:-1] for line in r.stdout.splitlines() if line.startswith("add '") and line.endswith("'")]

# primaries a leading `-f…` word may be rather than BSD's `-f <path>` (macOS find reads `-fprint` as -f print, GNU as
# the primary; both are checked as primaries)
FIND_F_PRIMARIES = {"-fprint", "-fprint0", "-fprintf", "-fls", "-follow", "-fstype", "-false"}

def find_starts(args):
    """find's start paths: the words before its first expression token, after -H/-L/-P and BSD's flags, plus each
    BSD `-f <path>` (TASK-244 security review: `find -f ../data/snapshots -delete`); none means `.`."""
    k, starts = 0, []
    while k < len(args) and re.fullmatch(r"-[HLPEXdsx]*(f.*)?", args[k]) and args[k] not in FIND_F_PRIMARIES:
        flag = re.fullmatch(r"-[HLPEXdsx]*(?:f(.*))?", args[k])
        if flag and flag.group(1) is not None:  # BSD `-f <path>` (attached: `-f../backlog`)
            if flag.group(1):
                starts.append(flag.group(1))
            elif k + 1 < len(args):
                starts.append(args[k + 1]); k += 1
        k += 1
    while k < len(args) and not args[k].startswith("-") and args[k] not in ("(", "!", ")"):
        starts.append(args[k]); k += 1
    return starts or ["."]

def perl_in_place(args, valued="MmIxdDCFl0"):
    """perl -i / -pi / -i.bak (and ruby's, whose switches with a value are `valued="0EFICrxWKT"`): `i` in a
    switch cluster, before a switch whose value is the rest of the cluster (`-Mstrict` is -M strict, not -i)."""
    k = 0
    while k < len(args) and args[k].startswith("-") and args[k] != "--":
        for c in args[k][1:]:
            if c == "i":
                return True
            if c in valued:
                break
            if c in "eE":  # the program is the next word
                k += 1
                break
        k += 1
    return False

BACKLOG_EDIT_MSG = ("Blocked: backlog/ files are CLI-managed — don't edit them in place with sed/perl/ruby/awk. "
                    "Use `backlog task edit <id>` (decision bodies are the exception and may be edited).")
DATA_MSG = "Blocked: data/ is never committed (corpus licensing unresolved; spec 00). Don't force-add it."
TAKEDOWNS_MSG = ("Blocked: a takedowns/ directory holds the takedown list and the operator's log, with "
                 "requesters' details (TASK-136); it is never committed.")

BACKLOG_MSG = ("Blocked: backlog/ files are CLI-managed — don't move, copy or delete them from the shell. "
               "Use the backlog CLI (e.g. `backlog task complete <id>` moves a Done task to backlog/completed/).")

# rsync (and macOS's openrsync, which takes any unique prefix of a long option: `--rem`) deleting files
def rsync_removes_sources(a):
    opt = a.partition("=")[0]
    return len(opt) >= 5 and any(n.startswith(opt) for n in ("--remove-source-files", "--remove-sent-files"))

def rsync_deletes(a):
    opt = a.partition("=")[0]
    return opt.startswith("--delete") or (len(opt) >= 5 and "--delete".startswith(opt))

def refuse(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)

BACKLOG_GIT_MSG = (
    "Blocked: backlog/ files are CLI-managed — git doesn't put them back, move or remove them by pathspec "
    "(`git restore`, `git checkout <commit> -- <path>`, `git reset <commit> -- <path>`, `git rm`, `git mv`, `git clean`, "
    "`git stash push -- <path>`, `git apply`, `git am`, `git merge-file`, `git checkout-index`, `git update-index`, "
    "`git read-tree --prefix`), "
    "and a pathspec of the whole tree (`.`, `'*.md'`, `:/…`) reaches backlog/ too: name the paths you mean, or add "
    "`':!backlog'`. Branch and commit operations (checkout/switch a branch, rebase, merge, reset to a commit) and "
    "unstaging (`git restore --staged <path>`) are fine; commit what the CLI wrote right away. Backlog 1.53 can't edit "
    "a completed task, so run `backlog task complete` only after the last review round (task-hygiene skill).")

def backlog_spec(spec, base):
    """What a git pathspec does to backlog/, judged from `base` (the directory git resolves it in): "exclude-backlog"
    for an exclude naming backlog/ itself (`:!backlog`, `:^backlog/`, `:(exclude)backlog`), "exclude" for any other
    exclude (it adds no file), True when it may name a file under backlog/, else False. It may when it is in backlog/
    or is the worktree's root (or above it, from a subdirectory), and so may a git glob (`*` crosses `/`) whose
    fixed directory is either, and any other `:` magic pathspec (`:/`, `:(top,icase)`), which this guard doesn't
    read: the root and magic count only where the repository has a backlog/. Paths compare case-blind (APFS), but
    an exclude only as git matches it, case and all (`:!Backlog` takes nothing out of backlog/)."""
    if spec.startswith(":"):
        m = re.fullmatch(r":(?:[!^]|\(exclude\))(.*)", spec)
        if m is None:
            return backlog_repo([base])
        if m.group(1) and rel(m.group(1), base) == "backlog":  # `backlog/` too: rel resolves the path
            return "exclude-backlog"
        return "exclude"
    if any(c in spec for c in "*?["):
        fixed = re.split(r"[*?\[]", spec, maxsplit=1)[0]
        spec = fixed.rpartition("/")[0] or "."
    r = rel(spec, base)
    return in_backlog(r) or (r == "." and backlog_repo([base]))

def specs_reach_backlog(specs, bases, literal=False):
    """Do these pathspecs, read from any of `bases`, name a file under backlog/? Only excludes means `.` plus
    them, as git reads it; an exclude of backlog/ itself takes it out whatever else is named. Under literal
    pathspecs (`--literal-pathspecs`, GIT_LITERAL_PATHSPECS) a `:` word is a plain path, never an exclude."""
    for base in bases:
        kinds = [(in_backlog(rel(s, base)) if literal and s.startswith(":") else backlog_spec(s, base)) for s in specs]
        if "exclude-backlog" in kinds:
            continue
        positive = [k for k in kinds if k not in ("exclude", "exclude-backlog")]
        if (specs and not positive and backlog_spec(".", base)) or any(k is True for k in positive):
            return True
    return False

def git_words(args, valued_long=(), valued_short=""):
    """A git subcommand's arguments read as parse-options reads them (long options already written out in full
    by cmdparse): (the options in order as (name, value) pairs, a short option as its letter, the non-option words
    before `--`, the words after `--` or None). An option in `valued_long` / a letter in `valued_short` takes the
    next word (or the rest of its short cluster) as its value."""
    opts, words, k = [], [], 0
    while k < len(args):
        a = args[k]
        if a == "--":
            return opts, words, args[k + 1 :]
        if a.startswith("--"):
            name, eq, value = a[2:].partition("=")
            if name in valued_long and not eq and k + 1 < len(args):
                value, k = args[k + 1], k + 1
            opts.append((name, value))
        elif a.startswith("-") and len(a) > 1:
            for i, c in enumerate(a[1:], 1):
                if c in valued_short:
                    value = a[i + 1 :]
                    if not value and k + 1 < len(args):
                        value, k = args[k + 1], k + 1
                    opts.append((c, value))
                    break
                opts.append((c, ""))
        else:
            words.append(a)
        k += 1
    return opts, words, None

def last_flag(opts, on, off):
    """The last of the options `on` (True) / `off` (False) given, else None: git's last-one-wins."""
    state = None
    for name, _ in opts:
        if name in on:
            state = True
        elif name in off:
            state = False
    return state

def rev_commit(directory, word):
    """The commit id `word` names in the repository at `directory`, or '' when it names none."""
    return git(directory, "rev-parse", "--verify", "--quiet", "--end-of-options", word + "^{commit}")

def rev_tree(directory, word):
    """The tree id `word` names in the repository at `directory` (a commit's tree), or '' when it names none."""
    return git(directory, "rev-parse", "--verify", "--quiet", "--end-of-options", word + "^{tree}")

def all_unmerged(directory, specs):
    """Is every index entry these pathspecs match (one at least) in conflict: a rebase, merge or cherry-pick stopped
    on it? Then `git checkout`/`restore --ours|--theirs` and `git rm` settle the conflict, which is how a conflicted
    backlog/ file is resolved (an editor write there is refused). Asked of git itself, with fsmonitor off."""
    if not specs:
        return False
    off = ("-c", "core.fsmonitor=false")
    listed = {p for p in git(directory, *off, "ls-files", "-z", "--", *specs).split("\0") if p}
    stages = git(directory, *off, "ls-files", "-z", "--unmerged", "--", *specs).split("\0")
    return bool(listed) and listed <= {f.partition("\t")[2] for f in stages}

def apply_paths(directory, opts, patches):
    """The paths a `git apply` of these patch files would write, as git itself reads them (`git apply --numstat
    -z`, with the options that move paths: -p, --directory, --include, --exclude, …), or None when git can't read
    them. It writes nothing and runs no hook or fsmonitor program."""
    keep = []
    for name, value in opts:
        if name in ("p", "C"):
            keep.append(f"-{name}{value}")
        elif name in ("directory", "include", "exclude"):
            keep.append(f"--{name}={value}")
        elif name in ("unidiff-zero", "recount", "inaccurate-eof", "allow-empty", "unsafe-paths", "reverse", "R"):
            keep.append("-R" if name == "R" else f"--{name}")
    try:
        r = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "apply", "--numstat",
                            "-z", *keep, "--", *patches], cwd=directory, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    # `added<TAB>deleted<TAB>path` per file; a field without its counts is a path on its own (a `\0old\0new` pair)
    paths = [f.split("\t", 2)[2] if f.count("\t") >= 2 else f for f in r.stdout.split("\0")]
    paths = [p for p in paths if p]
    # --numstat names a rename by one path only (the new one, or under -R the old), and the other is deleted, so both
    # sides of every rename and copy count too, read as written (C-unquoted; with -p or --directory one may name a
    # path git wouldn't touch, which over-blocks at worst)
    heads = ("rename from ", "rename to ", "copy from ", "copy to ")
    for patch in patches:
        try:
            with open(os.path.join(directory, patch), encoding="utf-8", errors="replace") as fh:
                paths += [c_unquote(line.split(" ", 2)[2].rstrip("\r\n")) for line in fh if line.startswith(heads)]
        except OSError:
            return None
    return paths

def c_unquote(path):
    """A path as git writes it in a patch header: `"…"` with C escapes (`\\303\\251`, `\\"`) when it holds odd bytes."""
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path
    try:
        return path[1:-1].encode("latin-1", "backslashreplace").decode("unicode_escape").encode("latin-1").decode(
            "utf-8", "replace")
    except (UnicodeError, ValueError):
        return path

def specs_touch_immutable(specs, bases):
    """Does a pathspec name data/, data/snapshots or data/indexes or a path in them (a glob by its fixed
    directory)? Whole-tree pathspecs don't count here: git writes only tracked files, and data/ is never tracked."""
    for base in bases:
        for s_ in specs:
            if s_.startswith(":"):
                continue
            if any(c in s_ for c in "*?["):
                s_ = re.split(r"[*?\[]", s_, maxsplit=1)[0].rpartition("/")[0] or "."
            if is_or_contains_immutable(rel(s_, base)):
                return True
    return False

def word_is_path(directory, word):
    """Does `word` name a path git would read as a pathspec: one on disk, or one the index holds?"""
    return os.path.lexists(os.path.join(directory, word)) or bool(
        git(directory, "-c", "core.fsmonitor=false", "ls-files", "--", word))

def backlog_git_specs(sub, args, directory, unmerged_ok=True):
    """(pathspecs, from_file): the pathspecs by which this git subcommand would write files in the worktree or the
    index, and whether it also reads paths from a file or stdin, which this guard can't see. None when this form
    writes nothing by pathspec: a branch or commit operation, unstaging, a read-only command or a dry run. `-p` with
    no pathspec works on the whole tree (`.`). `unmerged_ok` is False when git is pointed at another repository
    (`--git-dir`, `--work-tree`), whose conflicts the hook doesn't read."""
    def unmerged(specs):
        return unmerged_ok and all_unmerged(directory, specs)
    def patch(opts, specs):
        return specs or (["."] if any(n in ("p", "patch") for n, _ in opts) else [])
    if sub == "rm":
        opts, words, after = git_words(args, ("pathspec-from-file",))
        specs = words + (after or [])
        if last_flag(opts, ("n", "dry-run"), ("no-dry-run",)) or unmerged(specs):
            return None
        return specs, any(n == "pathspec-from-file" for n, _ in opts)
    if sub == "mv":
        opts, words, after = git_words(args)
        if last_flag(opts, ("n", "dry-run"), ("no-dry-run",)):
            return None
        return words + (after or []), False
    if sub == "restore":
        opts, words, after = git_words(args, ("source", "pathspec-from-file", "conflict"), "s")
        staged = last_flag(opts, ("S", "staged"), ("no-staged",))
        worktree = last_flag(opts, ("W", "worktree"), ("no-worktree",))
        source = last_flag(opts, ("s", "source"), ("no-source",))
        if staged and not worktree and not source:
            return None  # unstaging: the index takes HEAD's copy, the file on disk is the CLI's
        specs = patch(opts, words + (after or []))
        if not source and unmerged(specs):
            return None  # settling a conflict (`--ours`, `--theirs`, `--merge`)
        return specs, any(n == "pathspec-from-file" for n, _ in opts)
    if sub == "checkout":
        opts, words, after = git_words(args, ("orphan", "pathspec-from-file", "conflict"), "bB")
        from_file = any(n == "pathspec-from-file" for n, _ in opts)
        if after is not None:
            treeish, specs = words[:1], after
        elif words and rev_commit(directory, words[0]):
            treeish, specs = words[:1], words[1:]  # `git checkout <commit> <path>…`; a lone commit is a switch
        else:
            treeish, specs = [], words
        specs = patch(opts, specs)
        if not treeish and unmerged(specs):
            return None  # settling a conflict (`--ours`, `--theirs`, `--merge`)
        return specs, from_file
    if sub == "reset":
        opts, words, after = git_words(args, ("pathspec-from-file",))
        from_file = any(n == "pathspec-from-file" for n, _ in opts)
        if after is not None:
            treeish, specs = words[:1], after
        elif words and (rev_tree(directory, words[0]) or not word_is_path(directory, words[0])):
            # a commit, or a word that is no path either: one the hook can't resolve yet (`git fetch origin dev:t &&
            # git reset t <path>`) is still a tree-ish, and not HEAD's (TASK-244 security review)
            treeish, specs = words[:1], words[1:]
        else:
            treeish, specs = [], words  # no path at all: the whole branch or index moves, a commit operation
        specs = patch(opts, specs)
        head = rev_tree(directory, "HEAD")
        if not treeish or (head and rev_tree(directory, treeish[0]) == head):
            return None  # unstaging: the index takes HEAD's copy, the file on disk is the CLI's
        return specs, from_file
    if sub == "stash":
        if args and args[0] == "push":
            args = args[1:]
        elif args and not args[0].startswith("-"):
            return None  # pop, apply, list, show, save <message>, …
        opts, words, after = git_words(args, ("message", "pathspec-from-file"), "m")
        specs = words + (after or [])
        from_file = any(n == "pathspec-from-file" for n, _ in opts)
        return specs, from_file  # none: a whole-tree stash
    if sub in ("apply", "am"):
        opts, words, after = git_words(args, ("exclude", "include", "directory", "whitespace", "build-fake-ancestor",
                                              "resolvemsg", "patch-format", "quoted-cr", "empty"), "pC")
        names = {n for n, _ in opts}
        if sub == "apply" and names & {"stat", "numstat", "summary", "check"} and not last_flag(opts, ("apply",),
                                                                                                ("no-apply",)):
            return None  # it only reports
        if sub == "am" and names & {"continue", "resolved", "r", "skip", "abort", "quit", "show-current-patch"}:
            return None  # a stopped `git am`: it goes on with the patch it already holds, or stops
        patches = words + (after or [])
        if not patches or "-" in patches:
            return [], True  # the patch comes on stdin
        paths = apply_paths(directory, opts, patches)
        if paths is None:
            return [], True
        # git reads a patch's paths from the top of the worktree, and from a subdirectory skips the ones outside it
        return [os.path.join(repo_root(directory), p) for p in paths], False
    if sub == "clean":
        opts, words, after = git_words(args, ("exclude",), "e")
        excludes = [v for n, v in opts if n in ("e", "exclude")]
        if last_flag(opts, ("n", "dry-run"), ("no-dry-run",)) or (
                any(v.strip("/") == "backlog" for v in excludes) and not any(v.startswith("!") for v in excludes)):
            return None  # a dry run, or `-e backlog` keeps it (unless a `!` pattern puts things back)
        return words + (after or []) or ["."], False  # no pathspec: the directory it runs in
    if sub == "merge-file":
        opts, words, after = git_words(args, ("marker-size",), "L")
        if last_flag(opts, ("p", "stdout"), ("no-stdout",)):
            return None  # it prints the result
        return (words + (after or []))[:1], False  # it rewrites <current-file>
    if sub == "checkout-index":
        opts, words, after = git_words(args, ("prefix", "stage"))
        names = {n for n, _ in opts}
        if "temp" in names:
            return None  # temporary files, not the worktree
        prefix = ([v for n, v in opts if n == "prefix"] or [""])[-1]
        paths = words + (after or []) + (["backlog/"] if names & {"a", "all"} else [])  # -a: every file, backlog/ too
        # each file lands at <top>/<prefix><top-relative path>: `--prefix=out/` writes none in backlog/,
        # `--prefix=backlog/tasks/` all of them, from any subdirectory
        if not prefix:
            return paths, "stdin" in names
        top = os.path.realpath(repo_root(directory))  # git prints it resolved (/private/var on macOS): compare so
        return [os.path.join(top, prefix + os.path.relpath(os.path.realpath(os.path.join(directory, p_)), top))
                for p_ in paths], "stdin" in names
    if sub == "update-index":
        opts, words, after = git_words(args, ("chmod", "index-version", "cacheinfo"))
        if {n for n, _ in opts} <= {"assume-unchanged", "no-assume-unchanged", "skip-worktree", "no-skip-worktree",
                                    "refresh", "really-refresh", "q", "quiet", "ignore-missing", "unmerged"}:
            return None  # index flags only: no file content changes
        cache = [w for n, v in opts if n == "cacheinfo" for w in (v, v.split(",")[-1]) if v]
        return words + cache + (after or []), bool({n for n, _ in opts} & {"stdin", "index-info"})
    if sub == "read-tree":
        opts, _, _ = git_words(args, ("prefix", "index-output", "exclude-per-directory", "super-prefix"))
        prefix = [v for n, v in opts if n == "prefix"]
        if not prefix and any(n == "u" for n, _ in opts):
            return [repo_root(directory)], False  # `-u` writes the tree it reads over the whole worktree
        # read into the index at <prefix>, from the top of the worktree (`--prefix=` is the root itself)
        return ([os.path.join(repo_root(directory), prefix[-1] or ".")], False) if prefix else None
    return None

# options whose attached value is a path (`--prefix=$P`): one written with a `$`, `~` or backquote is refused as
# unresolved (option words aren't resolved like path words)
PATH_VALUED = ("--prefix", "--directory", "--include", "--exclude", "--pathspec-from-file", "--work-tree")

BACKLOG_GIT_SUBS = ("rm", "mv", "restore", "checkout", "reset", "stash", "apply", "am", "clean", "merge-file",
                    "checkout-index", "update-index", "read-tree")

# git settings and environment variables whose value git runs as a shell command (a pager, an editor, a diff or
# merge driver, a filter): the value is checked as a command of its own (TASK-244 security review)
COMMAND_ENV = ("GIT_PAGER", "PAGER", "GIT_EDITOR", "EDITOR", "VISUAL", "GIT_SEQUENCE_EDITOR", "GIT_EXTERNAL_DIFF",
               "GIT_SSH_COMMAND", "GIT_ASKPASS")

def embedded_commands(argv, g):
    """The shell commands a git invocation runs from its own words: every `-c key=value` value (a pager, editor,
    diff.external, a filter or driver; harmless for the rest, which aren't commands that write), the COMMAND_ENV
    assignments before it, `rebase --exec/-x`, `bisect run`, `submodule foreach`, `grep -O<cmd>`/
    `--open-files-in-pager=<cmd>`, `difftool -x/--extcmd`, each `filter-branch --*-filter`, and the value a
    `git config <key> <value>` sets."""
    texts = [v for v in git_config(argv).values() if v]
    texts += [v for n, v in getattr(argv, "assigns", {}).items() if n in COMMAND_ENV and v]
    if g is None:
        return texts
    sub, args = g[0], g[1]
    def values(longs, short=""):
        out = []
        for k, a in enumerate(args):
            name, eq, value = a.partition("=")
            if name in longs:
                out.append(value if eq else (args[k + 1] if k + 1 < len(args) else ""))
            elif short and a.startswith(short) and not a.startswith("--"):
                out.append(a[len(short):] or (args[k + 1] if k + 1 < len(args) else ""))
        return out
    if sub == "rebase":
        texts += values(("--exec",), "-x")
    elif sub == "difftool":
        texts += values(("--extcmd",), "-x")
    elif sub == "grep":
        texts += [a.partition("=")[2] for a in args if a.startswith("--open-files-in-pager=")]
        texts += [a[2:] for a in args if a.startswith("-O") and len(a) > 2]
    elif sub == "filter-branch":
        texts += values(tuple(f"--{f}-filter" for f in ("env", "tree", "index", "parent", "msg", "commit", "tag-name")))
    elif sub == "config":  # `git config core.pager '<cmd>'` sets what a later git runs
        texts += [a for a in args if not a.startswith("-")][1:2]
    elif sub == "bisect" and args[:1] == ["run"]:
        texts.append(shlex.join(args[1:]))
    elif sub == "submodule" and "foreach" in args:
        rest = [a for a in args[args.index("foreach") + 1 :] if a not in ("--recursive", "-q", "--quiet")]
        texts.append(" ".join(rest))
    return [t for t in texts if t.strip()]

def copy_targets(paths, base):
    """Where `cp -R`/`rsync`/`ditto` puts each source when the destination is a directory: dest/<its name>, or, for
    a source ending in `/` (its contents), dest/<each entry in it>."""
    dest, out = paths[-1], []
    full_dest = dest if os.path.isabs(dest) else os.path.join(base, dest)
    if not os.path.isdir(full_dest):
        return out
    for src in paths[:-1]:
        full_src = src if os.path.isabs(src) else os.path.join(base, src)
        if src.endswith("/") or src.endswith("/."):
            if os.path.isdir(full_src):
                out += [os.path.join(full_dest, n) for n in os.listdir(full_src)]
        else:
            out.append(os.path.join(full_dest, os.path.basename(os.path.normpath(full_src))))
    return out

def extracts(head, args):
    """Does this tar/unzip extract (rather than list or create)?"""
    if head == "unzip":
        return not any(a in ("-l", "-v", "-t", "-Z", "-p") for a in args)
    first = args[0] if args else ""
    return any(a in ("-x", "--extract", "--get") for a in args) or (
        not first.startswith("--") and "x" in first.lstrip("-"))

def extract_dir(head, args):
    """The directory tar `-C`/`--directory` or unzip `-d` extracts into, or None (the current one)."""
    flag = "-d" if head == "unzip" else "-C"
    for k, a in enumerate(args):
        if a in (flag, "--directory") and k + 1 < len(args):
            return args[k + 1]
        if a.startswith("--directory="):
            return a.partition("=")[2]
    return None

def backlog_repo(directories):
    """Is there a backlog/ in the worktree holding any of these directories, or in its repository's main worktree?"""
    return any(os.path.isdir(os.path.join(r, "backlog")) for b in directories
               for r in (repo_root(b), main_worktree(b)) if r)

# what `find -exec` may run on what it finds without writing it
FIND_READERS = frozenset("grep egrep fgrep rg cat head tail wc ls file stat echo printf test [ basename dirname md5 "
                         "md5sum shasum sha1sum sha256sum diff cmp realpath readlink true false".split())

def find_writes(args):
    """Does this find delete what it finds, or run anything but a known reader on it (`-exec rm {} +`, `-execdir git
    restore -s dev {} ;`, `-ok sh -c …`)? Which files it picks can't be seen here."""
    for k, a in enumerate(args):
        if a == "-delete" or a.startswith("--pre"):  # `-exec rg --pre <prog>` runs <prog> on each file
            return True
        if a in ("-exec", "-execdir", "-ok", "-okdir") and (k + 1 == len(args) or
                                                            os.path.basename(args[k + 1]) not in FIND_READERS):
            return True
    return False

def reaches_backlog_tree(path, base):
    """Is `path` (or what its glob matches) in backlog/, the root of a worktree, or a directory above one with a
    backlog/: a find started there can reach backlog/ files."""
    roots = [os.path.realpath(r) for r in (repo_root(base), main_worktree(base))
             if r and os.path.isdir(os.path.join(r, "backlog"))]
    for p in expand(path, base):
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))
        r = rel(p, base)
        if in_backlog(r) or (r == "." and os.path.isdir(os.path.join(full, "backlog"))):
            return True
        if any(os.path.commonpath([full, root]) == full for root in roots):
            return True
    return False

def git_work_trees(argv):
    """Where git resolves pathspecs besides the command's own directory: each `--work-tree` and GIT_WORK_TREE, as
    written (resolved by the caller, so one it can't resolve is refused)."""
    trees, k = [], 1
    while k < len(argv) and argv[k].startswith("-"):
        name, eq, value = argv[k].partition("=")
        takes = name in GIT_VALUE_OPTS and not eq
        if name == "--work-tree":
            trees.append(argv[k + 1] if takes and k + 1 < len(argv) else value)
        k += 2 if takes else 1
    if "GIT_WORK_TREE" in getattr(argv, "assigns", {}):
        trees.append(argv.assigns["GIT_WORK_TREE"])
    return trees

IMMUTABLE_MSG = "Blocked: data/snapshots/ and data/indexes/ are immutable (reproducibility, spec 03). Build a new one with `op snapshot build` / `op index build` instead."

MALFORMED_MSG = ("Blocked: protect-data-dir.sh got a tool call it can't read (not a JSON object, an unknown tool, or "
                 "no command or file path), so it can't tell what it would write; refusing (fail closed, TASK-244).")

def main():
    global cwd  # the payload's, replaced by read_payload's below
    # a payload that isn't what Claude Code sends (invalid JSON, a tool this hook isn't wired to, no command or path)
    # is refused: there is nothing to check it against (TASK-244 security review: it was let through)
    if not isinstance(ti, dict) or tool not in ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"):
        refuse(MALFORMED_MSG)
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = ti.get("file_path") or ti.get("notebook_path") or ""
        if not isinstance(path, str) or not path:
            refuse(MALFORMED_MSG)
        if inside_immutable(rel(path, os.path.dirname(path) if os.path.isabs(path) else cwd)):
            refuse(IMMUTABLE_MSG)
        sys.exit(0)

    if not isinstance(ti.get("command"), str) or not ti["command"].strip():
        refuse(MALFORMED_MSG)
    cmd, cwd = read_payload()
    def walked_or_refuse(env_empty, text=None, where=None):
        try:
            return list(walk(cmd if text is None else text, cwd if where is None else where, env_empty))
        except FailClosed as exc:
            refuse(f"Blocked: this git command can't be read reliably ({exc}), so what it does to data/ or backlog/ "
                   "can't be checked. Write abbreviated options out in full and run the git subcommand by its own name.")
        except ParseError:
            # Fail CLOSED (review gate round 3): any parse failure, whatever the text names (`rm -rf . "`), where the
            # main worktree has data/ or the repo has backlog/.
            if data_in(cwd) or os.path.isdir(os.path.join(repo_root(cwd), "backlog")):
                refuse("Blocked: this command could not be parsed (unbalanced quotes?), and this repo has data/ or "
                       "backlog/ — refusing rather than letting it through unexamined. Fix the quoting, or write the "
                       "command more plainly, and retry.")
            sys.exit(0)

    def check(walked, depth=0):
        """Refuse (exit 2) if a command in `walked` writes, moves or deletes what this guard protects. A command a
        git invocation runs from its own words (`embedded_commands`) is checked the same way, from the worktree's
        top, where git runs it; past four levels of that, refused."""
        if depth > 4:
            refuse("Blocked: git commands nested in git commands past four levels can't be checked; write them out.")
        commands = [(argv, d) for argv, d, _ in walked if argv]
        for argv, d, redirects in walked:
            for op, target in redirects:
                if ">" not in op or (op.endswith("&") and target.isdigit()):
                    continue
                resolved_target = resolve(target, argv, d)  # `> "$PWD/data/snapshots/x"`
                if resolved_target is None and (data_in(d) or data_in(cwd) or backlog_repo([d, cwd])):
                    # a target only the shell knows (`> "$(echo data)/snapshots/x"`): refused where data/ is, as a path
                    # word is (TASK-067 final review gate)
                    refuse(IMMUTABLE_MSG + " (A redirect target names a path this guard can't resolve, in a repo with "
                           "data/ or backlog/; write the path out.)")
                target = resolved_target or target
                if ">" in op and inside_immutable(rel(target, d)):
                    refuse(IMMUTABLE_MSG)
                if ">" in op and in_backlog(rel(target, d)):
                    refuse(BACKLOG_MSG)

        DESTROY = {"rm", "shred", "truncate", "rmdir", "unlink"}          # every path arg is a target
        DEST_LAST = {"cp", "rsync", "install", "ln", "ditto"}  # last path arg is the target
        IN_PLACE_EDITORS = ("sed", "perl", "ruby", "awk", "gawk")
        UNRESOLVED_MSG = (IMMUTABLE_MSG + " (A `$` word, `~` or `cd`/`pushd` target names a path this guard can't resolve, "
                          "in a repo with data/; write the path out.)")
        for raw, d in commands:
            # every word through cmdparse.expand_word: `"$PWD"/data`, `~+/data`, `$(pwd)`; `unresolved` keeps the words
            # it can't tell, which are refused below where they would decide a check (TASK-067 review gate)
            resolved = [raw[0], *(w if w.startswith("-") else resolve(w, raw, d) for w in raw[1:])]
            unresolved = {w for w, r in zip(raw, resolved) if r is None}
            unknown = raw.dir_unknown  # a `cd` before it went somewhere this guard can't tell
            if raw.env_empty:  # `"$TMPDIR"/*` read with TMPDIR '' is `/*`: checked as written, not globbed (NO_GLOB)
                NO_GLOB.update(r for w, r in zip(raw, resolved)
                               if r and (m := ENV_LEAD.match(w)) and (m.group(1) or m.group(2)) not in raw.shell_vars)
            # a word that expands to nothing names no path (`rm -rf "$TMPDIR"` with TMPDIR read as '')
            argv = Argv([w if r is None else r for w, r in zip(raw, resolved) if r != "" or w == ""], raw.via_xargs,
                        raw.assigns)
            head, args = argv[0], argv[1:]
            paths = [a for a in args if not a.startswith("-")]
            g = git_subcommand(argv, d)
            in_place = any(a.startswith("--in-place") or (a.startswith("-") and not a.startswith("--") and "i" in a) for a in args)
            if head == "perl":
                in_place = perl_in_place(args)
            if head == "ruby":
                in_place = perl_in_place(args, "0EFICrxWKT")
            if head in ("awk", "gawk"):  # gawk -i inplace / --include=inplace edits each file
                in_place = any(v.startswith("inplace") for v in
                               [*(args[k + 1] for k in range(len(args) - 1) if args[k] in ("-i", "--include")),
                                *(a.partition("=")[2] for a in args if a.startswith("--include=")),
                                *(a[2:] for a in args if a.startswith("-i") and len(a) > 2 and not a.startswith("--"))])
            # xargs appends words read from stdin that the hook never sees: refuse what they would decide (TASK-067)
            root_ = repo_root(d)
            # an unresolved path may be anywhere: data/ counts if this worktree, its main worktree, or the call's own
            # (when a `cd` went somewhere unknown, `d` is only where the walk last knew) has one (review gate round 3)
            has_data = data_in(d) or data_in(cwd)
            def refuse_unresolved(words_, implicit_cwd=False):
                """Refuse (where data/ or backlog/ is) when a path that decides a check can't be resolved, or the command works
                on the current directory itself and a `cd` before it couldn't be followed."""
                if (has_data or backlog_repo([d, cwd])) and (any(w in unresolved for w in words_)
                                                             or (implicit_cwd and unknown)):
                    refuse(UNRESOLVED_MSG)
            if getattr(argv, "via_xargs", False) and (
                head in DESTROY | DEST_LAST | {"mv", "tee"}
                or (head in IN_PLACE_EDITORS and in_place)
                or (g is not None and g[0] in ("add", "stage", *BACKLOG_GIT_SUBS))
            ) and (os.path.isdir(os.path.join(root_, "data")) or os.path.isdir(os.path.join(root_, "backlog"))):
                refuse("Blocked: xargs appends paths this guard can't see, and this repo has data/ or backlog/. "
                       "Run the command on the paths themselves (a shell loop or a glob) so they can be checked.")
            for text in embedded_commands(argv, g):  # `git -c core.pager='rm …' log`, `rebase --exec '…'`
                check(walked_or_refuse(raw.env_empty, text, repo_root(g[2]) if g else d), depth + 1)
            if g and g[0] in BACKLOG_GIT_SUBS:
                trees = [resolve(t, raw, d) for t in git_work_trees(argv)]  # `--work-tree=$X` too
                found = backlog_git_specs(g[0], g[1], g[2], unmerged_ok=not (trees or git_dir(argv, d)))
                if found is not None:
                    specs, from_file = found
                    bases = [g[2], *(os.path.join(g[2], t) for t in trees if t)]  # after -C, as git reads it
                    has_backlog = backlog_repo([*bases, cwd])
                    # a pathspec, -C or work tree only the shell knows (`git restore "$F"`, `cd "$X" && git rm .`)
                    hidden = unknown or None in trees or any(
                        w in unresolved for w in [*specs, *argv[1 : len(argv) - len(g[1]) - 1]]) or any(
                        a.partition("=")[0] in PATH_VALUED and re.search(r"[$`~]", a.partition("=")[2]) for a in g[1])
                    if has_backlog and (from_file or hidden):
                        refuse(BACKLOG_GIT_MSG + " (Its paths come from a file, stdin or a word this guard can't "
                               "resolve; name them on the command line.)")
                    literal = "--literal-pathspecs" in argv[1 : len(argv) - len(g[1]) - 1] or \
                        argv.assigns.get("GIT_LITERAL_PATHSPECS", os.environ.get("GIT_LITERAL_PATHSPECS", "0")) \
                        not in ("", "0")
                    if specs_reach_backlog(specs, bases, literal):
                        refuse(BACKLOG_GIT_MSG)
                    if g[0] in ("apply", "am") and sum(c[0][0] not in ("cd", "pushd", "popd") for c in commands) > 1:
                        # the patch is read now, before an earlier command in the call rewrites it
                        refuse(BACKLOG_GIT_MSG + " (Run `git apply`/`git am` in a call of its own, so the patch "
                               "this guard reads is the one git applies.)")
                    if specs_touch_immutable(specs, bases):  # data/ is gitignored, but a ref may still hold it
                        refuse(IMMUTABLE_MSG)
            if g and g[0] in ("add", "stage"):  # `git stage` is `git add`
                a = g[1]
                forced = any(x in ("-f", "--force") or (x.startswith("-") and not x.startswith("--") and "f" in x) for x in a)
                if forced:
                    refuse_unresolved([p for p in a if not p.startswith("-")], implicit_cwd=True)
                if forced and any(is_data(rel(p, g[2])) for p in a if not p.startswith("-")):
                    refuse(DATA_MSG)
                if any(through_takedowns(p, g[2], forced) for p in a if not p.startswith("-")):
                    refuse(TAKEDOWNS_MSG)  # a forced whole-tree add reaches takedowns/ through the dry run below
                if forced and any(x.startswith("--pathspec-from-file") for x in a):
                    refuse("Blocked: a forced `git add --pathspec-from-file` stages paths this guard can't see; data/ and "
                           "takedowns/ are never committed. Name the paths on the command line.")
                if forced and whole_tree(a) and os.path.isdir(os.path.join(repo_root(g[2]), "data")):
                    refuse(DATA_MSG + " (A forced add of the whole tree or a `:` magic pathspec stages all of it.)")
                if forced:
                    staged = dry_run_add(argv, a, g[2])
                    if staged is None:
                        refuse("Blocked: git refused a dry run of this forced `git add`, so what it would stage can't be "
                               "checked for data/ or takedowns/. Drop -f, or name the paths plainly.")
                    if any(is_data(s) for s in staged):
                        refuse(DATA_MSG)
                    if any(has_takedowns(s) for s in staged):
                        refuse(TAKEDOWNS_MSG)
                continue
            if g and g[0] == "update-index":
                # update-index ignores .gitignore entirely; paths from stdin are unseen
                a = g[1]
                if "--index-info" in a or ("--add" in a and "--stdin" in a):
                    refuse("Blocked: `git update-index --index-info` / `--add --stdin` stage paths this guard can't see; "
                           "data/ and takedowns/ are never committed.")
                # --cacheinfo m,sha,path (and the attached --cacheinfo=m,sha,path: TASK-067 review gate)
                values = [p.partition("=")[2] if p.startswith("--cacheinfo=") else p for p in a]
                words = [w for p in values if not p.startswith("-") for w in (p, p.split(",")[-1])]
                if "--add" in a:
                    refuse_unresolved(values)
                if "--add" in a and any(any_rel(is_data, w, g[2]) for w in words):
                    refuse(DATA_MSG)
                if "--add" in a and any(through_takedowns(w, g[2], False) for w in words):
                    refuse(TAKEDOWNS_MSG)
                continue
            gm = git_subcommand(argv, d)
            # `--output <file>` / `--output=<file>` (git log, diff, format-patch, …) writes that file (TASK-067 final
            # review gate)
            outputs = []
            for k_, a_ in enumerate(gm[1] if gm else []):
                if a_ == "--output" and k_ + 1 < len(gm[1]):
                    value = gm[1][k_ + 1]
                elif a_.startswith("--output="):
                    value = a_.partition("=")[2]  # an option word: not resolved above
                else:
                    continue
                out_path = resolve(value, raw, d)
                if out_path is None and has_data:
                    refuse(UNRESOLVED_MSG)
                outputs.append(out_path or value)
            if any(any_rel(inside_immutable, o, gm[2]) for o in outputs):
                refuse(IMMUTABLE_MSG)
            if any(any_rel(in_backlog, o, gm[2]) for o in outputs):
                refuse(BACKLOG_MSG)
            if gm and gm[0] == "format-patch" and "--stdout" not in gm[1]:
                # format-patch writes its patches into `-o`/`--output-directory` (or a unique prefix of it), else
                # format.outputDirectory, else the directory it runs in (TASK-156)
                fp, out_dirs = gm[1][: gm[1].index("--") if "--" in gm[1] else None], []
                for k_, a_ in enumerate(fp):
                    following = fp[k_ + 1] if k_ + 1 < len(fp) else ""
                    name, eq, attached = a_.partition("=")
                    if len(name) >= len("--output-d") and "--output-directory".startswith(name):
                        out_dirs.append(attached if eq else following)
                    elif a_.startswith("-") and not a_.startswith("--") and "o" in a_[1:]:
                        out_dirs.append(a_[a_.index("o", 1) + 1 :] or following)  # `-o<dir>`, `-ko <dir>`
                if not out_dirs and git_config_opaque(argv) and has_data:
                    # format.outputDirectory may come from config this guard can't read (GIT_CONFIG_*, --config-env)
                    refuse(IMMUTABLE_MSG + " (`git format-patch` without -o reads format.outputDirectory from config this "
                           "guard can't read, in a repo with data/; pass -o <dir> or --stdout.)")
                if not out_dirs:
                    out_dirs = [git_config(argv).get("format.outputdirectory")
                                or git(gm[2], "config", "--get", "format.outputDirectory") or "."]
                for out_dir in out_dirs:
                    found = resolve(out_dir, raw, gm[2])
                    if found is None and has_data:
                        refuse(UNRESOLVED_MSG)
                    patch = os.path.join(found or out_dir, "0001-x.patch")
                    if any_rel(inside_immutable, patch, gm[2]):
                        refuse(IMMUTABLE_MSG)
                    if any_rel(in_backlog, patch, gm[2]):
                        refuse(BACKLOG_MSG)
            if gm and gm[0] == "clean":
                # Separate -e/--exclude (and their values) from the flag clusters first: an attached `-enode_modules`
                # contains an `n` and was read as a dry run (review round 4).
                excludes, flags, pathspecs, args, k = [], [], [], gm[1], 0
                while k < len(args):
                    a_ = args[k]
                    if a_ in ("-e", "--exclude") and k + 1 < len(args):
                        excludes.append(args[k + 1]); k += 2; continue
                    if a_.startswith("--exclude="):
                        excludes.append(a_.split("=", 1)[1]); k += 1; continue
                    if a_.startswith("-") and not a_.startswith("--") and "e" in a_[1:]:
                        # A short cluster is read letter by letter, as git does: `-fdxenode_modules` is -f -d -x and
                        # -e node_modules, so only the letters BEFORE `e` are flags (review round 5).
                        pre, _, val = a_[1:].partition("e")
                        if pre:
                            flags.append("-" + pre)
                        if val:
                            excludes.append(val); k += 1
                        elif k + 1 < len(args):
                            excludes.append(args[k + 1]); k += 2
                        else:
                            k += 1
                        continue
                    if a_ == "--":
                        pathspecs += args[k + 1 :]; break
                    (flags if a_.startswith("-") else pathspecs).append(a_); k += 1
                shorts = "".join(f[1:] for f in flags if not f.startswith("--"))
                dry = "n" in shorts or "--dry-run" in flags
                only_ignored = "X" in shorts
                ignored = only_ignored or "x" in shorts
                # `-e data` keeps data/ under -x, but under -X it ADDS data/ to the ignore set and deletes it.
                excluded = not only_ignored and any(v.strip("/") == "data" for v in excludes)
                def covers_data(p):
                    return p.startswith(":") or any_rel(lambda r: r is not None and (r == "data" or r.startswith("data/") or r == "."), p, gm[2])
                if ignored and not dry and not excluded:
                    refuse_unresolved(pathspecs, implicit_cwd=True)  # `cd "$X" && git clean -fdx`, `git clean -fdx "$Y"`
                outside = bool(pathspecs) and not any(covers_data(p) for p in pathspecs)
                if ignored and not dry and not excluded and not outside:
                    refuse("Blocked: `git clean -x/-X` deletes gitignored files — that is all of data/ (snapshots, indexes, "
                           "search records). Clean specific paths outside data/, or use -x (not -X) with -e data.")
            stash_writes = gm and gm[0] == "stash" and (not gm[1] or gm[1][0] in ("push", "save") or gm[1][0].startswith("-"))
            # -a alone or in a short cluster (`-qa`, `-ua`, `-au`), but not inside -m's attached message (`-qmall`)
            if stash_writes and any(a == "--all" or (a.startswith("-") and not a.startswith("--") and "a" in a[1:].partition("m")[0])
                                    for a in gm[1][: gm[1].index("--") if "--" in gm[1] else None]):
                refuse("Blocked: `git stash --all` stashes (and removes) gitignored files, including data/.")
            if head in DESTROY | {"mv", "tee"} and any(any_rel(in_backlog, p, d) for p in paths):
                refuse(BACKLOG_MSG)
            if head in DEST_LAST and paths and any_rel(in_backlog, paths[-1], d):  # copying OUT of backlog/ is fine
                refuse(BACKLOG_MSG)
            if head in DEST_LAST and len(paths) > 1 and any(in_backlog(rel(t, d)) for t in copy_targets(paths, d)):
                refuse(BACKLOG_MSG)  # `cp -R /old/backlog .`, `rsync -a /old/ ./`
            if head in ("sponge", "touch") and any(any_rel(in_backlog, p, d) for p in paths):
                refuse(BACKLOG_MSG)
            if head == "patch" and backlog_repo([d, cwd]) and not any(
                    a in ("--dry-run", "-C", "--check") for a in args):
                refuse(BACKLOG_MSG + " (patch(1) writes the files its patch names, which this guard can't read; use "
                       "`git apply` on a patch file, in a call of its own.)")
            if head in ("tar", "bsdtar", "gtar", "unzip") and extracts(head, args):
                where = extract_dir(head, args) or "."
                if where in unresolved or reaches_backlog_tree(where, d):
                    refuse(BACKLOG_MSG + " (An archive extracted here can overwrite backlog/ files; extract it into "
                           "a directory of its own.)")
            # a word expand_word couldn't resolve is a path only the shell knows (`rm -rf "$UNSET/x"`): refuse where
            # data/ is, for every path that decides a check below
            if head in DESTROY | {"mv", "tee"}:
                refuse_unresolved(paths)
            if head in DEST_LAST:
                refuse_unresolved(paths if head == "rsync" and any(rsync_removes_sources(a) for a in args) else paths[-1:])
            if head == "dd":
                refuse_unresolved([a for a in raw[1:] if a.startswith("of=")])
            if head in IN_PLACE_EDITORS and in_place:  # not the program text (`sed -i "s/$x/y/" f`): words naming a path root
                refuse_unresolved([p for p in paths if p[:1] in "$~`"], implicit_cwd=True)
            if head in DESTROY and any(covers_immutable(p, d) for p in paths):
                refuse(IMMUTABLE_MSG + " To retire an old version use `op index retire <index_version>` (it refuses while a search record pins it).")
            if head == "mv" and paths and (any(covers_immutable(p, d) for p in paths[:-1]) or any_rel(inside_immutable, paths[-1], d)):
                refuse(IMMUTABLE_MSG)
            if head in DEST_LAST and paths and any_rel(is_or_contains_immutable, paths[-1], d):
                refuse(IMMUTABLE_MSG)
            if head == "rsync" and paths and any(rsync_deletes(a) for a in args) and covers_immutable(paths[-1], d):
                refuse(IMMUTABLE_MSG)
            if head == "rsync" and any(rsync_removes_sources(a) for a in args) and any(covers_immutable(p, d) for p in paths[:-1]):
                refuse(IMMUTABLE_MSG)  # it deletes each source file it copied
            if head == "tee" and any(any_rel(inside_immutable, p, d) for p in paths):
                refuse(IMMUTABLE_MSG)
            if head == "dd" and any(a.startswith("of=") and inside_immutable(rel(a[3:], d)) for a in args):
                refuse(IMMUTABLE_MSG)
            if head == "dd" and any(a.startswith("of=") and in_backlog(rel(a[3:], d)) for a in args):
                refuse(BACKLOG_MSG)
            # every start path counts, `.` when none is named; a start ABOVE data/ deletes inside it (conservative:
            # `find . -name '*.pyc' -delete` from a root with data/snapshots is refused too)
            find_deletes = head == "find" and any(a in args for a in ("-delete", "-exec", "-execdir", "-ok", "-okdir"))
            if find_deletes:
                refuse_unresolved(find_starts(args), implicit_cwd=not any(os.path.isabs(p) for p in find_starts(args)))
            if find_deletes and any(covers_immutable(p, d) for p in find_starts(args)):
                refuse(IMMUTABLE_MSG)
            for k_, a_ in enumerate(args):  # `-fprint <file>` and its kin write that file, as a redirect does
                if a_ in ("-fprint", "-fprint0", "-fprintf", "-fls"):
                    out = args[k_ + 1] if k_ + 1 < len(args) else ""
                    if out in unresolved and (has_data or backlog_repo([d, cwd])):
                        refuse(BACKLOG_MSG + " (find writes to a file this guard can't resolve; write it out.)")
                    if any_rel(inside_immutable, out, d):
                        refuse(IMMUTABLE_MSG)
                    if any_rel(in_backlog, out, d):
                        refuse(BACKLOG_MSG)
            if head == "find" and find_writes(args):
                starts = find_starts(args)
                if backlog_repo([d, cwd]) and (any(s in unresolved for s in starts)
                                               or (unknown and not all(os.path.isabs(s) for s in starts))):
                    refuse(BACKLOG_MSG + " (find's start path can't be resolved here; write it out.)")
                if any(reaches_backlog_tree(s, d) for s in starts):
                    refuse(BACKLOG_MSG + " (`find … -delete` or `-exec <command>` from here can reach backlog/ files, "
                           "and which ones can't be seen; start find in the directories you mean.)")
            if head in IN_PLACE_EDITORS and in_place and any(any_rel(inside_immutable, p, d) for p in paths):
                refuse(IMMUTABLE_MSG)
            if head in IN_PLACE_EDITORS and in_place and any(any_rel(lambda r: in_backlog(r) and not in_decisions(r), p, d) for p in paths):
                refuse(BACKLOG_EDIT_MSG)
    # Every allowed environment variable (HOME, TMPDIR, USER: cmdparse.ENV_FALLBACK) is also read as '': the
    # agent's shell may not have it (review gate round 3: `rm -rf "${TMPDIR}data"`).
    check(walked_or_refuse(False))
    if "$" in cmd or "~" in cmd:  # `cd ~` with HOME '' stays put (TASK-156)
        check(walked_or_refuse(True))
    sys.exit(0)

try:
    main()
except Exception as exc:  # a crash exits 1, which Claude Code lets through: refuse instead (TASK-067 final review gate)
    refuse(f"Blocked: protect-data-dir.sh could not check this command ({type(exc).__name__}). Write it more plainly "
           "(no deep brace nesting, no undecodable characters) and retry.")
PY
if [ -z "$PROG" ]; then  # the heredoc couldn't be read: an empty program would exit 0
  echo "Blocked: protect-data-dir.sh could not load its check; refusing rather than letting the command through." >&2
  exit 2
fi
python3 -c "$PROG" "$HOOK_DIR"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  echo "Blocked: protect-data-dir.sh could not run its check (exit $rc); refusing rather than letting the command through." >&2
fi
[ "$rc" -eq 0 ] || exit 2
