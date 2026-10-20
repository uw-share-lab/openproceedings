#!/usr/bin/env bash
# Case table for what the default branch steers (decision-052, TASK-271). GitHub reads .github/dependabot.yml
# and every `schedule:` workflow from the default branch (`main`), so: every Dependabot ecosystem targets dev;
# every nightly job but `resolve` needs `resolve` (`needs: resolve` or a flow list naming it) and checks out the one sha it outputs; and `resolve`'s script,
# run here with a fake `git` (no network), gives dev's head on a schedule, the dispatched sha otherwise, and
# refuses anything but a 40-hex sha. Read as text (no YAML parser on the runner's python3).
# Mutants in .claude/scripts/mutants/default-branch.json. Usage: ./test-default-branch.sh
# mutate-scope: .github/dependabot.yml .github/workflows/nightly.yml
set -u
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0

check() {  # check <label> <python exit status> <output>
  if [ "$2" = 0 ]; then pass=$((pass+1)); printf '  ok   %s\n' "$1"
  else fail=$((fail+1)); printf '  FAIL %s: %s\n' "$1" "$3"; fi
}

dependabot() {
  python3 - "$SRC/.github/dependabot.yml" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
updates = text.split("\nupdates:\n", 1)[1] if "\nupdates:\n" in text else ""
updates = re.split(r"\n(?=[^ \n#])", updates, maxsplit=1)[0]  # up to the next top-level key
# every list item, whatever key it starts with: its first line re-indented like the rest of its keys
items = ["    " + i for i in re.split(r"\n  - ", "\n" + updates)[1:]]
errs = [] if items else ["no updates entries"]
if text.count("package-ecosystem") != len(items):
    errs.append(f"{text.count('package-ecosystem')} package-ecosystem keys but {len(items)} block-style items")
for item in items:
    name = re.search(r"^    package-ecosystem: (.*)$", item, re.M)
    if item.lstrip().startswith("{") or not name:
        errs.append(f"an entry not in block style with a package-ecosystem: {item.strip()[:40]!r}")
    elif [ln for ln in item.split("\n") if re.match(r"    \S", ln) and not re.match(r"    [a-z-]+:( |$)", ln)]:
        errs.append(f"{name.group(1)}: a key that isn't plain `key:` (quoted or spaced)")
    elif len(keys := re.findall(r"^    ([\w-]+):", item, re.M)) != len(set(keys)):
        errs.append(f"{name.group(1)}: a repeated key")
    elif not re.search(r"^    target-branch: dev$", item, re.M):
        errs.append(f"{name.group(1)}: no `target-branch: dev`")
print("\n".join(errs))
sys.exit(1 if errs else 0)
PY
}
echo "== dependabot.yml"
out=$(dependabot 2>&1)
check "every ecosystem targets dev" $? "$out"

echo "== nightly.yml"
# Jobs are split at every line indented exactly two spaces under `jobs:` (a header the reader can't parse is an
# error, never folded into the job above), up to the next top-level key.
cat > "$TMP/jobs.py" <<'PY'
import re
def jobs(text, errs):
    body = text.split("\njobs:\n", 1)[1] if "\njobs:\n" in text else ""
    body = re.split(r"\n(?=[^ \n#])", body, maxsplit=1)[0]
    lines = body.split("\n")
    heads = [i for i, line in enumerate(lines) if re.match(r"  [^ #\n]", line)]
    out = {}
    for k, i in enumerate(heads):
        m = re.fullmatch(r"  ([A-Za-z0-9_-]+):( +#.*)?", lines[i])
        if not m or m.group(1) in out:
            errs.append(f"unreadable or repeated job header: {lines[i]!r}")
            continue
        out[m.group(1)] = "\n".join(lines[i + 1 : heads[k + 1] if k + 1 < len(heads) else len(lines)])
    return out
