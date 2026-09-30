#!/usr/bin/env bash
# Case table for .claude/scripts/changelog.py (spec 08 §Release, decision-023). Each case builds a
# throwaway repo (real commits and v* tags; the backend and frontend manifests; the code constants and
# uv.lock the script reads; an index manifest under data/indexes/; docs/releases.toml) with the script copied
# in, feeds it a PR list with --prs (or a fake `gh` on PATH that runs the script's own --jq filter over a
# REST-shaped fixture: no test reaches GitHub), and checks the exit status and the CHANGELOG.md it writes,
# or that a refusal wrote nothing and printed no traceback.
# Usage: ./test-changelog.sh
set -u
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_PREFIX
unset OP_DATA_DIR  # the script reads it as its default --data-dir, as op does
SRC="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
pass=0; fail=0
R="$TMP/r"
G=(git -C "$R" -c user.name=t -c user.email=t@example.org -c commit.gpgsign=false -c tag.gpgsign=false)
IDX=0123456789ab
SNAP=$(printf 'a%.0s' $(seq 1 64))

ok()  { pass=$((pass+1)); printf '  ok   %s\n' "$1"; }
bad() { fail=$((fail+1)); printf '  FAIL %s\n' "$1"; }
command -v jq >/dev/null || { echo "jq is required (the fake gh runs the script's --jq filter)"; exit 1; }

# versions <backend> <frontend>
versions() {
  printf '[project]\nname = "openproceedings"\nversion = "%s"\n' "$1" > "$R/backend/pyproject.toml"
  printf '{\n  "name": "frontend",\n  "version": "%s"\n}\n' "$2" > "$R/frontend/package.json"
}
# code <tokenizer> <schema> <query> <tantivy> — the constants the code at HEAD defines, and uv.lock's Tantivy
code() {
  local s="$R/backend/src/openproceedings"
  printf 'TOKENIZER_VERSION = "%s"  # 2: math\n' "$1" > "$s/query/normalize.py"
  printf 'SCHEMA_VERSION = "%s"\n' "$2" > "$s/engine/index.py"
  printf '"""q"""\n\nQUERY_VERSION = "%s"\n' "$3" > "$s/query/__init__.py"
  printf 'version = 1\n\n[[package]]\nname = "tantivy"\nversion = "%s"\n\n[[package]]\nname = "x"\nversion = "9"\n' "$4" > "$R/uv.lock"
}
# manifest <index_version> <tokenizer> <schema> <tantivy> [snapshot_hash] — an index built under data/
manifest() {
  mkdir -p "$R/data/indexes/$1"
  printf '{"index_version": "%s", "snapshot_hash": "%s", "tokenizer_version": "%s", "schema_version": "%s", "tantivy_version": "%s", "doc_count": 1}\n' \
    "$1" "${5:-$SNAP}" "$2" "$3" "$4" > "$R/data/indexes/$1/manifest.json"
}
# data <version> <tokenizer> <schema> <query> [tantivy] [index_version] — append a releases table
data() {
  printf '[releases."%s"]\nindex_version = "%s"\nsnapshot_hash = "%s"\ntokenizer_version = "%s"\nschema_version = "%s"\ntantivy_version = "%s"\nquery_version = "%s"\n\n' \
    "$1" "${6:-$IDX}" "$SNAP" "$2" "$3" "${5:-0.26.2}" "$4" >> "$R/docs/releases.toml"
}
commit() { "${G[@]}" commit -q --allow-empty -m "$1" && "${G[@]}" rev-parse HEAD; }
# pr <number> <title> <merged_at> <sha> <base> <head> [head_repo]
pr() { printf '{"number":%s,"title":"%s","merged_at":"%s","merge_commit_sha":"%s","base":"%s","head":"%s","head_repo":"%s"}' \
  "$1" "$2" "$3" "$4" "$5" "$6" "${7:-o/r}"; }

