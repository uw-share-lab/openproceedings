#!/usr/bin/env bash
# Case table for how mutate.py runs a mutant (nightly mutate shards ran past 140 min, 2026-10-09/10): the tables
# that name the mutated file run first and the rest only if they all pass; a failure stops the rest of its phase;
# a survivor runs every table; a table that hangs is stopped at its timeout and, if it hangs again alone, the
# mutant is TIMEOUT (killed); the timeout is 10x a table's baseline, at least 60 s, and a --table-timeout under
# 10x a baseline is refused (it would make a slow survivor a kill); an interrupt stops the queued mutants too.
# A table that declares the files it exercises (`# mutate-scope:` in its header) never runs for a mutant of another
# file, so a table flaky under load can't kill one (TASK-238); this one declares mutate.py, all it runs. Its timing
# checks are bounded by the sleeps they tell apart, not by how fast a loaded machine starts a run (TASK-238).
# A fixture repo of tiny tables, each logging its start to $MUT_LOG, so the table takes seconds.
# Mutants in .claude/scripts/mutants/mutate.json. Usage: ./test-mutate-run.sh
# mutate-scope: .claude/scripts/mutate.py
set -u
# Never inherit a repo from the caller (git exports GIT_DIR etc. to hooks such as pre-push).
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP=$(mktemp -d)
pass=0; fail=0
R="$TMP/r"
mkdir -p "$R/.claude/scripts/mutants" "$R/.claude/hooks/tests" "$R/.claude/scripts/tests" "$R/src"
cp "$SRC/.claude/scripts/mutate.py" "$R/.claude/scripts/mutate.py"
printf 'alpha gamma\n' > "$R/src/a.txt"
printf 'kappa\n' > "$R/src/hidden.txt"
printf 'def run(): pass\n' > "$R/src/widget.py"
printf 'mu\n' > "$R/src/helped.txt"
printf 'rho\n' > "$R/src/p1.txt"; printf 'rho\n' > "$R/src/p2.txt"
printf 'xi upsilon\n' > "$R/src/scoped.txt"; printf 'upsilon\n' > "$R/src/u.txt"
# the sleep that a hung table leaves running, by a length no other run of this table uses (a nested run's)
NAP="3017.$$"

