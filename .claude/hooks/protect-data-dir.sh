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
#   enforce-backlog-cli.sh), are refused here; enforce-backlog-cli.sh covers editor writes.
# - `git clean -x/-X` (unless a dry run, `-e data`, or pathspecs outside data/) and `git stash push|save --all`
#   (`-a` in any short cluster: `-qa`, `-ua`) are refused: they remove gitignored files, which is all of data/.
# - Every path word is resolved first (cmdparse.expand_word): `~`, `~+`, `~-`, `$PWD`, `$(pwd)`, `$HOME`, and
#   variables set earlier in the command or in this hook's environment (`rm -f "$TMPDIR/x"` is judged as the
#   path it names); `cd`/`pushd`/`popd` are followed. A path that decides a check and can't be resolved (an
#   unset variable, a relative path after a `cd` that couldn't be followed) is refused in a repo with data/.
# - xargs appends words this guard can't see: rm/unlink/mv/cp/…, sed -i/perl -i and git add/rm/mv/update-index
#   run through xargs are refused in a repo with data/ or backlog/ (cmdparse's `Argv.via_xargs`).
# Globs are expanded against the filesystem (`rm -rf data*`, `*`, `../*`), braces and `$'…'` decoded as bash
# does (`rm -rf data{,}`, cmdparse). An unparseable command that names
# data/ or backlog/ (any case) is refused (fail closed). Paths are resolved against the repo root, so
# frontend/src/data/… is unaffected. Exit 2 blocks.
HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
input=$(cat)
HOOK_INPUT="$input" python3 - "$HOOK_DIR" <<'PY'
import glob, json, os, subprocess, sys
sys.path.insert(0, os.path.join(sys.argv[1], "lib"))
from cmdparse import (GIT_VALUE_OPTS, Argv, FailClosed, ParseError, expand_word, git_subcommand, read_payload, repo_root,
                      walk)

try:
    payload = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except Exception:
    payload = {}
tool = payload.get("tool_name", "")
ti = payload.get("tool_input") or {}
cwd = payload.get("cwd") or os.getcwd()

def expand(path, base):
    """Every path a shell word can name: a glob is expanded against the real filesystem, so `data*`,
    `dat?`, `*` and `../*` are judged by what they match (review round 3). A glob that matches nothing
    deletes nothing, so its literal text is checked only as a path."""
    if not any(ch in path for ch in "*?["):
        return [path]
    full = path if os.path.isabs(path) else os.path.join(base, path)
    return [*glob.glob(full), path]

def rel(path, base):
    """Path relative to the repo root that contains `base`, with forward slashes; None if outside."""
    root = os.path.realpath(repo_root(base))
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(base, path))
    r = os.path.relpath(full, root).replace("\\", "/")
    return None if r.startswith("..") else r

def any_rel(pred, path, base):
    return any(pred(rel(p, base)) for p in expand(path, base))