# The standard repo: c1, c2 tagged v0.1.0 (0.1.0 has a data table), then c3, c4 untagged; the code and the
# index at data/indexes/$IDX say TOKENIZER 2 · SCHEMA 2 · Tantivy 0.26.2 · QUERY 2.
fresh() {
  rm -rf "$R" && mkdir -p "$R/.claude/scripts" "$R/backend/src/openproceedings/query" \
    "$R/backend/src/openproceedings/engine" "$R/frontend" "$R/docs"
  cp "$SRC/.claude/scripts/changelog.py" "$R/.claude/scripts/"
  git init -q "$R" && versions 0.2.0 0.2.0 && code 2 2 2 0.26.2 && manifest "$IDX" 2 2 0.26.2
  : > "$R/docs/releases.toml" && data 0.1.0 2 2 2
  C1=$(commit c1); C2=$(commit c2); "${G[@]}" tag -a v0.1.0 -m v0.1.0; C3=$(commit c3); C4=$(commit c4)
  {
    echo "["
    pr 10 'feat: an earlier feature' 2026-01-02T00:00:00Z "$C1" dev feat/early; echo ","
    pr 1  'feat: add the lexer' 2026-01-02T00:00:00Z "$C1" dev feat/lexer; echo ","
    pr 2  'fix(query): keep NEAR <in> one [field] for __init__ and venue_name' 2026-01-03T00:00:00Z "$C2" dev fix/near; echo ","
    pr 9  'ci: pin actions' 2026-01-03T00:00:00Z "$C2" dev ci/pin; echo ","
    pr 3  'Read the archive* and `x' 2026-01-04T00:00:00Z "$C3" dev fix/archive; echo ","
    pr 4  'feat!: drop the v0 route' 2026-01-05T00:00:00Z "$C4" dev feat/drop; echo ","
    pr 11 'Tidy the notes, recall@25' 2026-01-05T00:00:00Z "$C4" dev misc-branch; echo ","
    pr 5  'Promote dev to main' 2026-01-03T00:00:00Z "$C2" main dev O/R; echo ","
    pr 6  'chore: release 0.1.0' 2026-01-03T00:00:00Z "$C2" dev release/0.1.0; echo ","
    pr 12 'chore: merge main into dev after 0.1.0' 2026-01-03T00:00:00Z "$C2" dev release/0.1.0-back-merge; echo ","
    pr 7  'feat: stacked on the lexer' 2026-01-02T00:00:00Z "$C1" feat/lexer feat/x; echo ","
    pr 8  'docs: a note from a fork' 2026-01-04T00:00:00Z "$C3" main dev fork/r; echo ","
    pr 13 'fix: a fork branch named like a release' 2026-01-03T12:00:00Z "$C3" dev release/x fork/r
    echo "]"
  } > "$TMP/prs.json"
}
run() { python3 "$R/.claude/scripts/changelog.py" --repo o/r --prs "$TMP/prs.json" "$@" > "$TMP/out" 2>&1; }

# expect <ok|err> <label> [args...] — the exit status; on err, also that CHANGELOG.md wasn't touched and
# the refusal is a one-line message, not a traceback
expect() {
  local want="$1" label="$2" got before after; shift 2
  before=$(cat "$R/CHANGELOG.md" 2>/dev/null || echo "<none>")
  if run "$@"; then got=ok; else got=err; fi
  after=$(cat "$R/CHANGELOG.md" 2>/dev/null || echo "<none>")
  if [ "$got" = "$want" ] && { [ "$got" = ok ] || { [ "$before" = "$after" ] && ! grep -q Traceback "$TMP/out"; }; }; then
    ok "$label -> $got"
  else bad "$label -> $got (want $want; a refusal must leave CHANGELOG.md alone and print no traceback)"; cat "$TMP/out"; fi
}
# has / lacks <label> <fixed string> — in CHANGELOG.md; said <label> <fixed string> — in the last output
has()   { if grep -qF -- "$2" "$R/CHANGELOG.md"; then ok "$1"; else bad "$1: missing $2"; fi; }
lacks() { if grep -qF -- "$2" "$R/CHANGELOG.md"; then bad "$1: found $2"; else ok "$1"; fi; }
said()  { if grep -qF -- "$2" "$TMP/out"; then ok "$1"; else bad "$1: output lacks $2"; cat "$TMP/out"; fi; }
# under <label> <section> <n> — PR #n is listed in `## <section>`
under() {
  if awk -v s="## $2" -v n="[#$3]" '/^## /{in_=($0==s)} in_ && index($0,n){f=1} END{exit !f}' "$R/CHANGELOG.md"; then ok "$1"
  else bad "$1: #$3 not under ## $2"; cat "$R/CHANGELOG.md"; fi
}

