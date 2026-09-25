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
input=$(cat)
# Initialize explicitly: `eval` assigns nothing if the parse fails, which would otherwise let $path/$tool
# inherit same-named vars from the environment.
path=''
tool=''
parsed=''
eval "$(printf '%s' "$input" | python3 -c 'import json,sys,shlex
# Emit nothing on failure -> `parsed` stays empty -> the guard below fails closed.
d = json.load(sys.stdin)
p = d.get("tool_input", {}).get("file_path", "") or ""
t = d.get("tool_name", "") or ""
print(f"path={shlex.quote(p)}; tool={shlex.quote(t)}; parsed=1")' 2>/dev/null)"

# Fail CLOSED — but only for calls that could plausibly touch backlog/. If we cannot parse the tool call
# (no python3, malformed JSON) we can't tell a permitted decision-body Edit from a forbidden task Edit, so we
# refuse. Scoping the refusal to payloads that mention a backlog path keeps a python3 outage from blocking
# every Write/Edit in the repo — this hook runs on all of them.
if [ -z "$parsed" ]; then
  case "$input" in
    */backlog/*)
      echo "Backlog guard could not parse this tool call (python3 missing or malformed JSON), and the call" >&2
      echo "appears to touch backlog/ — refusing. This guard fails closed by design." >&2
      echo "Fix the environment, or make the change with the 'backlog' CLI." >&2
      exit 2
      ;;
  esac
  exit 0
fi

case "$path" in
  */backlog/decisions/*)
    # Body authoring is Edit-only; creation still goes through the CLI.
    case "$tool" in Edit|MultiEdit) exit 0 ;; esac
    echo "Decision FILES are CLI-created — don't Write one directly. Create it first, then Edit the body:" >&2
    echo "  backlog decision create \"<title>\"     (assigns id / date / status frontmatter)" >&2
    echo "  then Edit the file to fill in Context / Decision / Consequences" >&2
    echo "(Edit is permitted here because the CLI cannot write a decision body — see CLAUDE.md.)" >&2
    exit 2
    ;;
  */backlog/tasks/*|*/backlog/drafts/*|*/backlog/docs/*|*/backlog/milestones/*|*/backlog/completed/*|*/backlog/archive/*|*/backlog/config.yml|*/backlog/Backlog.md)
    echo "Backlog.md files are CLI-managed — do not edit them directly. Use the 'backlog' CLI instead, e.g.:" >&2
    echo "  backlog task create / edit / view      (tasks & subtasks)" >&2
    echo "  backlog doc create                      (specs / plans)" >&2
    echo "  backlog decision create                 (decisions)" >&2
    echo "Run 'backlog <command> --help' for options. This keeps metadata, relationships, and history consistent (see CLAUDE.md)." >&2
    exit 2
    ;;
esac
exit 0
