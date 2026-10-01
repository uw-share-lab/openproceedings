#!/usr/bin/env bash
# PreToolUse guard: Backlog.md task/doc/draft/milestone files are CLI-managed.
# Block direct Write/Edit to them so metadata, relationships, and history stay consistent.
# Reads the tool-call JSON on stdin; exit 2 blocks the call and feeds stderr back to the agent.
#
# Decisions are the one exception, and deliberately so: `backlog decision` exposes only `create`
# (title + status) — there is no `edit`, and no way to write a decision's Context/Decision/Consequences
# body through the CLI at all. Blocking Edit there enforced an impossible workflow and left decision
# records as empty stubs. So for backlog/decisions/ ONLY:
#   Write            -> still blocked  (files must be created by `backlog decision create`, which assigns id/date/status)
#   Edit / MultiEdit -> allowed        (the body has no other author)
# A path this guard can't read (an internal error, such as one that can't be encoded) is refused: exit 2, never a
# crash, which Claude Code would let through.
input=$(cat)
# Initialize explicitly: `eval` assigns nothing if the parse fails, which would otherwise let $path/$tool/$crashed
# inherit same-named vars from the environment.
path=''
tool=''
parsed=''
crashed=''
# shellcheck disable=SC2016  # single quotes are deliberate: this is Python source, not shell
eval "$(printf '%s' "$input" | python3 -c 'import json,os,sys,shlex
# Malformed JSON: emit nothing -> `parsed` stays empty -> the guard below fails closed for a backlog/ path. Any
# other error (a path that can'"'"'t be encoded) prints `crashed=1`, which is refused outright (TASK-067 final review).
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
try:
    p = d.get("tool_input", {}).get("file_path", "") or ""
    t = d.get("tool_name", "") or ""
    # Normalise before matching (TASK-067): relative to the call'"'"'s cwd, `//`, `./`, `..` and symlinks resolved,
    # lower-cased because APFS folds case (`Backlog/tasks/` is `backlog/tasks/`).
    if p:
        p = os.path.realpath(os.path.join(d.get("cwd") or os.getcwd(), p)).lower()
    print(f"path={shlex.quote(p)}; tool={shlex.quote(t)}; parsed=1")
except Exception:
    print("crashed=1")' 2>/dev/null)"

if [ -n "$crashed" ]; then
  echo "Backlog guard could not check this tool call (an internal error reading its path) — refusing." >&2
  echo "Use a plain path, or make the change with the 'backlog' CLI." >&2
  exit 2
fi

# Fail CLOSED — but only for calls that could plausibly touch backlog/. If we cannot parse the tool call
# (no python3, malformed JSON) we can't tell a permitted decision-body Edit from a forbidden task Edit, so we
# refuse. Scoping the refusal to payloads that mention a backlog path keeps a python3 outage from blocking
# every Write/Edit in the repo — this hook runs on all of them.
if [ -z "$parsed" ]; then
  case "$input" in
    *[Bb][Aa][Cc][Kk][Ll][Oo][Gg]/*)
      echo "Backlog guard could not parse this tool call (python3 missing or malformed JSON), and the call" >&2
      echo "appears to touch backlog/ — refusing. This guard fails closed by design." >&2
      echo "Fix the environment, or make the change with the 'backlog' CLI." >&2
      exit 2
      ;;
  esac
  exit 0
fi

case "$path" in   # normalised and lower-cased above
  */backlog/decisions/*)
    # Body authoring is Edit-only; creation still goes through the CLI.
    case "$tool" in Edit|MultiEdit) exit 0 ;; esac
    echo "Decision FILES are CLI-created — don't Write one directly. Create it first, then Edit the body:" >&2
    echo "  backlog decision create \"<title>\"     (assigns id / date / status frontmatter)" >&2
    echo "  then Edit the file to fill in Context / Decision / Consequences" >&2
    echo "(Edit is permitted here because the CLI cannot write a decision body — see CLAUDE.md.)" >&2
    exit 2
    ;;
  */backlog/tasks/*|*/backlog/drafts/*|*/backlog/docs/*|*/backlog/milestones/*|*/backlog/completed/*|*/backlog/archive/*|*/backlog/config.yml|*/backlog/backlog.md)
    echo "Backlog.md files are CLI-managed — do not edit them directly. Use the 'backlog' CLI instead, e.g.:" >&2
    echo "  backlog task create / edit / view      (tasks & subtasks)" >&2
    echo "  backlog doc create                      (specs / plans)" >&2
    echo "  backlog decision create                 (decisions)" >&2
    echo "Run 'backlog <command> --help' for options. This keeps metadata, relationships, and history consistent (see CLAUDE.md)." >&2
    exit 2
    ;;
esac
exit 0
