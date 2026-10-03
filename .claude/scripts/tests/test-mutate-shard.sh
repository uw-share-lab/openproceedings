#!/usr/bin/env bash
# Case table for mutate.py --shard i/n (TASK-171; the nightly mutate matrix runs one shard a job): the shards
# partition the selected mutants (disjoint, complete, the same split every run) and a bad i/n is refused with a
# clear error. Every row runs `--list`, which prints the selected labels and runs nothing, so the table takes a
# second. Mutants in .claude/scripts/mutants/mutate.json. Usage: ./test-mutate-shard.sh
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
REAL="$SRC/.claude/scripts/mutate.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0

# A fixture tree: this mutate.py with 7 mutants a1..g1 in two files (sorted by file name, then in file order).
mkdir -p "$TMP/r/.claude/scripts/mutants"
cp "$REAL" "$TMP/r/.claude/scripts/mutate.py"
FIX="$TMP/r/.claude/scripts/mutate.py"
printf '[{"label":"a1","file":"x","old":"o","new":"n"},{"label":"b2","file":"x","old":"o","new":"n"},{"label":"c1","file":"x","old":"o","new":"n"},{"label":"d2","file":"x","old":"o","new":"n"}]\n' \
  > "$TMP/r/.claude/scripts/mutants/1.json"
printf '[{"label":"e1","file":"x","old":"o","new":"n"},{"label":"f2","file":"x","old":"o","new":"n"},{"label":"g1","file":"x","old":"o","new":"n"}]\n' \
  > "$TMP/r/.claude/scripts/mutants/2.json"

check() {  # check <label> <got> <want>
  if [ "$2" = "$3" ]; then pass=$((pass+1)); printf '  ok   %s\n' "$1"
  else fail=$((fail+1)); printf '  FAIL %s: got [%s] want [%s]\n' "$1" "$2" "$3"; fi
}
labels() {  # labels <mutate.py> <args...> — the selected labels on one line; "rc=N" if it exits non-zero
  local script="$1" out rc; shift
  out=$(python3 "$script" --list "$@" 2>/dev/null); rc=$?
  if [ "$rc" -ne 0 ]; then echo "rc=$rc"; else printf '%s\n' "$out" | paste -sd' ' -; fi
}
refused() {  # refused <label> <shard> <expected message> — exits 1 with that message on stderr, lists nothing
  local out err rc
  # `--shard=`, so argparse hands -1/3 to parse_shard rather than reading it as an option
  out=$(python3 "$FIX" --list --shard="$2" 2>"$TMP/err"); rc=$?; err=$(cat "$TMP/err")
  if [ "$rc" -eq 1 ] && [ -z "$out" ] && printf '%s' "$err" | grep -qF -- "--shard '$2': $3"; then
    pass=$((pass+1)); printf '  ok   refused: %s\n' "$1"
  else fail=$((fail+1)); printf '  FAIL refused: %s: rc=%s out=[%s] err=[%s]\n' "$1" "$rc" "$out" "$err"; fi
}

echo "== the split (fixture of 7)"
check "no --shard: every mutant"            "$(labels "$FIX")"               "a1 b2 c1 d2 e1 f2 g1"
check "1/1 is every mutant"                 "$(labels "$FIX" --shard 1/1)"   "a1 b2 c1 d2 e1 f2 g1"
check "1/3: every 3rd from the 1st"         "$(labels "$FIX" --shard 1/3)"   "a1 d2 g1"
check "2/3: every 3rd from the 2nd"         "$(labels "$FIX" --shard 2/3)"   "b2 e1"
check "3/3: every 3rd from the 3rd"         "$(labels "$FIX" --shard 3/3)"   "c1 f2"
check "7/7: the last mutant alone"          "$(labels "$FIX" --shard 7/7)"   "g1"
check "9/9: more shards than mutants, empty" "$(labels "$FIX" --shard 9/9)"  ""
check "leading zeros: 02/03 is 2/3"         "$(labels "$FIX" --shard 02/03)" "b2 e1"
check "--match first, then the split"       "$(labels "$FIX" --match 1 --shard 2/2)" "c1 g1"
check "--list prints no shard header"       "$(python3 "$FIX" --list --shard 1/3 2>&1 | head -1)" "a1"

echo "== the real mutant set: n shards partition it, the same way on every runner"
# The reference order, computed here and not by mutate.py: the files sorted by name, each in file order. Every
# shard job builds its own list, so the order must not depend on the directory listing.
python3 -c 'import json, pathlib, sys
for f in sorted(pathlib.Path(sys.argv[1]).glob("*.json")):
    for m in json.loads(f.read_text()):
        print(m["label"])' "$SRC/.claude/scripts/mutants" > "$TMP/ref"
total=$(grep -c . "$TMP/ref")
check "the reference is not empty"             "$([ "$total" -gt 0 ] && echo yes)" "yes"
python3 "$REAL" --list > "$TMP/all"; rc=$?
check "--list: exit 0"                         "$rc" "0"
check "--list: every mutant, in sorted-file order" "$(cat "$TMP/all")" "$(cat "$TMP/ref")"
for n in 3 8; do
  : > "$TMP/union"; bad=0
  for i in $(seq 1 "$n"); do python3 "$REAL" --list --shard "$i/$n" >> "$TMP/union" || bad=1; done
  check "$n shards: every one exits 0"           "$bad" "0"
  # one multiset comparison: each label as often as in the reference, so complete and disjoint
  check "$n shards: complete and disjoint"       "$(sort "$TMP/union")" "$(sort "$TMP/ref")"
done
check "8 shards: sizes differ by at most 1" \
  "$(for i in $(seq 1 8); do python3 "$REAL" --list --shard "$i/8" | grep -c .; done | sort -n | sed -n '1p;$p' | paste -sd' ' - \
     | awk '{print ($2 - $1 <= 1) ? "yes" : "no"}')" "yes"
first=$(labels "$REAL" --shard 5/8)
# Bash 3.2 can misparse a case-pattern ')' inside $(...); keep the assertion outside it.
case "$first" in ''|rc=*) listed=no;; *) listed=yes;; esac
check "stable: shard 5/8 lists mutants"        "$listed" "yes"
check "stable: shard 5/8 twice is the same"    "$(labels "$REAL" --shard 5/8)" "$first"

echo "== a bad i/n is refused"
form="expected i/n, e.g. 2/8"; range="need 1 <= i <= n"
refused "0/3 (shards count from 1)"   0/3    "$range"
refused "4/3 (i past n)"              4/3    "$range"
refused "1/0 (no shards)"             1/0    "$range"
refused "0/0"                         0/0    "$range"
refused "-1/3 (negative)"             -1/3   "$form"
refused "3 (no slash)"                3      "$form"
refused "1/2/3 (two slashes)"         1/2/3  "$form"
refused "a/b (not numbers)"           a/b    "$form"
refused "empty"                       ""     "$form"
refused "/3 (no i)"                   /3     "$form"
refused "' 1/3' (a space)"            " 1/3" "$form"
refused "superscript digit"           "²/3"  "$form"
refused "Arabic-Indic digits"         "١/٣"  "$form"

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
