#!/usr/bin/env bash
# Case table for .claude/scripts/merge_group_gate.py, the pr-gates checks in a merge-queue build (decision-030,
# TASK-161). Builds a throwaway repo whose queue branches are real two-parent merges in the shape GitHub's
# merge queue makes with the MERGE method, and serves the PRs from a fake `gh` on PATH (REST-shaped JSON under
# $TMP/gh; a path with no file fails like a 404), so no case reaches GitHub. Every gate must fail closed:
# a group it can't fully resolve is an error, never a pass.
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
[ -f "$f" ] || { echo "HTTP 404: Not Found ($2)" >&2; exit 1; }
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
att() { printf 'Summary\n\n<!-- op-review: %s APPROVE -->' "$1"; }   # an attested body for <sha>

# expect <ok|err> <label> <gate> <base> <head> [head ref]   — the ref defaults to the queue ref for the last PR
expect() {
  local want="$1" label="$2" gate="$3" base="$4" head="$5" ref="${6:-}" got
  [ -n "$ref" ] || ref="refs/heads/gh-readonly-queue/dev/pr-$LAST-$base"
  if (cd "$R" && PATH="$TMP/bin:$PATH" FAKE_GH="$TMP/gh" python3 "$GATE" "$gate" --base "$base" --head "$head" \
        --head-ref "$ref" --repo o/r) > "$TMP/out" 2>&1; then got=ok; else got=err; fi
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
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")"
expect ok  "two PRs, each attested for its own head"                         review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "$(att "$B")"
expect err "the first PR of two has no attestation (only the head ref's is)" review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$B")"; pr 12 "$B" "$(att "$B")"
expect err "a PR attests another PR's head"                                  review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "<!-- op-review: $B REQUEST_CHANGES -->"
expect err "an attestation of REQUEST_CHANGES"                               review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "<!-- op-review: ${B:0:12} APPROVE -->"
expect err "an attestation of an abbreviated sha"                            review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$N" "$(att "$N")"
expect err "the PR's head moved since it was queued (attests the new head)"  review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")" "" closed
expect err "a closed PR"                                                     review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")" "" open main
expect err "a PR that targets main"                                          review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"
expect err "gh can't read a PR in the group (fails closed)"                  review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; printf 'not json' > "$TMP/gh/repos_o_r_pulls_12.json"
expect err "gh returns something that isn't JSON"                            review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; printf '[1]' > "$TMP/gh/repos_o_r_pulls_12.json"
expect err "gh returns JSON that isn't a PR object"                          review "$BASE" "$Q2"
reset_prs; pr 11 "$A" "$(att "$A")"; pr 12 "$B" "$(att "$B")"
expect err "the head ref names a PR that isn't the newest in the group"      review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-11-$BASE"
expect err "a head ref that isn't dev's queue (main's)"                      review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/main/pr-12-$BASE"
expect err "a head ref that isn't a queue ref at all"                        review "$BASE" "$Q2" "refs/heads/b"
expect err "a head ref with an abbreviated sha"                              review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-${BASE:0:12}"
expect err "a head ref with trailing text"                                   review "$BASE" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE/x"
expect err "an empty range (head is base)"                                   review "$BASE" "$BASE" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE"
expect err "an abbreviated base sha"                                         review "${BASE:0:12}" "$Q2"
expect err "a base that doesn't exist"                                       review "$(printf 'f%.0s' $(seq 1 40))" "$Q2"
Q1HEAD=$(g rev-parse q1)
expect err "a base that isn't on the queue's first-parent chain"             review "$A" "$Q2"
# The newest merge alone, from the previous queue commit: a group checked from the middle still checks its PRs.
expect ok  "a range from the previous queue commit (one PR)"                 review "$Q1HEAD" "$Q2" "refs/heads/gh-readonly-queue/dev/pr-12-$Q1HEAD"
g switch -q -c q3 q2; echo direct >> "$R/README.md"; g commit -q -am "a direct commit"; Q3=$(g rev-parse HEAD)
expect err "a non-merge commit in the range (squash/rebase method)"          review "$BASE" "$Q3" "refs/heads/gh-readonly-queue/dev/pr-12-$BASE"
g switch -q -c q4 dev; g merge -q --no-ff -m "Merge pull request #11 from o/a" a b >/dev/null 2>&1; Q4=$(g rev-parse HEAD)
[ "$(g rev-list --no-walk --parents "$Q4" | wc -w)" -eq 4 ] || { echo "setup: q4 is not an octopus merge"; exit 1; }
expect err "an octopus merge (three parents)"                                review "$BASE" "$Q4" "refs/heads/gh-readonly-queue/dev/pr-11-$BASE"
Q5=$(queue q5 a:11 b:11)
reset_prs; pr 11 "$B" "$(att "$A") $(att "$B")"; LAST=11
expect err "the same PR number twice in one group"                           review "$BASE" "$Q5"
# A merge whose subject names no PR: the one open dev PR headed at parent 2 is looked up instead.
g switch -q -c q6 dev; g merge -q --no-ff -m "an unusual subject" a; Q6=$(g rev-parse HEAD); LAST=11
reset_prs; pr 11 "$A" "$(att "$A")"
printf '[{"number": 11, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect ok  "an unusual merge subject resolved by the commit's one open PR"   review "$BASE" "$Q6"
printf '[]' > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect err "an unusual merge subject and no open PR for the commit"          review "$BASE" "$Q6"
printf '[{"number": 11, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}, {"number": 13, "state": "open", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" "$A" > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect err "an unusual merge subject and two open PRs for the commit"        review "$BASE" "$Q6"
printf '[{"number": 11, "state": "closed", "base": {"ref": "dev"}, "head": {"sha": "%s"}}]' "$A" > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect err "an unusual merge subject and only a closed PR for the commit"    review "$BASE" "$Q6"
printf '[{"number": 11, "state": "open", "base": {"ref": "main"}, "head": {"sha": "%s"}}]' "$A" > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect err "an unusual merge subject and only a main PR for the commit"      review "$BASE" "$Q6"
printf '{"number": 11}' > "$TMP/gh/repos_o_r_commits_${A}_pulls.json"
expect err "an unusual merge subject and a lookup that isn't a list"         review "$BASE" "$Q6"

echo "== learnings"
Q7=$(queue q7 a:11 n:12); LAST=12
reset_prs; pr 11 "$A" ""; pr 12 "$N" ""
expect err "the second PR adds no entry (the first PR's doesn't count)"      learnings "$BASE" "$Q7"
reset_prs; pr 11 "$A" ""; pr 12 "$N" "" no-learning
expect ok  "the PR without an entry is labelled no-learning"                 learnings "$BASE" "$Q7"
reset_prs; pr 11 "$A" ""; pr 12 "$N" "" other-label,no-learnings
expect err "a label that only resembles no-learning"                         learnings "$BASE" "$Q7"
reset_prs; pr 11 "$A" ""; pr 12 "$N" ""; python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); p["labels"]="no-learning"; json.dump(p, open(sys.argv[1],"w"))' "$TMP/gh/repos_o_r_pulls_12.json"
expect err "labels that aren't a list"                                       learnings "$BASE" "$Q7"
Q8=$(queue q8 a:11 b:12)
reset_prs; pr 11 "$A" ""; pr 12 "$B" ""
expect ok  "each PR adds its own entry"                                      learnings "$BASE" "$Q8"
Q9=$(queue q9 x:12)
reset_prs; pr 12 "$X" ""
expect ok  "a PR that extends an existing entry"                             learnings "$BASE" "$Q9"
Q10=$(queue q10 rm:12)
reset_prs; pr 12 "$D" ""
expect err "a PR that only deletes an entry"                                 learnings "$BASE" "$Q10"
Q11=$(queue q11 s:12)
reset_prs; pr 12 "$S" ""
expect err "an entry in a subfolder"                                         learnings "$BASE" "$Q11"
Q12=$(queue q12 w:12)
reset_prs; pr 12 "$W" ""
expect err "an entry with an uppercase slug"                                 learnings "$BASE" "$Q12"
Q13=$(queue q13 mv:12)
reset_prs; pr 12 "$M" ""
expect ok  "a non-entry renamed to an entry and extended"                    learnings "$BASE" "$Q13"
reset_prs; pr 12 "$N" "" no-learning
expect err "a learnings check of a PR whose head moved still fails"          learnings "$BASE" "$Q13"

