#!/usr/bin/env bash
# PreToolUse(Bash) review gate: the PROTECTED branches ('main' and 'dev') are protected — all changes
# land through a pull request. The team flow is feature -> PR -> dev (integration) -> PR -> main (prod).
#
# Blocks, from ANY branch, any git command that would write or delete a remote PROTECTED ref
# ('main'/'dev'), and blocks `git commit`/`git merge`/non-deletion `git push` while checked out on a
# protected branch. Deleting a remote *feature* branch is allowed (it cannot rewrite a protected
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
# The decision tokenizes the command and parses each git subcommand and its push refspecs — it does
# not substring-match the raw text — and it recurses into `bash -c "..."`/`sh -lc '...'` wrappers
# and `eval "..."`. Exit 2 blocks the call and feeds stderr back to the agent.
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
# command hidden behind `$(...)`, a `$var`, a here-string, a pipe into `bash`/`xargs`, or a script
# file whose contents are never shown to this hook is NOT fully closed off — the opaque-script check
# above only WARNS, it cannot prove the script is safe. A determined actor can still evade a
# command-string parser. Do not mistake this hook for a hard security boundary; it exists to catch
# accidental/automated main-mutations, not to stop someone who deliberately routes around it.
# If python3 is unavailable the fail-closed fallback below still catches the plain-text
# `git push`/`commit`/`merge` forms (using the same cwd-aware branch resolution, best-effort).
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
import json, os, shlex, subprocess, sys

# openproceedings: tokenize with the shared cmdparse tokenizer so unspaced `;`/`&&`, newlines, `(`/`)` and
# redirects are separate tokens (security review round 2: `if true; then git push origin HEAD:dev; fi` and
# `git push origin HEAD:dev;` read `dev;` as the ref), and compare command names by basename
# (`/usr/bin/git`).
sys.path.insert(0, os.environ.get("HOOK_LIB", ""))
from cmdparse import base as _base, is_redirect as _is_redirect, is_separator as _is_sep, tokenize as _tokenize

def _split(text):
    """Punctuation-aware tokens; separators normalised into SEPARATORS, redirect operators dropped."""
    out = []
    for t in _tokenize(text):
        if _is_sep(t):
            out.append(";")
        elif not _is_redirect(t):
            out.append(t)
    return out

HOOK_CWD = os.environ.get("HOOK_CWD") or os.getcwd()

try:
    cmd = json.loads(os.environ.get("HOOK_INPUT", "")).get("tool_input", {}).get("command", "")
except Exception:
    cmd = ""

SEPARATORS = {"&&", "||", ";", "|", "&"}  # _split() maps every separator (incl. newline, parens) to ";"
# git's own options that take a value; skip the value when hunting for the subcommand.
VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
SOURCE_CMDS = {".", "source"}  # always run a file; no -c-string form exists for these
PROTECTED = {"main", "dev"}    # branches that only a merged PR may write; extend here to add more

_branch_cache = {}