# t-a names a.txt: fails when `alpha` is gone, hangs on `HANG`
cat > "$R/.claude/hooks/tests/t-a.sh" <<EOF
root="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
echo "t-a \$root" >> "\$MUT_LOG"
if grep -q HANG "\$root/src/a.txt"; then sleep $NAP; fi
grep -q alpha "\$root/src/a.txt"
EOF
# t-a-slow names a.txt too: with `SLOW` in it, takes 20 s before it passes
SLOW="20.$$"  # 20 s, by a length of its own, as NAP
# a mutant of stop() leaves the sleeps running: never past this table
trap 'pkill -f "sleep $NAP" 2>/dev/null; pkill -f "sleep $SLOW" 2>/dev/null; rm -rf "$TMP"' EXIT
cat > "$R/.claude/hooks/tests/t-a-slow.sh" <<EOF
root="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
echo "t-a-slow \$root" >> "\$MUT_LOG"
if grep -q SLOW "\$root/src/a.txt"; then sleep $SLOW; echo "t-a-slow-end \$root" >> "\$MUT_LOG"; fi
true
EOF
# t-once names a.txt: with `ONCE` in it, hangs the first time only (a table slowed once, by load)
cat > "$R/.claude/hooks/tests/t-once.sh" <<EOF
root="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
echo "t-once \$root" >> "\$MUT_LOG"
if grep -q ONCE "\$root/src/a.txt" && [ ! -e "\$MUT_LOG.once" ]; then : > "\$MUT_LOG.once"; sleep $NAP; fi
true
EOF
# t-other names neither file (it spells the hidden one in pieces): fails when `kappa` is gone from it
cat > "$R/.claude/scripts/tests/t-other.sh" <<'EOF'
root="$(cd "$(dirname "$0")/../../.." && pwd)"
echo "t-other $root" >> "$MUT_LOG"
name="hid""den"
grep -q kappa "$root/src/$name.txt"
EOF
# t-w names widget.py only by its stem, as a table imports cmdparse: fails when `run` is gone
cat > "$R/.claude/scripts/tests/t-w.sh" <<'EOF'
root="$(cd "$(dirname "$0")/../../.." && pwd)"
echo "t-w $root" >> "$MUT_LOG"
cd "$root/src" && python3 -c 'import widget; widget.run()'
EOF
# t-h names helped.txt only in the helper beside it that it runs (as test-dependabot.sh runs its Python case table)
cat > "$R/.claude/scripts/tests/t-h.sh" <<'EOF'
echo "t-h $(cd "$(dirname "$0")/../../.." && pwd)" >> "$MUT_LOG"
python3 "$(dirname "$0")/h_cases.py"
EOF
cat > "$R/.claude/scripts/tests/h_cases.py" <<'EOF'
import pathlib, sys
sys.exit("mu" not in (pathlib.Path(__file__).parents[3] / "src" / "helped.txt").read_text())
EOF
# t-pair names p1.txt: fails only when `rho` is gone from both copies (text a gate keeps identical in two files)
cat > "$R/.claude/hooks/tests/t-pair.sh" <<'EOF'
root="$(cd "$(dirname "$0")/../../.." && pwd)"
echo "t-pair $root" >> "$MUT_LOG"
grep -q rho "$root/src/p1.txt" || grep -q rho "$root/src/p2.txt"
EOF
# t-flaky declares it exercises scoped.txt only, and fails in every mutant's copy, as a table flaky under load
# would (TASK-238): it runs for a mutant of scoped.txt, and never for another file's
cat > "$R/.claude/scripts/tests/t-flaky.sh" <<'EOF'
# mutate-scope: src/scoped.txt
# it names src/u.txt too, and still never runs for u.txt's mutants
root="$(cd "$(dirname "$0")/../../.." && pwd)"
echo "t-flaky $root" >> "$MUT_LOG"
case "$root" in */baseline) true ;; *) false ;; esac
EOF
cat > "$R/.claude/scripts/mutants/m.json" <<'EOF'
[
 {"label": "m-first", "file": "src/a.txt", "old": "alpha", "new": "omega"},
 {"label": "m-survives", "file": "src/a.txt", "old": "gamma", "new": "delta"},
 {"label": "m-equivalent", "file": "src/a.txt", "old": "gamma", "new": "delta", "equivalent": true},
 {"label": "m-second", "file": "src/hidden.txt", "old": "kappa", "new": "lambda"},
 {"label": "m-stops", "file": "src/a.txt", "old": "alpha", "new": "SLOW"},
 {"label": "m-hangs", "file": "src/a.txt", "old": "alpha", "new": "HANG alpha"},
 {"label": "m-slow", "file": "src/a.txt", "old": "alpha", "new": "SLOW alpha"},
 {"label": "m-stem", "file": "src/widget.py", "old": "def run", "new": "def ran"},
 {"label": "m-helper", "file": "src/helped.txt", "old": "mu", "new": "nu"},
 {"label": "m-once", "file": "src/a.txt", "old": "gamma", "new": "ONCE gamma"},
 {"label": "m-int-1", "file": "src/a.txt", "old": "alpha", "new": "SLOW alpha"},
 {"label": "m-int-2", "file": "src/a.txt", "old": "gamma", "new": "delta"},
 {"label": "m-both", "file": "src/p1.txt", "old": "rho", "new": "tau", "also": ["src/p2.txt"]},
 {"label": "m-onecopy", "file": "src/p1.txt", "old": "rho", "new": "tau"},
 {"label": "m-alsostale", "file": "src/p1.txt", "old": "rho", "new": "tau", "also": ["src/a.txt"]},
 {"label": "m-scoped", "file": "src/scoped.txt", "old": "xi", "new": "pi"},
 {"label": "m-unexercised", "file": "src/u.txt", "old": "upsilon", "new": "phi"},
 {"label": "m-alsoscoped", "file": "src/u.txt", "old": "upsilon", "new": "phi", "also": ["src/scoped.txt"]}
]
EOF
# Mutants mutate.py refuses to run as written (TASK-254): an old text that occurs twice, and edits that stop a file
# compiling (Python, JSON, a shell script by suffix or by its #! line, a heredoc's Python program, a heredoc an edit
# adds); an edit to a file that already didn't compile is run as usual. No table names these files.
printf 'zeta zeta\n' > "$R/src/twice.txt"
printf 'x = 1\n' > "$R/src/ok.py"
printf 'def (:\n' > "$R/src/bad.py"
printf '{"a": 1}\n' > "$R/src/ok.json"
printf '#!/usr/bin/env bash\necho hi\nIFS= read -r -d "" P <<%sPY%s || true\nprint(1)\nPY\n' "'" "'" > "$R/src/hook.sh"
printf '#!/usr/bin/env bash\necho hi\n' > "$R/src/hook"
cat > "$R/.claude/scripts/mutants/v.json" <<'JSON'
[
 {"label": "v-ambiguous", "file": "src/twice.txt", "old": "zeta", "new": "eta"},
 {"label": "v-py", "file": "src/ok.py", "old": "x = 1", "new": "x = ("},
 {"label": "v-broken", "file": "src/bad.py", "old": "def", "new": "dfe"},
 {"label": "v-json", "file": "src/ok.json", "old": "1}", "new": "1"},
 {"label": "v-shell", "file": "src/hook.sh", "old": "echo hi", "new": "echo hi; fi"},
 {"label": "v-heredoc", "file": "src/hook.sh", "old": "print(1)", "new": "print(1"},
 {"label": "v-shebang", "file": "src/hook", "old": "echo hi", "new": "echo hi; fi"},
 {"label": "v-bounds", "file": "src/hook.sh", "old": "\nPY\n", "new": "\nPY\nIFS= read -r -d \"\" Q <<'PY' || true\ndef (:\nPY\n"},
 {"label": "v-fine", "file": "src/ok.py", "old": "x = 1", "new": "x = 2"}
]
JSON
# R3: R with a 5 s floor, so a hang is stopped by a timeout no load can make it refuse (an explicit --table-timeout
# is refused under 10x the slowest baseline, and a loaded machine can take 0.5 s to start a tiny table)
R3="$TMP/r3"
cp -R "$R" "$R3"
sed -E 's/^(TIMEOUT_FACTOR, TIMEOUT_FLOOR = [0-9]+, )[0-9.]+/\15.0/' "$SRC/.claude/scripts/mutate.py" \
  > "$R3/.claude/scripts/mutate.py"