Q16=$(queue q16 cut:12)
reset_prs; pr 12 "$K" ""
expect err "a PR that only removes lines from an entry"                     learnings "$BASE" "$Q16"
Q17=$(queue q17 t:12)
reset_prs; pr 12 "$T" ""
expect err "an entry name with a trailing extension"                         learnings "$BASE" "$Q17"

echo "== attribution"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "Summary"
expect ok  "clean commits, titles and bodies"                                attribution "$BASE" "$Q8"
Q14=$(queue q14 a:11 c:12)
reset_prs; pr 11 "$A" "Summary"; pr 12 "$C" "Summary"
expect err "a co-author trailer in a queued PR's commit"                     attribution "$BASE" "$Q14"
reset_prs; pr 11 "$A" "Summary"; pr 12 "$B" "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
expect err "a generated-with footer in the second PR's body"                 attribution "$BASE" "$Q8"
reset_prs; pr 11 "$A" "Summary" "" open dev "Generated with Claude"; pr 12 "$B" "Summary"
expect err "attribution in the first PR's title"                             attribution "$BASE" "$Q8"
g switch -q -c q15 dev; g merge -q --no-ff -m "Merge pull request #11 from o/a

Co-authored-by: Claude <noreply@anthropic.com>" a; Q15=$(g rev-parse HEAD); LAST=11
reset_prs; pr 11 "$A" "Summary"
expect err "attribution in the queue's merge commit message"                 attribution "$BASE" "$Q15"
reset_prs; pr 11 "$A" "Summary"; python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); p["body"]=None; json.dump(p, open(sys.argv[1],"w"))' "$TMP/gh/repos_o_r_pulls_11.json"
LAST=11; expect ok  "a PR with an empty (null) body"                         attribution "$BASE" "$Q1"
reset_prs; pr 11 "$A" "Summary"; python3 -c 'import json,sys; p=json.load(open(sys.argv[1])); p["body"]=["x"]; json.dump(p, open(sys.argv[1],"w"))' "$TMP/gh/repos_o_r_pulls_11.json"
expect err "a body that isn't a string"                                      attribution "$BASE" "$Q15"
reset_prs
expect err "gh can't read the PR"                                            attribution "$BASE" "$Q15"

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