def get_branch(directory):
    """Resolve the checked-out branch of `directory` via a real `git -C`, memoized. Returns ''
    (never matches a protected branch) if the directory doesn't exist or isn't inside a git worktree — in
    that case the git call being analyzed would itself fail at runtime, so under-blocking here is
    harmless."""
    d = directory or HOOK_CWD
    if d not in _branch_cache:
        try:
            r = subprocess.run(
                ["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            _branch_cache[d] = r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            _branch_cache[d] = ""
    return _branch_cache[d]


def resolve_dir(candidate, base):
    if not candidate:
        return base
    return candidate if os.path.isabs(candidate) else os.path.normpath(os.path.join(base, candidate))


def unwrap(tok):
    """`$(git ...)` and backticks still invoke git; best-effort de-quote of a bare token."""
    return tok.strip("$(){}`\"'")


def dest_protected(refspec):
    """True if this push refspec's DESTINATION ref is a protected branch (any branch can name it)."""
    s = refspec.lstrip("+")  # a leading '+' is a force marker, not part of the ref
    dst = s.split(":", 1)[1] if ":" in s else s
    if dst.startswith("refs/"):
        dst = dst.rsplit("/", 1)[-1]
    return dst in PROTECTED


def push_verdict(args, directory):
    """Classify the args following `git push`, using the branch checked out in `directory`."""
    flags = [a for a in args if a.startswith("-")]
    positionals = [a for a in args if not a.startswith("-")]
    refspecs = positionals[1:]  # positionals[0] is the remote

    # --mirror/--all can create or delete a protected branch without ever naming it.
    if any(f in ("--mirror", "--all") for f in flags):
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
    if get_branch(directory) in PROTECTED:
        return "protected"  # ordinary push while standing on a protected branch
    return "allow"


warnings = []  # opaque-script wrappers seen along the way; only surfaced if nothing else blocks


def analyze(tokens, state):
    """Walk tokens; return the first blocking verdict, else 'allow'. Recurses into shell wrappers.
    `state["dir"]` tracks the working directory implied by any `cd <dir>` seen so far in this
    (sub)command — shared across recursive calls so a `cd` before a wrapper still applies inside it."""
    i = 0
    while i < len(tokens):
        tok = unwrap(tokens[i])

        if tok == "cd" and (i == 0 or tokens[i - 1] in SEPARATORS):
            j = i + 1
            if j < len(tokens) and tokens[j] not in SEPARATORS and not tokens[j].startswith("-"):
                state["dir"] = resolve_dir(unwrap(tokens[j]), state["dir"])
            while j < len(tokens) and tokens[j] not in SEPARATORS:
                j += 1
            i = j
            continue

        if _base(tok) in SHELLS or tok in SOURCE_CMDS:  # bash -c "..." / sh -lc '...' / . file / source file
            supports_c = _base(tok) in SHELLS
            j = i + 1
            found_c = False
            first_positional = None
            while j < len(tokens) and tokens[j] not in SEPARATORS:
                # The `-c` command flag can sit anywhere in a single-dash short cluster
                # (-c, -lc, -cl, -ic, -cx, -lic, -icl ...): all four shells run the next word as
                # the command. `c` is the only single-letter option that does this, so any
                # single-dash flag containing 'c' is the command flag. Long options that merely
                # contain 'c' (--norc, --rcfile, --noprofile) are NOT — the `--` guard excludes
                # them so the loop skips past to the real -c.
                short_c = supports_c and (
                    tokens[j] == "-c" or (
                        tokens[j].startswith("-")
                        and not tokens[j].startswith("--")
                        and "c" in tokens[j]
                    )
                )
                if short_c:
                    found_c = True
                    if j + 1 < len(tokens):
                        try:
                            inner = _split(tokens[j + 1])
                        except ValueError:
                            return "parse-fail"
                        v = analyze(inner, state)
                        if v != "allow":
                            return v
                    break
                if not tokens[j].startswith("-") and first_positional is None:
                    first_positional = unwrap(tokens[j])
                j += 1

            if not found_c and first_positional:
                # bash/sh/zsh/dash/ksh/./source <file ...>: an opaque script this parser cannot
                # see inside. Only worth flagging where a hidden commit/push/merge would matter.
                if get_branch(state["dir"]) in PROTECTED:
                    warnings.append(f"{tok} {first_positional}")

            i += 1
            continue

        if tok == "eval":  # eval joins its args and re-parses them as a command
            parts = []
            j = i + 1
            while j < len(tokens) and tokens[j] not in SEPARATORS:
                parts.append(tokens[j])
                j += 1
            try:
                inner = _split(" ".join(parts))
            except ValueError:
                return "parse-fail"
            v = analyze(inner, state)
            if v != "allow":
                return v
            i = j
            continue

        if _base(tok) != "git":
            i += 1
            continue

        # Skip git's global options to reach the subcommand, CHAINING every `-C <dir>` the way git
        # itself does (git's own semantics, and this takes priority over any `cd`): multiple `-C`
        # flags compose left-to-right — each relative `-C` is resolved against the directory the
        # PRECEDING `-C` established, an absolute `-C` resets the base. Keeping only the last value
        # and resolving it against the outer dir would mis-resolve `-C a -C ../b` and let a
        # main-worktree target slip through. The chain starts at `state["dir"]` (the `cd`/cwd base).
        effective_dir = state["dir"]
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            opt = tokens[j]
            if opt in VALUE_OPTS:
                if opt == "-C" and j + 1 < len(tokens):
                    effective_dir = resolve_dir(unwrap(tokens[j + 1]), effective_dir)
                j += 2
            else:
                j += 1
        if j >= len(tokens):
            break

        sub = tokens[j]
        args = []
        k = j + 1
        while k < len(tokens) and tokens[k] not in SEPARATORS:
            args.append(tokens[k])
            k += 1

        if sub == "push":
            v = push_verdict(args, effective_dir)
            if v != "allow":
                return v
        elif sub == "pull":
            pass  # sync carve-out: fetch + integrate into LOCAL main only; see header rationale.
        elif sub == "merge":
            # sync carve-out: a fast-forward-only merge creates no merge commit, so it's allowed on a
            # protected branch. Require --ff-only AND reject --no-ff/--ff — those OVERRIDE --ff-only and
            # would still make a merge commit (a commit on the protected branch). A plain merge is
            # likewise a commit and blocked.
            ff_sync = "--ff-only" in args and not ({"--no-ff", "--ff"} & set(args))
            if get_branch(effective_dir) in PROTECTED and not ff_sync:
                return "protected-merge"
        elif sub == "commit" and get_branch(effective_dir) in PROTECTED:
            return "protected"

        i = j + 1

    return "allow"


if not cmd:
    print("allow")
else:
    try:
        tokens = _split(cmd)
    except Exception:
        # Unbalanced quotes — bash rejects the same syntax before running, so nothing executes,
        # but hand it to the conservative shell-level fallback rather than silently allowing.
        print("parse-fail")
    else:
        result = analyze(tokens, {"dir": HOOK_CWD})
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
  case "$input" in
    *"git commit"*|*"git merge"*)
      [ "$on_protected" = 1 ] && verdict="protected" || verdict="allow" ;;
    *"git push"*)
      case "$input" in
        *" main"*|*":main"*|*"/main"*|*" dev"*|*":dev"*|*"/dev"*) verdict="protected-ref" ;;
        *) [ "$on_protected" = 1 ] && verdict="protected" || verdict="allow" ;;
      esac ;;
    *) verdict="allow" ;;
  esac
fi

case "$verdict" in
  protected)
    echo "Review gate: protected branches (main, dev) take no direct commits/pushes/merges. Open a PR:" >&2
    echo "  git switch -c <branch>" >&2
    echo "  git commit ...   &&   git push -u origin <branch>" >&2
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
    echo "  git commit ...   &&   git push -u origin <branch>" >&2
    echo "  gh pr create --base dev --fill   &&   gh pr merge --squash --delete-branch" >&2
    exit 2
    ;;
  protected-ref)
    echo "Refusing: this command would write or delete a protected remote ref (main/dev) directly." >&2
    echo "Changes reach a protected branch only through a merged pull request (gh pr merge)." >&2
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