def resolve(word, argv, d):
    """The path a shell word names (cmdparse.expand_word: `~`, `~+`, `~-`, `$PWD`, `$(pwd)`, `$HOME`, variables
    set earlier in the command or in this hook's environment), or None when it can't be told: a variable this
    hook can't see, or a relative path after a `cd`/`pushd`/`popd` it couldn't follow (TASK-067 review gate)."""
    unknown = getattr(argv, "dir_unknown", False)
    r = expand_word(word, None if unknown else d, getattr(argv, "shell_vars", {}), getattr(argv, "olddir", None))
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
    A worktree has no data/, so removing a worktree stays allowed."""
    root = os.path.realpath(repo_root(base))
    for p in expand(path, base):
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(base, p))
        if is_or_contains_immutable(rel(p, base)) or holds_immutable(full):
            return True
        if os.path.commonpath([full, root]) == full and holds_immutable(root):
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

def find_starts(args):
    """find's start paths: the words before its first expression token, after -H/-L/-P and BSD's flags;
    none means `.`."""
    k, starts = 0, []
    while k < len(args) and args[k] in ("-H", "-L", "-P", "-E", "-X", "-d", "-s", "-x"):
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

def refuse(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)

IMMUTABLE_MSG = "Blocked: data/snapshots/ and data/indexes/ are immutable (reproducibility, spec 03). Build a new one with `op snapshot build` / `op index build` instead."

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if path and inside_immutable(rel(path, os.path.dirname(path) if os.path.isabs(path) else cwd)):
        refuse(IMMUTABLE_MSG)
    sys.exit(0)

cmd, cwd = read_payload()
try:
    walked = list(walk(cmd, cwd))
except FailClosed as exc:
    refuse(f"Blocked: this git command can't be read reliably ({exc}), so what it does to data/ or backlog/ "
           "can't be checked. Write abbreviated options out in full and run the git subcommand by its own name.")
except ParseError:
    # Fail CLOSED (review round 3): an unparseable command that names data/ or backlog/ is refused.
    if "data" in cmd.lower() or "backlog" in cmd.lower():
        refuse("Blocked: this command could not be parsed (unbalanced quotes?) and mentions data/ or backlog/ — "
               "refusing rather than letting it through unexamined. Fix the quoting and retry.")
    sys.exit(0)
commands = [(argv, d) for argv, d, _ in walked if argv]
for argv, d, redirects in walked:
    for op, target in redirects:
        target = resolve(target, argv, d) or target  # `> "$PWD/data/snapshots/x"`
        if ">" in op and inside_immutable(rel(target, d)):
            refuse(IMMUTABLE_MSG)
        if ">" in op and in_backlog(rel(target, d)):
            refuse(BACKLOG_MSG)

DESTROY = {"rm", "shred", "truncate", "rmdir", "unlink"}          # every path arg is a target
DEST_LAST = {"cp", "rsync", "install", "ln"}          # last path arg is the target
IN_PLACE_EDITORS = ("sed", "perl", "ruby", "awk", "gawk")
UNRESOLVED_MSG = (IMMUTABLE_MSG + " (A `$` word, `~` or `cd`/`pushd` target names a path this guard can't resolve, "
                  "in a repo with data/; write the path out.)")
for raw, d in commands:
    # every word through cmdparse.expand_word: `"$PWD"/data`, `~+/data`, `$(pwd)`; `unresolved` keeps the words
    # it can't tell, which are refused below where they would decide a check (TASK-067 review gate)
    resolved = [raw[0], *(w if w.startswith("-") else resolve(w, raw, d) for w in raw[1:])]
    unresolved = {w for w, r in zip(raw, resolved) if r is None}
    unknown = raw.dir_unknown  # a `cd` before it went somewhere this guard can't tell
    argv = Argv([w if r is None else r for w, r in zip(raw, resolved)], raw.via_xargs, raw.assigns)
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
    has_data = os.path.isdir(os.path.join(root_, "data"))
    def refuse_unresolved(words_, implicit_cwd=False):
        """Refuse (in a repo with data/) when a path that decides a check can't be resolved, or the command
        works on the current directory itself and a `cd` before it couldn't be followed."""
        if has_data and (any(w in unresolved for w in words_) or (implicit_cwd and unknown)):
            refuse(UNRESOLVED_MSG)
    if getattr(argv, "via_xargs", False) and (
        head in DESTROY | DEST_LAST | {"mv", "tee"}
        or (head in IN_PLACE_EDITORS and in_place)
        or (g is not None and g[0] in ("add", "stage", "rm", "mv", "update-index"))
    ) and (os.path.isdir(os.path.join(root_, "data")) or os.path.isdir(os.path.join(root_, "backlog"))):
        refuse("Blocked: xargs appends paths this guard can't see, and this repo has data/ or backlog/. "
               "Run the command on the paths themselves (a shell loop or a glob) so they can be checked.")
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
    if gm and gm[0] in ("mv", "rm") and any(in_backlog(rel(p, gm[2])) for p in gm[1] if not p.startswith("-")):
        refuse(BACKLOG_MSG)
    if head in DESTROY | {"mv", "tee"} and any(any_rel(in_backlog, p, d) for p in paths):
        refuse(BACKLOG_MSG)
    if head in DEST_LAST and paths and any_rel(in_backlog, paths[-1], d):  # copying OUT of backlog/ is fine
        refuse(BACKLOG_MSG)
    # a word expand_word couldn't resolve is a path only the shell knows (`rm -rf "$UNSET/x"`): refuse where
    # data/ is, for every path that decides a check below
    if head in DESTROY | {"mv", "tee"}:
        refuse_unresolved(paths)
    if head in DEST_LAST:
        refuse_unresolved(paths if head == "rsync" and any(a.startswith("--remove-s") for a in args) else paths[-1:])
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
    if head == "rsync" and paths and any(a.startswith("--delete") for a in args) and covers_immutable(paths[-1], d):
        refuse(IMMUTABLE_MSG)
    if head == "rsync" and any(a.startswith("--remove-s") for a in args) and any(covers_immutable(p, d) for p in paths[:-1]):
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
    if head in IN_PLACE_EDITORS and in_place and any(any_rel(inside_immutable, p, d) for p in paths):
        refuse(IMMUTABLE_MSG)
    if head in IN_PLACE_EDITORS and in_place and any(any_rel(lambda r: in_backlog(r) and not in_decisions(r), p, d) for p in paths):
        refuse(BACKLOG_EDIT_MSG)
sys.exit(0)
PY
