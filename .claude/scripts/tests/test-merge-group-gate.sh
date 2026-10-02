#!/usr/bin/env bash
# Case table for .claude/scripts/merge_group_gate.py, the pr-gates checks in a merge-queue build (decision-027,
# TASK-161). Builds a throwaway repo whose queue branches are real two-parent merges in the shape GitHub's
# merge queue makes with the MERGE method, and serves the PRs from a fake `gh` on PATH (REST-shaped JSON under
# $TMP/gh; a path with no file fails like gh on a 404), so no case reaches GitHub. Every gate must fail closed:
# a group it can't fully resolve is an error, never a pass, and every err row names the ::error:: it expects,
# so a row can't pass on an incidental failure.
# Usage: ./test-merge-group-gate.sh
set -u
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
GATE="$SRC/.claude/scripts/merge_group_gate.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
R="$TMP/r"
g() { git -C "$R" -c user.name=t -c user.email=t@example.org -c commit.gpgsign=false "$@"; }

# The fake gh: `gh api <path>` prints $TMP/gh/<path, / as _>.json, or fails when there is none.
mkdir -p "$TMP/bin" "$TMP/gh"
cat > "$TMP/bin/gh" <<'SH'
#!/usr/bin/env bash
[ "$1" = api ] || { echo "fake gh: only 'gh api <path>'" >&2; exit 2; }
f="$FAKE_GH/$(printf '%s' "$2" | tr '/' '_').json"
[ -f "$f" ] || { echo '{"message":"Not Found","status":"404"}'; echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
cat "$f"
SH
chmod +x "$TMP/bin/gh"

# pr <number> <head sha> <body> [labels csv] [state] [base ref] [title] — writes repos/o/r/pulls/<number>
pr() {
  python3 - "$TMP/gh/repos_o_r_pulls_$1.json" "$1" "$2" "$3" "${4:-}" "${5:-open}" "${6:-dev}" "${7:-a title}" <<'PY'
import json, sys
out, n, head, body, labels, state, base, title = sys.argv[1:]
json.dump({"number": int(n), "state": state, "title": title, "body": body,
           "base": {"ref": base}, "head": {"sha": head},
           "labels": [{"name": x} for x in labels.split(",") if x]}, open(out, "w"))
PY
}
# setpr <number> <key>=<json>... — change fields of a PR written by pr
setpr() {
  python3 - "$TMP/gh/repos_o_r_pulls_$1.json" "${@:2}" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1)
    p[k] = json.loads(v)
json.dump(p, open(sys.argv[1], "w"))
PY
}
att() { printf 'Summary\n\n<!-- op-review: %s APPROVE -->' "$1"; }   # an attested body for <sha>

# expect <ok|err:<regex>> <label> <gate> <base> <head> [head ref]
#   err:<regex> also needs an ::error:: line matching <regex> (grep -E); the ref defaults to the queue ref for $LAST
expect() {
  local want="$1" label="$2" gate="$3" base="$4" head="$5" ref="${6:-}" got rx=""
  case $want in err:*) rx="${want#err:}"; want=err ;; esac
  [ -n "$ref" ] || ref="refs/heads/gh-readonly-queue/dev/pr-$LAST-$base"
  if (cd "$R" && PATH="$TMP/bin:$PATH" FAKE_GH="$TMP/gh" python3 "$GATE" "$gate" --base "$base" --head "$head" \
        --head-ref "$ref" --repo o/r) > "$TMP/out" 2>&1; then got=ok; else got=err; fi
  if [ "$got" = err ] && [ -n "$rx" ] && ! grep -Eq "::error::.*$rx" "$TMP/out"; then got="err (other reason)"; fi
  if [ "$got" = "$want" ] && ! grep -q Traceback "$TMP/out"; then
    pass=$((pass+1)); printf '  ok   %-12s %-66s -> %s\n' "$gate" "$label" "$got"
  else fail=$((fail+1)); printf '  FAIL %-12s %-66s -> %s (want %s)\n' "$gate" "$label" "$got" "$want"; sed 's/^/       /' "$TMP/out"; fi
}