# R4: R with a 120 s floor, so an explicit --table-timeout under the floor shows it is honoured, not raised to it
R4="$TMP/r4"
cp -R "$R" "$R4"
sed -E 's/^(TIMEOUT_FACTOR, TIMEOUT_FLOOR = [0-9]+, )[0-9.]+/\1120.0/' "$SRC/.claude/scripts/mutate.py" \
  > "$R4/.claude/scripts/mutate.py"

# A second fixture, whose mutate.py has a 1 s floor so a timeout derived from a baseline shows: t-b takes 0.5 s
# (10x: 5 s), and 2.5 s with `SLOW2`, past the floor but well under 10x its baseline: slow, not hung
R2="$TMP/r2"
mkdir -p "$R2/.claude/scripts/mutants" "$R2/.claude/hooks/tests" "$R2/src"
sed -E 's/^(TIMEOUT_FACTOR, TIMEOUT_FLOOR = [0-9]+, )[0-9.]+/\11.0/' "$SRC/.claude/scripts/mutate.py" \
  > "$R2/.claude/scripts/mutate.py"
printf 'beta\n' > "$R2/src/b.txt"
cat > "$R2/.claude/hooks/tests/t-b.sh" <<'EOF'
root="$(cd "$(dirname "$0")/../../.." && pwd)"
sleep 0.5
if grep -q SLOW2 "$root/src/b.txt"; then sleep 2; fi
if grep -q LATE "$root/src/b.txt"; then sleep 2; exit 1; fi
grep -q beta "$root/src/b.txt"
EOF
# t-q names b.txt: fast (its timeout is the 1 s floor), and with `QONCE` hangs the first time only, which stops
# t-b mid-run: t-b must run again once the hang is not confirmed
cat > "$R2/.claude/hooks/tests/t-q.sh" <<EOF
root="\$(cd "\$(dirname "\$0")/../../.." && pwd)"
if grep -q QONCE "\$root/src/b.txt" && [ ! -e "\$MUT_LOG.once" ]; then : > "\$MUT_LOG.once"; sleep $NAP; fi
true
EOF
cat > "$R2/.claude/scripts/mutants/m.json" <<'EOF'
[
 {"label": "m-bslow", "file": "src/b.txt", "old": "beta", "new": "beta SLOW2"},
 {"label": "m-bonce", "file": "src/b.txt", "old": "beta", "new": "beta QONCE LATE"}
]
EOF