echo "== the standard repo, byte for byte"
fresh; expect ok "writes CHANGELOG.md"
{ sed -n '1,/^## /p' "$R/CHANGELOG.md" | sed '$d'; cat <<'EOF'
## Unreleased

### Added

- **Breaking:** drop the v0 route ([#4](https://github.com/o/r/pull/4))

### Changed

- a note from a fork ([#8](https://github.com/o/r/pull/8))
- Tidy the notes, recall@25 ([#11](https://github.com/o/r/pull/11))

### Fixed

- a fork branch named like a release ([#13](https://github.com/o/r/pull/13))
- Read the archive\* and \`x ([#3](https://github.com/o/r/pull/3))

## 0.1.0

### Added

- add the lexer ([#1](https://github.com/o/r/pull/1))
- an earlier feature ([#10](https://github.com/o/r/pull/10))

### Fixed

- query: keep NEAR \<in\> one \[field\] for \_\_init\_\_ and venue_name ([#2](https://github.com/o/r/pull/2))

### Internal

- pin actions ([#9](https://github.com/o/r/pull/9))

### Data

- index_version `0123456789ab`, snapshot `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- TOKENIZER_VERSION 2 · SCHEMA_VERSION 2 · Tantivy 0.26.2 · QUERY_VERSION 2
- First release: no earlier search records.
EOF
} > "$TMP/want"
if head -1 "$TMP/want" | grep -qx '# Changelog' && diff -u "$TMP/want" "$R/CHANGELOG.md" > "$TMP/diff"; then ok "matches the golden"; else bad "differs from the golden"; cat "$TMP/diff"; fi
cp "$R/CHANGELOG.md" "$TMP/first"; run
if cmp -s "$TMP/first" "$R/CHANGELOG.md"; then ok "a second run gives the same bytes"; else bad "a second run changed the bytes"; fi
python3 "$R/.claude/scripts/changelog.py" --repo O/R --prs "$TMP/prs.json" > "$TMP/out" 2>&1
if cmp -s "$TMP/first" "$R/CHANGELOG.md"; then ok "--repo in another case gives the same bytes"; else bad "--repo O/R changed the bytes"; fi
expect ok  "--check on the file it just wrote"                           --check
printf 'x\n' >> "$R/CHANGELOG.md"
expect err "--check on an edited file"                                  --check
rm "$R/CHANGELOG.md"
expect err "--check with no CHANGELOG.md"                               --check
if [ ! -e "$R/CHANGELOG.md" ]; then ok "--check writes nothing"; else bad "--check wrote CHANGELOG.md"; fi
expect err "--check and --notes together"                               --check --notes 0.1.0

echo "== placement by tag"
fresh; "${G[@]}" tag -a v0.2.0 -m v0.2.0 "$C4"; data 0.2.0 2 2 2
expect ok  "two tags"
under "a PR goes to the oldest tag that holds it"                       0.1.0 1
under "a later PR to the tag after"                                     0.2.0 4
lacks "no Unreleased section"                                           "## Unreleased"
fresh; "${G[@]}" tag -d v0.1.0 >/dev/null; : > "$R/docs/releases.toml"; data 0.9.0 2 2 2; data 0.10.0 2 2 2
"${G[@]}" tag -a v0.9.0 -m v0.9.0 "$C2"; "${G[@]}" tag -a v0.10.0 -m v0.10.0 "$C4"
expect ok  "tags v0.9.0 and v0.10.0"
under "versions sort as numbers, not strings"                           0.9.0 1
under "v0.10.0 holds the later PRs"                                     0.10.0 4

echo "== --release"
fresh; expect err "no data table for the release"                       --release 0.2.0
fresh; data 0.2.0 2 2 2; versions 0.2.0 0.1.9
expect err "frontend version differs"                                   --release 0.2.0
fresh; data 0.2.0 2 2 2; versions 0.1.9 0.2.0
expect err "backend version differs"                                    --release 0.2.0
fresh; data 0.2.0 2 2 2; printf '[project]\nname = "x"\n' > "$R/backend/pyproject.toml"
expect err "a manifest with no version"                                 --release 0.2.0
fresh; data 0.2.0 2 2 2; rm "$R/frontend/package.json"
expect err "a missing frontend/package.json"                            --release 0.2.0
fresh; data 0.2.0 2 2 2
expect ok  "versions, code and index agree with the table"              --release 0.2.0
has   "the untagged PRs are titled 0.2.0"                               "## 0.2.0"
lacks "no Unreleased section"                                           "## Unreleased"
has   "unchanged versions replay reproduced"                            "Search records saved under 0.1.0 replay as \`reproduced\` on the index_version they pin, while it is kept."
fresh; data 0.2.0 2 2 2; "${G[@]}" checkout -q "$C3"
expect ok  "on a HEAD behind dev"                                       --release 0.2.0
under "a PR in HEAD is titled 0.2.0"                                    0.2.0 3
under "a PR merged after HEAD stays Unreleased"                         Unreleased 4
fresh; versions 0.1.0 0.1.0
expect err "a version already tagged"                                   --release 0.1.0
fresh; data 0.0.9 2 2 2; versions 0.0.9 0.0.9
expect err "a version older than the latest tag"                        --release 0.0.9
fresh; data 0.2.0 2 2 2
expect err "not MAJOR.MINOR.PATCH"                                      --release 0.2
fresh; data 0.2.0 2 2 2; "${G[@]}" tag -a v0.1.1 -m v0.1.1; data 0.1.1 2 2 2
expect err "nothing merged since the last tag"                          --release 0.2.0

echo "== --release checks the table against the code and the index"
fresh; data 0.2.0 2 2 2; code 2 2 3 0.26.2
expect err "the code's QUERY_VERSION differs from the table"            --release 0.2.0
said  "names the code's value"                                          "QUERY_VERSION 2 (the code says 3)"
fresh; data 0.2.0 2 2 2; code 3 2 2 0.26.2
expect err "the code's TOKENIZER_VERSION differs"                       --release 0.2.0
fresh; data 0.2.0 2 2 2; code 2 3 2 0.26.2
expect err "the code's SCHEMA_VERSION differs"                          --release 0.2.0
fresh; data 0.2.0 2 2 2; code 2 2 2 0.27.0
expect err "uv.lock's Tantivy differs"                                  --release 0.2.0
fresh; data 0.2.0 2 2 2; printf 'version = 1\n' > "$R/uv.lock"
expect err "uv.lock pins no Tantivy"                                    --release 0.2.0
fresh; data 0.2.0 2 2 2; : > "$R/backend/src/openproceedings/query/__init__.py"
expect err "the code defines no QUERY_VERSION"                          --release 0.2.0
fresh; data 0.2.0 2 2 2 0.26.2 ba9876543210
expect err "no manifest for the table's index"                          --release 0.2.0
fresh; data 0.2.0 2 2 2; manifest "$IDX" 2 2 0.26.2 "$(printf 'b%.0s' $(seq 1 64))"
expect err "the index's snapshot_hash differs"                          --release 0.2.0
fresh; data 0.2.0 2 2 2; manifest "$IDX" 2 3 0.26.2
expect err "the index's schema_version differs"                         --release 0.2.0
fresh; data 0.2.0 2 2 2; manifest "$IDX" 2 2 0.27.0
expect err "the index's tantivy_version differs (code and table agree)" --release 0.2.0
said  "names the manifest's tantivy_version"                            "tantivy_version 0.26.2 (its manifest says 0.27.0)"
fresh; data 0.2.0 2 2 2; mkdir -p "$TMP/elsewhere/indexes"; rm -rf "$TMP/elsewhere/indexes/$IDX"; mv "$R/data/indexes/$IDX" "$TMP/elsewhere/indexes/"
expect ok  "--data-dir names where the index lives"                     --release 0.2.0 --data-dir "$TMP/elsewhere"
if OP_DATA_DIR="$TMP/elsewhere" python3 "$R/.claude/scripts/changelog.py" --repo o/r --prs "$TMP/prs.json" --release 0.2.0 > "$TMP/out" 2>&1; then
  ok "OP_DATA_DIR is the default data dir, as for op"; else bad "OP_DATA_DIR ignored"; cat "$TMP/out"; fi

echo "== --notes"
fresh; python3 "$R/.claude/scripts/changelog.py" --repo o/r --prs "$TMP/prs.json" --notes 0.1.0 > "$TMP/notes" 2> "$TMP/out"
sed -n '/^## 0.1.0$/,$p' "$TMP/want" | tail -n +3 > "$TMP/want-notes"
if cmp -s "$TMP/want-notes" "$TMP/notes"; then ok "prints the 0.1.0 section without its heading"; else bad "--notes 0.1.0"; diff -u "$TMP/want-notes" "$TMP/notes"; fi
if [ ! -e "$R/CHANGELOG.md" ]; then ok "--notes writes nothing"; else bad "--notes wrote CHANGELOG.md"; fi
expect err "--notes for a release that doesn't exist"                   --notes 0.3.0
expect err "--notes Unreleased (not a version)"                         --notes Unreleased
data 0.2.0 2 2 2
if python3 "$R/.claude/scripts/changelog.py" --repo o/r --prs "$TMP/prs.json" --release 0.2.0 --notes 0.2.0 > "$TMP/notes" 2> "$TMP/out" \
  && head -3 "$TMP/notes" | grep -qF "**Breaking:** drop the v0 route"; then ok "--release with --notes gives the pending release's notes"; else bad "--release --notes"; cat "$TMP/notes" "$TMP/out"; fi
fresh; "${G[@]}" tag -a v0.1.1 -m v0.1.1 "$C3"; "${G[@]}" tag -a v0.1.10 -m v0.1.10 "$C4"; data 0.1.1 2 2 2; data 0.1.10 2 2 2
python3 "$R/.claude/scripts/changelog.py" --repo o/r --prs "$TMP/prs.json" --notes 0.1.1 > "$TMP/notes" 2> "$TMP/out"
if grep -qF '[#3]' "$TMP/notes" && ! grep -qF '[#4]' "$TMP/notes"; then ok "--notes 0.1.1 is not 0.1.10"; else bad "--notes 0.1.1 printed another section"; cat "$TMP/notes" "$TMP/out"; fi

echo "== replay across versions"
fresh; data 0.1.1 3 2 2; versions 0.1.1 0.1.1; code 3 2 2 0.26.2; manifest "$IDX" 3 2 0.26.2
expect err "a TOKENIZER_VERSION change in a patch release"              --release 0.1.1
fresh; data 0.1.1 2 2 3; versions 0.1.1 0.1.1; code 2 2 3 0.26.2
expect err "a QUERY_VERSION change in a patch release"                  --release 0.1.1
fresh; data 0.1.1 2 3 2; versions 0.1.1 0.1.1; code 2 3 2 0.26.2; manifest "$IDX" 2 3 0.26.2
expect err "a SCHEMA_VERSION change in a patch release"                 --release 0.1.1
fresh; data 0.1.1 2 3 2 0.27.0; versions 0.1.1 0.1.1; code 2 3 2 0.27.0; manifest "$IDX" 2 3 0.27.0
expect err "a Tantivy upgrade (with its schema bump) in a patch release" --release 0.1.1
said  "refused as a patch"                                              "not a patch release"
fresh; data 0.2.0 2 2 2 0.27.0; code 2 2 2 0.27.0; manifest "$IDX" 2 2 0.27.0
expect err "a Tantivy upgrade without a SCHEMA_VERSION bump"            --release 0.2.0
said  "names the missing bump"                                          "without a SCHEMA_VERSION bump"
fresh; data 0.2.0 2 3 2 0.27.0; code 2 3 2 0.27.0; manifest "$IDX" 2 3 0.27.0
expect ok  "a Tantivy upgrade with its SCHEMA_VERSION bump, minor"      --release 0.2.0
has   "both are named"                                                  "(SCHEMA_VERSION 2 → 3, Tantivy 0.26.2 → 0.27.0)."
fresh; data 0.2.0 2 2 3; code 2 2 3 0.26.2
expect ok  "a QUERY_VERSION change in a minor release"                  --release 0.2.0
has   "the Data line names the change"                                  "- Search records saved under 0.1.0 or earlier replay as \`drifted\` (QUERY_VERSION 2 → 3)."
if [ "$(grep -A2 '^## 0.2.0' "$R/CHANGELOG.md" | tail -1)" = "**Search records saved under 0.1.0 or earlier replay as \`drifted\`: QUERY_VERSION 2 → 3. To reproduce one, run the release it was saved under on the index it pins.**" ]; then
  ok "the callout is the section's first line"; else bad "the callout is not the section's first line"; cat "$R/CHANGELOG.md"; fi
fresh; data 0.2.0 3 2 3; code 3 2 3 0.26.2; manifest "$IDX" 3 2 0.26.2
expect ok  "two versions change"                                        --release 0.2.0
has   "both are named"                                                  "(TOKENIZER_VERSION 2 → 3, QUERY_VERSION 2 → 3)."
fresh; data 0.1.1 2 2 2; versions 0.1.1 0.1.1
expect ok  "a patch release with unchanged versions"                    --release 0.1.1
fresh; data 0.1.1 2 2 2; data 0.2.0 2 2 3; data 0.3.0 2 2 3; code 2 2 3 0.26.2; versions 0.3.0 0.3.0
expect ok  "three earlier tables"                                       --release 0.3.0
has   "compared with the latest earlier release, not the oldest"        "- Search records saved under 0.2.0 replay as \`reproduced\` on the index_version they pin, while it is kept; those saved earlier replay as \`drifted\`."
fresh; data 0.1.1 2 2 2; data 0.2.0 2 2 2
expect ok  "a run of unchanged releases"                                --release 0.2.0
has   "the whole run reproduces"                                        "Search records saved under 0.1.0 to 0.1.1 replay as \`reproduced\` on the index_version they pin, while it is kept."
fresh; data 0.1.1 2 2 3; data 0.2.0 2 2 4; code 2 2 4 0.26.2
expect ok  "a change against the latest earlier release only"           --release 0.2.0
has   "the move is from the latest earlier release"                     "QUERY_VERSION 3 → 4"

echo "== tags and data"
fresh; : > "$R/docs/releases.toml"
expect err "a tagged release with no data table"
fresh; printf '[releases."0.1.0"]\nindex_version = "XYZ"\n' > "$R/docs/releases.toml"
expect err "a data table with a bad index_version"
fresh; grep -v '^query_version' "$R/docs/releases.toml" > "$TMP/d" && cp "$TMP/d" "$R/docs/releases.toml"
expect err "a data table missing a key"
said  "names the missing key"                                           "missing ['query_version']"
fresh; sed -i.bak 's/^index_version = .*/index_version = "0123456789AB"/' "$R/docs/releases.toml"
expect err "an index_version that is not 12 lowercase hex"
fresh; sed -i.bak 's/^snapshot_hash = .*/snapshot_hash = "abc"/' "$R/docs/releases.toml"
expect err "a snapshot_hash that is not 64 hex"
fresh; printf 'owner = "x"\n' >> "$R/docs/releases.toml"
expect err "an unknown key in a data table"
fresh; printf 'notes = "   "\n' >> "$R/docs/releases.toml"
expect err "a blank value"
fresh; printf '[other]\n' >> "$R/docs/releases.toml"
expect err "an unknown top-level table"
fresh; printf 'releases = 1\n' > "$R/docs/releases.toml"
expect err "releases is not a table of tables"
fresh; sed -i.bak 's/^\[releases."0.1.0"\]/[releases."v0.1.0"]/' "$R/docs/releases.toml"
expect err "a table keyed v0.1.0"
"${G[@]}" tag -d v0.1.0 >/dev/null
expect err "a table keyed v0.1.0 with no tags (no section renders it)"
fresh; printf 'notes = "a new\\n  crawl"\n' >> "$R/docs/releases.toml"
expect ok  "notes are written on one line"
has   "the notes line"                                                  "- a new crawl"
fresh; printf 'notes = "Generated with [Claude Code]"\n' >> "$R/docs/releases.toml"
expect err "an AI-attribution marker in the notes"
fresh; printf 'notes = "thanks @someone"\n' >> "$R/docs/releases.toml"
expect err "an @-mention in the notes"
fresh; rm "$R/docs/releases.toml"; "${G[@]}" tag -d v0.1.0 >/dev/null
expect ok  "no tags and no data file: everything is Unreleased"
lacks "no release section"                                              "## 0.1.0"
fresh; sed -i.bak "s/$C3/$(printf 'f%.0s' $(seq 1 40))/" "$TMP/prs.json"
expect err "a merge commit the repo doesn't have"
fresh; "${G[@]}" tag v1.0 >/dev/null; "${G[@]}" tag vnext >/dev/null
expect ok  "tags that aren't vX.Y.Z are ignored"

echo "== PR list"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"ci: pin Co-Authored-By: Claude"/' "$TMP/prs.json"
expect err "an AI-attribution trailer in a title"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"ci: noreply@anthropic.com"/' "$TMP/prs.json"
expect err "an attribution address in a title"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"chore: Generated with [Claude Code](x)"/' "$TMP/prs.json"
expect err "a bracketed footer (escaping must not hide it)"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"chore: Generated with  [Claude Code]"/' "$TMP/prs.json"
expect err "a footer with a double space"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"chore: Generated with\\u00a0[Claude Code]"/' "$TMP/prs.json"
expect err "a footer with a non-breaking space"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"fix: ask jane.doe@example.org"/' "$TMP/prs.json"
expect err "an email address in a title"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"deps: bump @types\/node and pin next@15.1.0 (@-mention rule)"/' "$TMP/prs.json"
expect ok  "an npm scope, a version pin and the word @-mention pass"
has   "a deps: title is Internal, the scope kept"                        "- bump @types/node and pin next@15.1.0 (@-mention rule) ([#9]"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"ci: thanks @someone"/' "$TMP/prs.json"
expect err "an @-mention in a title"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"ci: see https:\/\/example.org"/' "$TMP/prs.json"
expect err "a URL in a title"
fresh; sed -i.bak 's/"title":"ci: pin actions"/"title":"ci: see www.example.org"/' "$TMP/prs.json"
expect err "a www. address in a title"
fresh; sed -i.bak 's/"number":10,/"number":1,/' "$TMP/prs.json"
expect err "a repeated PR number"
fresh; sed -i.bak "s/$C1\"/${C1:0:12}\"/" "$TMP/prs.json"
expect err "a short merge sha"
fresh; sed -i.bak 's/"base":"dev","head":"feat\/lexer",//' "$TMP/prs.json"
expect err "an entry missing fields"
fresh; printf '[1]' > "$TMP/prs.json"
expect err "an entry that isn't an object"
fresh; printf '{}' > "$TMP/prs.json"
expect err "not a JSON array"
fresh; printf '[' > "$TMP/prs.json"
expect err "not JSON"
fresh; sed -i.bak 's/"head":"dev","head_repo":"fork\/r"/"head":"dev","head_repo":null/' "$TMP/prs.json"
expect ok  "a deleted fork (head_repo null) into main is counted"
has   "the deleted fork's PR"                                           "[#8]"
fresh; expect err "a malformed --repo"                                  --repo 'o/r/../x'
fresh
if python3 "$R/.claude/scripts/changelog.py" --prs "$TMP/prs.json" > "$TMP/out" 2>&1; then bad "ran without a repo"; else ok "no --repo and no origin remote -> err"; fi
"${G[@]}" remote add origin git@github.com:acme/widgets.git
if python3 "$R/.claude/scripts/changelog.py" --prs "$TMP/prs.json" > "$TMP/out" 2>&1; then ok "ssh origin remote read"; else bad "ssh origin remote read"; cat "$TMP/out"; fi
has   "links name the origin repo"                                      "https://github.com/acme/widgets/pull/1)"
"${G[@]}" remote set-url origin https://github.com/Acme/Gadgets.git
if python3 "$R/.claude/scripts/changelog.py" --prs "$TMP/prs.json" > "$TMP/out" 2>&1; then ok "https origin remote read"; else bad "https origin remote read"; cat "$TMP/out"; fi
has   "an https remote, lower-cased"                                    "https://github.com/acme/gadgets/pull/1)"

echo "== fetching through gh (a fake gh on PATH runs the script's --jq over REST-shaped pulls)"
fresh; mkdir -p "$TMP/bin"
python3 - "$TMP/prs.json" > "$TMP/rest.json" <<'PY'
import json, sys
rows = [
    {"number": r["number"], "title": r["title"], "merged_at": r["merged_at"],
     "merge_commit_sha": r["merge_commit_sha"], "base": {"ref": r["base"], "repo": {"full_name": "o/r"}},
     "head": {"ref": r["head"], "repo": None if r["head_repo"] is None else {"full_name": r["head_repo"]}}}
    for r in json.load(open(sys.argv[1]))
]
rows.append({"number": 99, "title": "feat: closed without merging", "merged_at": None,
             "merge_commit_sha": "e" * 40, "base": {"ref": "dev", "repo": {"full_name": "o/r"}},
             "head": {"ref": "feat/closed", "repo": {"full_name": "o/r"}}})
print(json.dumps(rows))
PY
cat > "$TMP/bin/gh" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" > "$TMP/gh-args"
jqf=""; while [ \$# -gt 0 ]; do [ "\$1" = --jq ] && { jqf="\$2"; shift; }; shift; done
jq -c "\$jqf" "$TMP/rest.json"
EOF
chmod +x "$TMP/bin/gh"
if PATH="$TMP/bin:$PATH" python3 "$R/.claude/scripts/changelog.py" --repo o/r > "$TMP/out" 2>&1 && cmp -s "$TMP/want" "$R/CHANGELOG.md"; then
  ok "gh's JSON lines through the real --jq give the golden"; else bad "gh's JSON lines differ from the golden"; cat "$TMP/out"; diff -u "$TMP/want" "$R/CHANGELOG.md"; fi
lacks "a closed, unmerged PR is left out"                               "[#99]"
if grep -q -- '--paginate' "$TMP/gh-args" && grep -q 'repos/o/r/pulls?state=closed' "$TMP/gh-args"; then ok "asks every page of closed PRs"; else bad "gh args: $(cat "$TMP/gh-args")"; fi
printf '#!/usr/bin/env bash\necho "HTTP 401" >&2\nexit 1\n' > "$TMP/bin/gh"
if PATH="$TMP/bin:$PATH" python3 "$R/.claude/scripts/changelog.py" --repo o/r > "$TMP/out" 2>&1; then bad "a failing gh is not a refusal"; else ok "a failing gh -> err"; fi
printf '#!/usr/bin/env bash\necho "not json"\n' > "$TMP/bin/gh"
if PATH="$TMP/bin:$PATH" python3 "$R/.claude/scripts/changelog.py" --repo o/r > "$TMP/out" 2>&1; then bad "gh output that isn't JSON was accepted"
elif grep -q Traceback "$TMP/out"; then bad "gh output that isn't JSON gives a traceback"; else ok "gh output that isn't JSON -> err"; fi

echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