# The repo: dev, and PR branches cut from it.
git init -q -b dev "$R"
mkdir -p "$R/.claude/learnings/sub"
printf '# old\n\n**Key lesson:** k\n' > "$R/.claude/learnings/2026-01-01-old.md"
printf '# draft\n\none\ntwo\nthree\nfour\nfive\n' > "$R/.claude/learnings/draft.txt"
echo x > "$R/README.md"
g add -A && g commit -q -m init
BASE=$(g rev-parse HEAD)
branch() {  # branch <name> <commit message> <file>=<content>... — one commit on a branch from dev; prints its sha
  local name="$1" msg="$2"; shift 2
  g switch -q -c "$name" dev
  for kv in "$@"; do mkdir -p "$(dirname "$R/${kv%%=*}")"; printf '%s\n' "${kv#*=}" >> "$R/${kv%%=*}"; done
  g add -A && g commit -q -m "$msg" && g rev-parse HEAD
}
A=$(branch a "feat: a" .claude/learnings/2026-10-02-a.md="# a" a.txt=a)              # adds an entry
B=$(branch b "fix: b" .claude/learnings/2026-10-02-b.md="# b" b.txt=b)               # adds an entry
N=$(branch n "chore: no entry" n.txt=n)                                                # no entry
X=$(branch x "docs: extends an entry" .claude/learnings/2026-01-01-old.md="addendum")  # extends one
S=$(branch s "chore: entry in a subfolder" .claude/learnings/sub/2026-10-02-s.md="# s")
W=$(branch w "chore: badly named entry" .claude/learnings/2026-10-02-Upper.md="# w")
C=$(branch c "feat: c

Co-authored-by: Claude <noreply@anthropic.com>" c.txt=c)                               # attributed commit
g switch -q -c rm dev; g rm -q .claude/learnings/2026-01-01-old.md; g commit -q -m "chore: deletes an entry"; D=$(g rev-parse HEAD)
g switch -q -c mv dev; g mv .claude/learnings/draft.txt .claude/learnings/2026-01-02-moved.md
printf 'more\n' >> "$R/.claude/learnings/2026-01-02-moved.md"; g add -A; g commit -q -m "chore: renames and extends"; M=$(g rev-parse HEAD)
[ "$(g diff --name-status --find-renames dev mv | cut -c1)" = R ] || { echo "setup: mv is not a rename"; exit 1; }
g switch -q -c cut dev; printf '# old\n' > "$R/.claude/learnings/2026-01-01-old.md"; g commit -q -am "chore: only removes lines"; K=$(g rev-parse HEAD)
T=$(branch t "chore: entry with a trailing extension" .claude/learnings/2026-10-02-t.md.bak="# t")
g switch -q -c bin dev; printf 'a\000b\n' > "$R/.claude/learnings/2026-10-02-bin.md"; g add -A; g commit -q -m "chore: binary entry"; Y=$(g rev-parse HEAD)
# dev2: dev moved on after the PR branches were cut, trimming an entry (the PRs above don't have that commit)
g switch -q -c dev2 dev; printf '# old\n' > "$R/.claude/learnings/2026-01-01-old.md"; g commit -q -am "chore: dev trims an entry"; BASE2=$(g rev-parse HEAD)

# queue <name> <branch>:<number>... — a queue branch off dev with one GitHub-style merge per PR; prints its head
queue() {
  local name="$1"; shift
  g switch -q -c "$name" dev
  for bn in "$@"; do g merge -q --no-ff -m "Merge pull request #${bn#*:} from o/${bn%%:*}" "${bn%%:*}"; done
  g rev-parse HEAD
}

reset_prs() { rm -f "$TMP"/gh/*.json; }

echo "== review"
Q1=$(queue q1 a:11); LAST=11
reset_prs; pr 11 "$A" "$(att "$A")"
expect ok  "one PR, attested for its head"                                   review "$BASE" "$Q1"
Q2=$(queue q2 a:11 b:12); LAST=12
Q2FIRST=$(g rev-parse "$Q2^1")   # the group's first queue commit (q2's merge of #11)
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")"
expect ok  "two PRs, each attested for its own head"                         review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "$(att "$B")"
expect err:"#11: no review attestation" "the first PR of two has no attestation (only the head ref's is)" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$B")"; pr 12 "$B" "$(att "$B")"
expect err:"#11: no review attestation" "a PR attests another PR's head"     review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "<!-- op-review: $B REQUEST_CHANGES -->"
expect err:"#12: no review attestation" "an attestation of REQUEST_CHANGES"  review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "<!-- op-review: ${B:0:12} APPROVE -->"
expect err:"#12: no review attestation" "an attestation of an abbreviated sha" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$N" "$(att "$N")"
expect err:"#12's head is" "the PR's head moved since it was queued (attests the new head)" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")" "" closed
expect err:"wasn't merged by queue commit" "a closed, unmerged PR"           review "$BASE" "$Q2"
# An entry ahead merged before this build's jobs ran: dev moved to its queue commit, which is this group's first.
reset_prs; pr 11 "$A" "$(att "$A")" "" closed; setpr 11 merged=true "merge_commit_sha=\"$Q2FIRST\""; pr 12 "$B" "$(att "$B")"
expect ok  "the PR ahead was already merged by this group's queue commit"    review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")" "" closed; setpr 11 merged=true "merge_commit_sha=\"$Q2\""; pr 12 "$B" "$(att "$B")"
expect err:"#11 is 'closed'" "a PR merged by some other commit"              review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")" "" closed; setpr 11 merged=false "merge_commit_sha=\"$Q2FIRST\""; pr 12 "$B" "$(att "$B")"
expect err:"#11 is 'closed'" "a closed PR whose merged flag is false"        review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "Summary" "" closed; setpr 11 merged=true "merge_commit_sha=\"$Q2FIRST\""; pr 12 "$B" "$(att "$B")"
expect err:"#11: no review attestation" "a merged PR ahead is still checked" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")" "" open main
expect err:"targets 'main', not dev" "a PR that targets main"                review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"
expect err:"gh api repos/o/r/pulls/12 failed" "gh can't read a PR in the group" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; printf 'not json' > "$TMP/gh/repos_o_r_pulls_12.json"
expect err:"isn't JSON" "gh returns something that isn't JSON"               review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; printf '[1]' > "$TMP/gh/repos_o_r_pulls_12.json"
expect err:"isn't a JSON object" "gh returns JSON that isn't a PR object"    review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")"
expect err:"but the head ref names #11" "the head ref names a PR that isn't the newest in the group" review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-11-$BASE"
expect err:"is not dev's merge queue" "a head ref that isn't dev's queue (main's)" review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/main/pr-12-$BASE"
expect err:"is not dev's merge queue" "a head ref that isn't a queue ref at all" review "$BASE" "$Q2" "refs/heads/b"
expect err:"is not dev's merge queue" "a head ref with an abbreviated sha"   review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-${BASE:0:12}"
expect err:"is not dev's merge queue" "a head ref with trailing text"        review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE/x"
expect err:"holds no commits" "an empty range (head is base)"                review "$BASE" "$BASE" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE"
expect err:"full 40-character" "an abbreviated base sha"                     review "${BASE:0:12}" "$Q2"
expect err:"full 40-character" "an abbreviated head sha"                     review "$BASE" "${Q2:0:12}"
expect err:"git rev-list .* failed" "a base that doesn't exist"              review "$(printf 'f%.0s' $(seq 1 40))" "$Q2"
expect err:"first parent is not" "a base that isn't on the queue's first-parent chain" review "$A" "$Q2"
# The newest merge alone, from the previous queue commit: a group checked from the middle still checks its PRs.
expect ok  "a range from the previous queue commit (one PR)"                 review "$Q2FIRST" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-$Q2FIRST"
g switch -q -c q3 q2; echo direct >> "$R/README.md"; g commit -q -am "a direct commit"; Q3=$(g rev-parse HEAD)
expect err:"has 1 parent" "a non-merge commit in the range (squash/rebase method)" review "$BASE" "$Q3" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE"
g switch -q -c q4 dev; g merge -q --no-ff -m "Merge pull request #11 from o/a" a b >/dev/null 2>&1; Q4=$(g rev-parse HEAD)
[ "$(g rev-list --no-walk --parents "$Q4" | wc -w)" -eq 4 ] || { echo "setup: q4 is not an octopus merge"; exit 1; }
expect err:"has 3 parent" "an octopus merge (three parents)"                 review "$BASE" "$Q4" "refs/heads/gh-readonly-queue/dev/pr-11-$BASE"
# The same PR, at the same head, merged twice in one group.
Q5=$(g commit-tree -p "$Q1" -p "$A" -m "Merge pull request #11 from o/a" "$Q1^{tree}"); LAST=11
reset_prs; pr 11 "$A" "$(att "$A")"
expect err:"appears twice" "the same PR twice in one group"                  review "$BASE" "$Q5"
# A merge whose subject names no PR: the one open dev PR headed at parent 2 is looked up instead.
g switch -q -c q6 dev; g merge -q --no-ff -m "an unusual subject" a; Q6=$(g rev-parse HEAD); LAST=11
LOOKUP="$TMP/gh/repos_o_r_commits_${A}_pulls.json"
reset_prs; pr 11 "$A" "$(att "$A")"
printf '[{"number": 11, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" > "$LOOKUP"
expect ok  "an unusual merge subject resolved by the commit's one open PR"   review "$BASE" "$Q6"
printf '[]' > "$LOOKUP"
expect err:"names no PR, and 0" "an unusual merge subject and no open PR for the commit" review "$BASE" "$Q6"
printf '[{"number": 11, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}, {"number": 13, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" "$A" > "$LOOKUP"
expect err:"names no PR, and 2" "an unusual merge subject and two open PRs for the commit" review "$BASE" "$Q6"
printf '[{"number": 11, "state": "closed", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" > "$LOOKUP"
expect err:"names no PR, and 0" "an unusual merge subject and only a closed PR for the commit" review "$BASE" "$Q6"
printf '[{"number": 11, "state": "open", "base": {"ref": "main"}, "head": {"sha": "%s"}}]' "$A" > "$LOOKUP"
expect err:"names no PR, and 0" "an unusual merge subject and only a main PR for the commit" review "$BASE" "$Q6"
printf '[{"number": 11, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "0000000000000000000000000000000000000000"}}]' > "$LOOKUP"
expect err:"names no PR, and 0" "an unusual merge subject and a PR at another head" review "$BASE" "$Q6"
printf '[{"number": true, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" > "$LOOKUP"
expect err:"names no PR, and 1" "an unusual merge subject and a PR number that isn't an int" review "$BASE" "$Q6"
printf '{"number": 11}' > "$LOOKUP"
expect err:"aren't a list" "an unusual merge subject and a lookup that isn't a list" review "$BASE" "$Q6"
rm -f "$LOOKUP"
g switch -q -c q18 dev; g merge -q --no-ff -m "Revert \"Merge pull request #11 from o/a\"" a; Q18=$(g rev-parse HEAD)
expect err:"gh api repos/o/r/commits/.* failed" "a subject that only contains a merge subject is not one" review "$BASE" "$Q18"

echo "== learnings"
Q7=$(queue q7 a:11 n:12); LAST=12
reset_prs; pr 11 "$A" ""; pr 12 "$N" ""
expect err:"#12: no added or extended" "the second PR adds no entry (the first PR's doesn't count)" learnings "$BASE" "$Q7"
Q19=$(queue q19 n:11 a:12)
reset_prs; pr 11 "$N" ""; pr 12 "$A" ""
expect err:"#11: no added or extended" "the first PR adds no entry (the head ref's PR does)" learnings "$BASE" "$Q19"
reset_prs; pr 11 "$A" ""; pr 12 "$N" "" no-learning
expect ok  "the PR without an entry is labelled no-learning"                 learnings "$BASE" "$Q7"
reset_prs; pr 11 "$A" ""; pr 12 "$N" "" other-label,no-learnings
expect err:"#12: no added or extended" "a label that only resembles no-learning" learnings "$BASE" "$Q7"
reset_prs; pr 11 "$A" ""; pr 12 "$N" ""; setpr 12 'labels="no-learning"'
expect err:"labels aren't a list" "labels that aren't a list"                learnings "$BASE" "$Q7"
Q8=$(queue q8 a:11 b:12)
reset_prs; pr 11 "$A" ""; pr 12 "$B" ""; setpr 12 'labels="x"'
expect err:"labels aren't a list" "labels that aren't a list, on a PR with an entry" learnings "$BASE" "$Q8"
reset_prs; pr 11 "$A" ""; pr 12 "$B" ""
expect ok  "each PR adds its own entry"                                      learnings "$BASE" "$Q8"
Q9=$(queue q9 x:12)
reset_prs; pr 12 "$X" ""
expect ok  "a PR that extends an existing entry"                             learnings "$BASE" "$Q9"
Q10=$(queue q10 rm:12)
reset_prs; pr 12 "$D" ""
expect err:"#12: no added or extended" "a PR that only deletes an entry"     learnings "$BASE" "$Q10"
Q11=$(queue q11 s:12)
reset_prs; pr 12 "$S" ""
expect err:"#12: no added or extended" "an entry in a subfolder"             learnings "$BASE" "$Q11"
Q12=$(queue q12 w:12)
reset_prs; pr 12 "$W" ""
expect err:"#12: no added or extended" "an entry with an uppercase slug"     learnings "$BASE" "$Q12"
Q13=$(queue q13 mv:12)
reset_prs; pr 12 "$M" ""
expect ok  "a non-entry renamed to an entry and extended"                    learnings "$BASE" "$Q13"
reset_prs; pr 12 "$N" "" no-learning
expect err:"#12's head is" "a learnings check of a PR whose head moved still fails" learnings "$BASE" "$Q13"
Q16=$(queue q16 cut:12)
reset_prs; pr 12 "$K" ""
expect err:"#12: no added or extended" "a PR that only removes lines from an entry" learnings "$BASE" "$Q16"
Q17=$(queue q17 t:12)
reset_prs; pr 12 "$T" ""
expect err:"#12: no added or extended" "an entry name with a trailing extension" learnings "$BASE" "$Q17"
Q20=$(queue q20 bin:12)
reset_prs; pr 12 "$Y" ""
expect err:"#12: no added or extended" "a binary entry (numstat '-') adds no lines" learnings "$BASE" "$Q20"
# The PR's own diff, from its merge base: a PR cut before dev trimmed an entry is not credited with the old lines.
g switch -q -c q21 dev2; g merge -q --no-ff -m "Merge pull request #12 from o/n" n; Q21=$(g rev-parse HEAD)
reset_prs; pr 12 "$N" ""
expect err:"#12: no added or extended" "dev trimmed an entry after the PR branched" learnings "$BASE2" "$Q21"

echo "== attribution"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "Summary"
expect ok  "clean commits, titles and bodies"                                attribution "$BASE" "$Q8"
Q14=$(queue q14 a:11 c:12)
reset_prs; pr 11 "$A" "Summary"; pr 12 "$C" "Summary"
expect err:"a commit message in the group" "a co-author trailer in a queued PR's commit" attribution "$BASE" "$Q14"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
expect err:"#12: the PR title/body" "a generated-with footer in the second PR's body" attribution "$BASE" "$Q8"
reset_prs; pr 11 "$A" "Summary" "" open dev "Generated with Claude"; pr 12 "$B" "Summary"
expect err:"#11: the PR title/body" "attribution in the first PR's title"   attribution "$BASE" "$Q8"
reset_prs; pr 11 "$A" "co-authored-by: CLAUDE"; pr 12 "$B" "Summary"
expect err:"#11: the PR title/body" "attribution in another case"           attribution "$BASE" "$Q8"
g switch -q -c q15 dev; g merge -q --no-ff -m "Merge pull request #11 from o/a

Co-authored-by: Claude <noreply@anthropic.com>" a; Q15=$(g rev-parse HEAD); LAST=11
reset_prs; pr 11 "$A" "Summary"
expect err:"a commit message in the group" "attribution in the queue's merge commit message" attribution "$BASE" "$Q15"
reset_prs; pr 11 "$A" "Summary"; setpr 11 body=null
expect ok  "a PR with an empty (null) body"                                  attribution "$BASE" "$Q1"
reset_prs; pr 11 "$A" "Summary"; setpr 11 'body=["x"]'
expect err:"body isn't a string" "a body that isn't a string"                attribution "$BASE" "$Q1"
reset_prs
expect err:"gh api repos/o/r/pulls/11 failed" "gh can't read the PR"         attribution "$BASE" "$Q1"
# No gh on PATH at all: an ::error::, not a traceback (git only, by symlink; python3 by absolute path).
mkdir -p "$TMP/nogh" && ln -sf "$(command -v git)" "$TMP/nogh/git"
PY3="$(command -v python3)"
if (cd "$R" && PATH="$TMP/nogh" "$PY3" "$GATE" attribution --base "$BASE" --head "$Q1" \
      --head-ref "refs/heads/gh-readonly-queue/dev/pr-11-$BASE" --repo o/r) > "$TMP/out" 2>&1; then got=ok; else got=err; fi
if [ "$got" = err ] && grep -q "::error::.*could not run gh" "$TMP/out" && ! grep -q Traceback "$TMP/out"; then
  pass=$((pass+1)); printf '  ok   %-12s %-66s -> %s\n' attribution "gh missing from PATH" err
else fail=$((fail+1)); printf '  FAIL %-12s %-66s -> %s\n' attribution "gh missing from PATH" "$got"; sed 's/^/       /' "$TMP/out"; fi

echo "== pr-gates.yml and test.yml wiring"
# The workflow side of the gate, read as text (no YAML parser on the runner's python3): each pr-gates job refuses
# an unknown event first, runs its own merge_group_gate.py gate on merge_group with the event's three fields, and
# runs every pull_request step only on pull_request; every required check's workflow triggers on merge_group.
wiring() {
  python3 - "$SRC/.github/workflows" <<'PY'
import re, sys
from pathlib import Path
wf = Path(sys.argv[1])
errs = []
for name in ("lint", "test", "claude-tooling", "pr-gates"):
    on = (wf / f"{name}.yml").read_text().split("\npermissions:", 1)[0]
    if not re.search(r"\n  merge_group:", on):
        errs.append(f"{name}.yml: no merge_group trigger")
if "github.event.merge_group.base_sha" not in (wf / "test.yml").read_text():
    errs.append("test.yml: no merge_group base for the OpenAPI baseline")
text = (wf / "pr-gates.yml").read_text()
jobs = dict(re.findall(r"\n  ([a-z-]+):\n(.*?)(?=\n  [a-z-]+:\n|\Z)", "\n" + text.split("\njobs:\n", 1)[1], re.S))
for job, gate in (("attribution", "attribution"), ("learnings", "learnings"), ("review-attested", "review")):
    steps = (jobs.get(job) or "").split("\n      - ")[1:]
    if not steps or "Refuse an event" not in steps[0] or "!= 'pull_request' && github.event_name != 'merge_group'" not in steps[0] or "exit 1" not in steps[0]:
        errs.append(f"{job}: the first step doesn't refuse other events")
    runs = [s for s in steps if "merge_group_gate.py" in s]
    if len(runs) != 1 or f"merge_group_gate.py {gate} " not in runs[0]:
        errs.append(f"{job}: not exactly one step running merge_group_gate.py {gate}")
    for s in runs:
        for need in ("if: github.event_name == 'merge_group'", "GH_TOKEN: ${{ github.token }}",
                     "BASE_SHA: ${{ github.event.merge_group.base_sha }}", "HEAD_SHA: ${{ github.event.merge_group.head_sha }}",
                     "HEAD_REF: ${{ github.event.merge_group.head_ref }}",
                     '--base "$BASE_SHA" --head "$HEAD_SHA" --head-ref "$HEAD_REF" --repo "$REPO"'):
            if need not in s:
                errs.append(f"{job}: the merge_group step lacks {need}")
    for s in steps:
        if "github.event.pull_request" in s and "github.event_name == 'pull_request'" not in s:
            errs.append(f"{job}: a pull_request step runs on other events")
    # A skipped job satisfies a required check, so a job-level if: may only be the dev -> main promotion exemption.
    job_if = re.findall(r"^    if: (.*)$", jobs.get(job) or "", re.M)
    exempt = "${{ !(github.head_ref == 'dev' && github.base_ref == 'main' && github.event.pull_request.head.repo.full_name == github.repository) }}"
    if any(cond != exempt for cond in job_if):
        errs.append(f"{job}: a job-level if: other than the promotion exemption")
    if "pull-requests: read" not in (jobs.get(job) or ""):
        errs.append(f"{job}: no pull-requests: read")
print("\n".join(errs))
sys.exit(1 if errs else 0)
PY
}
if out=$(wiring 2>&1); then pass=$((pass+1)); echo "  ok   wiring       pr-gates, test, lint and claude-tooling are wired for merge_group"
else fail=$((fail+1)); echo "  FAIL wiring       $out"; fi

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