check() {  # check <label> <got> <want>
  if [ "$2" = "$3" ]; then pass=$((pass+1)); printf '  ok   %s\n' "$1"
  else fail=$((fail+1)); printf '  FAIL %s: got [%s] want [%s]\n' "$1" "$2" "$3"; fi
}
got=$(grep -c '^TIMEOUT_FACTOR, TIMEOUT_FLOOR = 10, 1.0' "$R2/.claude/scripts/mutate.py")
check "R2's mutate.py has the 1 s floor" "$got" "1"
got=$(grep -c '^TIMEOUT_FACTOR, TIMEOUT_FLOOR = 10, 5.0' "$R3/.claude/scripts/mutate.py")
check "R3's mutate.py has the 5 s floor" "$got" "1"
got=$(grep -c '^TIMEOUT_FACTOR, TIMEOUT_FLOOR = 10, 120.0' "$R4/.claude/scripts/mutate.py")
check "R4's mutate.py has the 120 s floor" "$got" "1"
run() {  # run <label match> [args...]: the result line and exit status in $line $rc, seconds in $secs, log in $TMP/log
  local m="$1"; shift
  : > "$TMP/log"
  local t0; t0=$(date +%s)
  rm -f "$TMP/log.once"
  MUT_LOG="$TMP/log" python3 "${ROOTDIR:-$R}/.claude/scripts/mutate.py" --jobs 2 --match "$m" "$@" > "$TMP/out" 2>&1
  rc=$?
  secs=$(( $(date +%s) - t0 ))
  line=$(grep -E '^  (ok  |FAIL) ' "$TMP/out" | sed -E 's/ +/ /g; s/^ //')
}
ran() {  # ran <table>: yes if <table> started for the mutant (not the baseline)
  if grep -E "^$1 " "$TMP/log" | grep -qv '/baseline$'; then echo yes; else echo no; fi
}

echo "== the tables that name the file first"
run m-first
check "killed by a table that names its file: exit 0" "$rc" "0"
check "killed by a table that names its file: the line" "$line" "ok KILLED m-first (t-a.sh)"
got=$(ran t-other)
check "a table that doesn't name it never starts" "$got" "no"

echo "== also: the same edit in every copy (TASK-243)"
run m-both
check "also: both copies changed: killed" "$line" "ok KILLED m-both (t-pair.sh)"
run m-onecopy
check "one copy changed: survives" "$line" "FAIL SURVIVED m-onecopy"
run m-alsostale
check "also: a copy without the text: stale" "$line" "FAIL STALE m-alsostale"

echo "== a survivor runs every table"
run m-survives
check "survivor: exit 1" "$rc" "1"
check "survivor: the line" "$line" "FAIL SURVIVED m-survives"
got=$(ran t-a)$(ran t-a-slow)$(ran t-other)$(ran t-w)$(ran t-h)
check "survivor: every table started" "$got" "yesyesyesyesyes"
run m-equivalent
check "an equivalent survivor: exit 0" "$rc" "0"
check "an equivalent survivor: the line" "$line" "ok SURVIVED m-equivalent"

run m-stem
check "named by its stem: the line" "$line" "ok KILLED m-stem (t-w.sh)"
got=$(ran t-other)
check "named by its stem: a table that doesn't name it never starts" "$got" "no"
run m-helper
check "named in a table's helper: the line" "$line" "ok KILLED m-helper (t-h.sh)"
got=$(ran t-other)
check "named in a table's helper: a table that doesn't name it never starts" "$got" "no"