PY
# The resolve job's script, extracted for the run rows below.
python3 - "$SRC/.github/workflows/nightly.yml" "$TMP/resolve.sh" "$TMP" <<'PY'
import sys
sys.path.insert(0, sys.argv[3])
from jobs import jobs
r = jobs(open(sys.argv[1]).read(), []).get("resolve", "")
body = r.split("        run: |\n", 1)[1] if "        run: |\n" in r else "exit 99\n"
lines = []
for line in body.splitlines():
    if not line.startswith(" " * 10):
        break
    lines.append(line[10:])
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
PY
nightly() {
  python3 - "$SRC/.github/workflows/nightly.yml" "$TMP" <<'PY'
import re, sys
sys.path.insert(0, sys.argv[2])
from jobs import jobs
errs = []
found = jobs(open(sys.argv[1]).read(), errs)
r = found.get("resolve", "")
if not r:
    errs.append("no resolve job")
if not re.search(r"^    permissions: \{\}$", r, re.M) or not re.search(r"^      sha: \$\{\{ steps\.sha\.outputs\.sha \}\}$", r, re.M):
    errs.append("resolve: not permissions: {} with the sha output")
# one step, the one the output reads, and nothing that can skip it or ignore its failure
if len(re.findall(r"^      - ", r, re.M)) != 1 or not re.search(r"^      - id: sha$", r, re.M):
    errs.append("resolve: not exactly one step, `- id: sha`")
if re.search(r"^ +if:|continue-on-error", r, re.M):
    errs.append("resolve: an if: or continue-on-error")
# the step is env + run and nothing else (an explicit shell:, even bash, is refused); the check itself is POSIX, and
# the run rows below run it under sh too, so a `defaults:` shell can't skip it either
if re.findall(r"^        ([\w-]+):", r, re.M) != ["env", "run"]:
    errs.append("resolve: its step's keys aren't exactly env and run (GitHub's default bash)")
if not re.search(r'^        env: \{ EVENT: "\$\{\{ github\.event_name \}\}", REPO: "\$\{\{ github\.repository \}\}", SHA: "\$\{\{ github\.sha \}\}" \}$', r, re.M):
    errs.append("resolve: its env isn't EVENT, REPO and SHA from the event")
pinned = '        with: { ref: "${{ needs.resolve.outputs.sha }}", persist-credentials: false }'
for name, body in found.items():
    if name == "resolve":
        continue
    if not re.search(r"^    needs: (resolve|\[\s*(.+,\s*)?resolve(\s*,.+)?\s*\])$", body, re.M):  # scalar or flow list
        errs.append(f"{name}: doesn't need resolve")
    if re.search(r"^    if:", body, re.M):  # e.g. always(): it would run with resolve failed, an empty ref, main
        errs.append(f"{name}: a job-level if:")
    lines = body.split("\n")
    uses = [i for i, line in enumerate(lines) if "actions/checkout@" in line]
    if not uses:
        errs.append(f"{name}: no checkout")
    for i in uses:
        if not re.fullmatch(r"      - uses: actions/checkout@[0-9a-f]{40} # v[0-9.]+", lines[i]) or i + 1 >= len(lines) or lines[i + 1] != pinned:
            errs.append(f"{name}: a checkout not pinned to resolve's sha: {lines[i].strip()}")
print("\n".join(errs))
sys.exit(1 if errs else 0)
PY
}
out=$(nightly 2>&1)
check "every job needs resolve and checks out its sha" $? "$out"

# resolve's script, run: a fake git answers ls-remote with dev's head (and records what it was asked).
mkdir -p "$TMP/bin"
DEV=1111111111111111111111111111111111111111
DISP=2222222222222222222222222222222222222222

run() {  # run <event> <sha> — prints "rc=<n> sha=<output>", under $SHELL_UNDER_TEST (bash, then sh)
  : > "$TMP/out"; : > "$TMP/summary"
  env -i PATH="$TMP/bin:/usr/bin:/bin" EVENT="$1" REPO=uw-share-lab/openproceedings SHA="$2" \
    GITHUB_OUTPUT="$TMP/out" GITHUB_STEP_SUMMARY="$TMP/summary" "$SHELL_UNDER_TEST" -e "$TMP/resolve.sh" >/dev/null 2>&1
  printf 'rc=%s %s' "$?" "$(cat "$TMP/out")"
}
shells="bash sh"; command -v dash >/dev/null && shells="$shells dash"  # macOS's sh is bash; CI's is dash
for SHELL_UNDER_TEST in $shells; do  # GitHub runs `run:` under bash; a `shell: sh` or `defaults:` would be dash
cat > "$TMP/bin/git" <<EOF
#!/bin/sh
echo "\$*" > "$TMP/git-args"
[ "\$1" = ls-remote ] && [ "\$3" = refs/heads/dev ] && printf '%s\trefs/heads/dev\n' "$DEV"
EOF
chmod +x "$TMP/bin/git"
got=$(run schedule "$DISP")
if [ "$got" = "rc=0 sha=$DEV" ] && grep -q "$DEV" "$TMP/summary" && [ "$(cat "$TMP/git-args")" = "ls-remote https://github.com/uw-share-lab/openproceedings refs/heads/dev" ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: schedule: dev's head, from ls-remote, in the summary" "$ok" "$got"
rm -f "$TMP/git-args"
got=$(run workflow_dispatch "$DISP")
if [ "$got" = "rc=0 sha=$DISP" ] && [ ! -e "$TMP/git-args" ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: dispatch: the dispatched sha, no ls-remote" "$ok" "$got"
got=$(run workflow_dispatch "2222")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: a short sha is refused" "$ok" "$got"
got=$(run workflow_dispatch "$DISP
3333333333333333333333333333333333333333")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: two shas are refused" "$ok" "$got"
got=$(run workflow_dispatch "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: a 40-character non-hex value is refused" "$ok" "$got"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/git"
got=$(run schedule "$DISP")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "$SHELL_UNDER_TEST: schedule: no dev head is refused" "$ok" "$got"

done

echo "passed: $pass  failed: $fail"
[ "$fail" = 0 ]
