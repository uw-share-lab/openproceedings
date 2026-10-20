#!/usr/bin/env bash
# Case table for what the default branch steers (decision-052, TASK-271). GitHub reads .github/dependabot.yml
# and every `schedule:` workflow from the default branch (`main`), so: every Dependabot ecosystem targets dev;
# every nightly job but `resolve` needs `resolve` and checks out the one sha it outputs; and `resolve`'s script,
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
entries = re.split(r"\n  - package-ecosystem: ", text)[1:]
errs = [] if entries else ["no updates entries"]
for e in entries:
    name = e.split("\n", 1)[0]
    if not re.search(r"^    target-branch: dev$", e, re.M):
        errs.append(f"{name}: no `target-branch: dev`")
print("\n".join(errs))
sys.exit(1 if errs else 0)
PY
}
echo "== dependabot.yml"
out=$(dependabot 2>&1)
check "every ecosystem targets dev" $? "$out"

echo "== nightly.yml"
# The resolve job's script, extracted for the run rows below.
python3 - "$SRC/.github/workflows/nightly.yml" "$TMP/resolve.sh" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
m = re.search(r"\n  resolve:\n(.*?)(?=\n  [a-z-]+:\n)", text, re.S)
body = m.group(1).split("        run: |\n", 1)[1] if m and "        run: |\n" in m.group(1) else "exit 99\n"
lines = []
for line in body.splitlines():
    if not line.startswith(" " * 10):
        break
    lines.append(line[10:])
open(sys.argv[2], "w").write("\n".join(lines) + "\n")
PY
nightly() {
  python3 - "$SRC/.github/workflows/nightly.yml" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
jobs = dict(re.findall(r"\n  ([a-z-]+):\n(.*?)(?=\n  [a-z-]+:\n|\Z)", "\n" + text.split("\njobs:\n", 1)[1], re.S))
errs = []
r = jobs.get("resolve", "")
if not r:
    errs.append("no resolve job")
if "permissions: {}" not in r or "sha: ${{ steps.sha.outputs.sha }}" not in r:
    errs.append("resolve: not permissions: {} with the sha output")
if re.search(r"^    if: |continue-on-error", r, re.M):
    errs.append("resolve: a job-level if: or continue-on-error")
for need in ('EVENT: "${{ github.event_name }}"', 'REPO: "${{ github.repository }}"', 'SHA: "${{ github.sha }}"'):
    if need not in r:
        errs.append(f"resolve: lacks {need}")
for name, body in jobs.items():
    if name == "resolve":
        continue
    if not re.search(r"^    needs: resolve$", body, re.M):
        errs.append(f"{name}: doesn't need resolve")
    checkouts = re.findall(r"- uses: actions/checkout@[0-9a-f]{40}[^\n]*\n        with: ([^\n]*)", body)
    if not checkouts or len(checkouts) != body.count("actions/checkout@"):
        errs.append(f"{name}: a checkout without a with: line")
    for w in checkouts:
        if 'ref: "${{ needs.resolve.outputs.sha }}"' not in w:
            errs.append(f"{name}: a checkout not pinned to resolve's sha")
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
cat > "$TMP/bin/git" <<EOF
#!/bin/sh
echo "\$*" > "$TMP/git-args"
[ "\$1" = ls-remote ] && [ "\$3" = refs/heads/dev ] && printf '%s\trefs/heads/dev\n' "$DEV"
EOF
chmod +x "$TMP/bin/git"
run() {  # run <event> <sha> — prints "rc=<n> sha=<output>"
  : > "$TMP/out"; : > "$TMP/summary"
  env -i PATH="$TMP/bin:/usr/bin:/bin" EVENT="$1" REPO=uw-share-lab/openproceedings SHA="$2" \
    GITHUB_OUTPUT="$TMP/out" GITHUB_STEP_SUMMARY="$TMP/summary" bash "$TMP/resolve.sh" >/dev/null 2>&1
  printf 'rc=%s %s' "$?" "$(cat "$TMP/out")"
}
got=$(run schedule "$DISP")
if [ "$got" = "rc=0 sha=$DEV" ] && grep -q "$DEV" "$TMP/summary" && [ "$(cat "$TMP/git-args")" = "ls-remote https://github.com/uw-share-lab/openproceedings refs/heads/dev" ]; then ok=0; else ok=1; fi
check "schedule: dev's head, from ls-remote, in the summary" "$ok" "$got"
rm -f "$TMP/git-args"
got=$(run workflow_dispatch "$DISP")
if [ "$got" = "rc=0 sha=$DISP" ] && [ ! -e "$TMP/git-args" ]; then ok=0; else ok=1; fi
check "dispatch: the dispatched sha, no ls-remote" "$ok" "$got"
got=$(run workflow_dispatch "2222")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "a short sha is refused" "$ok" "$got"
got=$(run workflow_dispatch "$DISP
3333333333333333333333333333333333333333")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "two shas are refused" "$ok" "$got"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/git"
got=$(run schedule "$DISP")
if [ "$got" = "rc=1 " ]; then ok=0; else ok=1; fi
check "schedule: no dev head is refused" "$ok" "$got"

echo "passed: $pass  failed: $fail"
[ "$fail" = 0 ]