echo "== a table that declares its files runs only for their mutants (TASK-238)"
run m-scoped
check "a mutant of a declared file: killed by the table" "$line" "ok KILLED m-scoped (t-flaky.sh)"
run m-unexercised
check "a mutant of a file no table exercises: never killed by a table that declares others" "$line" "FAIL SURVIVED m-unexercised"
got=$(ran t-flaky)$(ran t-other)
check "a mutant of another file: the declaring table never starts, the others do" "$got" "noyes"
run m-alsoscoped
check "a mutant that also changes a declared file: the table runs" "$line" "ok KILLED m-alsoscoped (t-flaky.sh)"
got=$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0, ".claude/scripts"); import mutate
print(sorted(mutate.table_scope(".claude/scripts/tests/test-mutate-run.sh") or []))')
check "this table declares mutate.py only (its fixtures' declarations aren't its own)" "$got" "['.claude/scripts/mutate.py']"

got=$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0, ".claude/scripts"); import mutate
print(mutate.can_kill(".claude/scripts/tests/test-dependabot.sh", [".claude/scripts/mutate.py"]))')
check "test-dependabot.sh never runs for a mutate.py mutant (it declares the dependabot scripts; TASK-254)" "$got" "False"
got=$(cd "$SRC" && python3 -c 'import sys; sys.path.insert(0, ".claude/scripts"); import mutate
for t in ("test-mutate-shard", "test-merge-group-gate", "test-changelog"):
    print(t, sorted(mutate.table_scope(f".claude/scripts/tests/{t}.sh") or []))')
want="test-mutate-shard ['.claude/scripts/mutate.py']
test-merge-group-gate ['.claude/scripts/merge_group_gate.py', '.github/workflows/claude-tooling.yml', '.github/workflows/lint.yml', '.github/workflows/pr-gates.yml', '.github/workflows/test.yml']
test-changelog ['.claude/scripts/changelog.py']"
check "the single-script tables declare what they run (TASK-254)" "$got" "$want"

echo "== a mutant that can't be run as written is refused, and no table runs for it (TASK-254)"
MUT_LOG="$TMP/log" python3 "$R/.claude/scripts/mutate.py" --check --match v- > "$TMP/out" 2>&1
check "--check: exit 1" "$?" "1"
got=$(grep -E '^  FAIL ' "$TMP/out" | sed -E 's/ +/ /g; s/^ //')
want="FAIL AMBIGUOUS v-ambiguous
FAIL UNCOMPILABLE v-py
FAIL UNCOMPILABLE v-json
FAIL UNCOMPILABLE v-shell
FAIL UNCOMPILABLE v-heredoc
FAIL UNCOMPILABLE v-shebang
FAIL UNCOMPILABLE v-bounds"
check "--check: each refused mutant and why; an edit to a file that didn't compile, and a fine edit, pass" "$got" "$want"
MUT_LOG="$TMP/log" python3 "$R/.claude/scripts/mutate.py" --check --match v-fine > "$TMP/out" 2>&1
check "--check: nothing refused: exit 0" "$?" "0"
run v-ambiguous
check "a run refuses an ambiguous mutant" "$line" "FAIL AMBIGUOUS v-ambiguous"
got=$(grep -cv '/baseline$' "$TMP/log")
check "a refused mutant: no table started for it" "$got" "0"
run v-broken
check "an edit to a file that already didn't compile runs (no table names it: it survives)" "$line" "FAIL SURVIVED v-broken"

echo "== the rest, when no table names the file"
run m-second
check "killed in the second phase: exit 0" "$rc" "0"
check "killed in the second phase: the line" "$line" "ok KILLED m-second (t-other.sh)"

echo "== a failure stops the rest of its phase"
run m-stops
check "stopped: exit 0" "$rc" "0"
check "stopped: the line" "$line" "ok KILLED m-stops (t-a.sh)"
got=$(grep -c '^t-a-slow-end ' "$TMP/log")
check "stopped: the slow table never finished" "$got" "0"

echo "== a hang is stopped at its timeout, and killed"
# in R4 (120 s floor) with --table-timeout 30: refused only past a 3 s baseline; about 60 s (two 30 s timeouts), and
# 240 s or more if the explicit timeout were ignored or raised to the floor, a margin load can't close
ROOTDIR="$R4" run m-hangs --table-timeout 30
check "hang: exit 0" "$rc" "0"
check "hang: the line" "$line" "ok TIMEOUT m-hangs (t-a.sh hung)"
got=$([ "$secs" -ge 55 ] && echo yes || echo "no ($secs s)")
check "hang: stopped at the 30 s --table-timeout (twice), no sooner" "$got" "yes"
got=$([ "$secs" -lt 200 ] && echo yes || echo "no ($secs s)")
check "hang: the explicit 30 s honoured, not the 120 s floor or the sleep" "$got" "yes"
got=$(pgrep -f "sleep $NAP" > /dev/null && echo "still running" || echo gone)
check "hang: the table's own children are stopped too" "$got" "gone"

echo "== a hang is a kill only if it hangs again alone"
ROOTDIR="$R3" run m-once
check "hung once: exit 1" "$rc" "1"
check "hung once: the line" "$line" "FAIL SURVIVED m-once"

echo "== the timeout is derived from each table's baseline"
run m-slow
check "slow under the 60 s floor (10x its baseline is less): exit 1" "$rc" "1"
check "slow under the 60 s floor: the line" "$line" "FAIL SURVIVED m-slow"
ROOTDIR="$R2" run m-bslow
check "slow past the floor, under 10x its baseline: exit 1" "$rc" "1"
check "slow past the floor, under 10x its baseline: the line" "$line" "FAIL SURVIVED m-bslow"
ROOTDIR="$R2" run m-bonce
check "a hang not confirmed: the tables it stopped run again" "$line" "ok KILLED m-bonce (t-b.sh)"
ROOTDIR="$R2" run m-bslow --table-timeout 1
check "a --table-timeout under 10x a baseline: exit 2" "$rc" "2"
check "a --table-timeout under 10x a baseline: no mutant judged" "$line" ""
got=$(grep -c 'under 10x the baseline of t-b.sh' "$TMP/out")
check "a --table-timeout under 10x a baseline: says which table" "$got" "1"

echo "== a misspelt # mutate-scope: path is refused (TASK-254)"
R5="$TMP/r5"
cp -R "$R" "$R5"
printf '# mutate-scope: src/scoped.txt src/scopd.txt\ntrue\n' > "$R5/.claude/scripts/tests/t-typo.sh"
python3 "$R5/.claude/scripts/mutate.py" --list --match m-first > "$TMP/out" 2>&1
check "a declared path that doesn't exist: exit 2" "$?" "2"
got=$(grep -c "t-typo.sh: src/scopd.txt" "$TMP/out")
check "a declared path that doesn't exist: says which table and path" "$got" "1"
python3 "$R/.claude/scripts/mutate.py" --list --match m-first > "$TMP/out" 2>&1
check "every declared path exists: exit 0" "$?" "0"

echo "== interrupted (Ctrl-C, or CI's timeout; TERM from an outer run's timeout): it stops now, and its tables"
for sig in INT TERM; do
  : > "$TMP/log"
  MUT_LOG="$TMP/log" python3 "$R/.claude/scripts/mutate.py" --jobs 2 --match m-slow > "$TMP/out" 2>&1 &
  pid=$!
  for _ in $(seq 1 600); do grep -q '^t-a-slow .*/m0$' "$TMP/log" 2>/dev/null && break; sleep 0.1; done
  started=$(grep -c '^t-a-slow .*/m0$' "$TMP/log")
  check "$sig: the slow table started before the signal" "$started" "1"
  t0=$(date +%s)
  kill "-$sig" "$pid"
  wait "$pid"
  secs=$(( $(date +%s) - t0 ))
  got=$([ "$secs" -lt 15 ] && echo yes || echo "no ($secs s)")
  check "$sig: exits well before the slow table's 20 s" "$got" "yes"
  sleep 1  # mutate.py exits only after stop() has signalled each table's group; give the kernel a moment
  got=$(pgrep -f "sleep $SLOW" > /dev/null && echo "still running" || echo gone)
  check "$sig: the slow table was stopped" "$got" "gone"
done

echo "== interrupted with mutants queued: none of them starts"
: > "$TMP/log"
MUT_LOG="$TMP/log" python3 "$R/.claude/scripts/mutate.py" --jobs 1 --match m-int > "$TMP/out" 2>&1 &
pid=$!
for _ in $(seq 1 600); do grep -q '^t-a-slow .*/m0$' "$TMP/log" 2>/dev/null && break; sleep 0.1; done
kill -INT "$pid"
wait "$pid"
sleep 1
got=$(grep -c '/m1$' "$TMP/log")
check "INT, --jobs 1: the queued mutant's tables never start" "$got" "0"

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
