# A query lexer that "does something reasonable" with odd input silently changes what a reviewer searched

**Key lesson:** In the query language, every spelling that could plausibly mean two things (a `-` touching `)`, a mid-word `$`, `year:2023 OR 2024`, a full-width `（`) must be an error or a warning with a span, never a quiet choice; probe with real reviewer habits (WoS, Scholar, pasted smart quotes) and mutate every rule.

- **Date:** 2026-09-25 · **Task:** task-011, task-012, task-013 · **Area:** query
- **Artifacts:** `backend/src/openproceedings/query/{lexer,parser,ast,canonical}.py`; commits 303037c, 5586999, ed16153, 106811f; decision-001

## What we set out to do
Lex and parse spec 02's query language into a typed AST with positioned diagnostics, and print a canonical
form whose hash identifies a query.

## What we learned
- **The first lexer passed 139 tests and still had 5 silent meaning changes**, all found by reviewers who
  probed with how people actually type queries:
  - `behavio$r` (WoS mid-word wildcard) was searched as `behavio r`;
  - `"large language model"-based` became `… AND NOT based`;
  - `trust －bias` (full-width minus) was searched as `bias`;
  - `year:2023 OR 2024` meant "2023 papers, or any paper mentioning 2024";
  - `source:foo` was accepted.
  The fix pattern each time was: error or warn, and quote the reading back to the user.
- **A golden table can pin nothing.** `shape()` rendered a word as `stem + wildcard`, which always equals
  the raw text, so no row checked wildcard detection. Render the part under test separately
  (`WORD:bench~*`). 18 of 41 lexer mutants survived before that fix.
- **The lexer and the tokenizer must share one definition of LaTeX math.** Counting `$` signs in the
  lexer disagreed with the tokenizer's Pandoc rule (`model$$`, `$f(x)$-DP`). `normalize.math_regions()`
  now exposes the tokenizer's own regions (evidence: `test_lexer.py` rows for `$f(x)$-DP` and `($x$)`).
- **Derive look-alike tables from data.** The NFKC look-alike set was produced by scanning every code
  point, and `test_nfkc_lookalike_table_is_derived_from_unicode` re-derives it on every run (0.07s).
- **"One error per mistake" is not "one error per query".** A `quietly()` helper that dropped errors while
  stepping over a bad span also hid genuinely separate mistakes (`source:(PMLR` lost its unbalanced
  paren). Suppress only errors whose span overlaps an error already reported.
- **Canonical form has to respect the lexer's own rules.** Decision-001 wrote `gpt-4*` ≡ `"gpt 4*"`, but
  the lexer rejects `"gpt 4*"` (the stem in that phrase part is `4`). Canonical form prints `"gpt-4*"`
  instead. The idempotence property (50k examples) is what keeps printing and parsing in step.

## Dead ends — don't repeat these
- **Splicing a file by an index computed before another replacement in the same script** shifted the
  splice and corrupted `test_parser.py` and `parser.py` (`ddef`, `def expected_aft    def …`). It happened
  twice in one session. Use unique-anchor `str.replace` (assert the count is 1), or recompute indices
  after every edit.
- **`make lint 2>&1 | grep …` hides lint's exit status**, so commit ed16153 went in with two mypy errors.
  Check `$?` (or `set -o pipefail`) before committing.
- **Suspecting a recursion crash without probing.** `title:`×5000 looked like unbounded recursion, but a
  field can't be followed by a field. Probe before "fixing". The real crash was the unknown-field path
  (`x:`×501), which a reviewer found.

## Decisions (and what would change them)
- `source:` is an error outside Scholar mode (`FIELD_COMPAT_ONLY`), so `Filter` never holds an
  untranslated alias. This would be reversed only if task-015 needs `source:` in native mode.
- `title: trust` (a space after the colon) is accepted and `title :trust` is an error. The first is
  unambiguous; the second would silently be `title AND trust`.
- Year values are 1000–9999 and `NEAR/n` has n ≤ 100, bounded in both the parser and the AST validators.
  Task-024's Tantivy compile will need its own limits if these change.

## Follow-ups
- [ ] task-014: default filters recognised by content need `structure()` equality and canonical
  filter order; keep `WARN_NESTED_FILTER` consistent with `WARN_FILTER_SCOPE`.
- [ ] task-015: Scholar mode must translate `source:`, since native mode already rejects it.

## Propagated to
- Spec 02 §Grammar (lexical details, rules) and §Error handling; skills `query-grammar`,
  `error-diagnostics`, `scholar-syntax-compat`, `codemirror-lezer`.
- Tests: `test_lexer.py` (NFKC table, wildcard shape), `test_parser.py` (one error per mistake, separate
  mistakes each reported), `test_ast.py` (invariants), `test_canonical.py` (idempotence, operator words).

## Addendum 2026-09-25 (tasks 014–017, decision-002, decision-003)
- **Printing the lint status is not gating on it.** Commit 62dd486 went in with lint at exit 2 because the
  command printed `lint=$?` and committed anyway, an hour after the first entry above recorded the same
  trap. Chain every commit on `make lint >/dev/null && …`. The pre-push hook would have caught it before
  the remote, but not before the commit.
- **Ask the reviewer's actual question when a rule changes a result set.** Reading the PoP string
  `(large language model$ | …)` has three defensible answers (Scholar's precedence, native precedence, or
  intent). It went to the review lead, who chose intent (decision-002). Only that string was affected; the
  primary string (`main-7-most-updated`, confirmed by the lead) quotes its phrases.
- **A rule that makes an equivalent spelling invalid is a bug in the rule.** `"generative AI$"` was
  rejected while `"generative-AI$"` passed. Counting a phrase's earlier words toward the stem fixed both,
  and removed canonical form's hyphen workaround (`gpt-4*` → `"gpt 4*"`, as decision-001 first wrote it).
- **Generate trees, not just strings.** The AST strategy found in minutes what string generators hadn't:
  a nested-filter warning on replay. It was legitimate (semantic, not printing), so the property now
  excludes exactly that code rather than all warnings. Keep escape hatches out of properties: the
  all-negative property first skipped any tree that parsed, and now compares against an independent
  positivity check.
- **Golden expected sets need an independent source.** The 200-record fixture's expected ids come from a
  separate regex evaluator in `make_reference_200.py`, and all 40 queries agreed with ReferenceEngine
  on the first run. Random word order almost never forms phrases, so the generator seeds some.

## Corrections 2026-09-25 (M1 review gate)
- "Canonical form prints `"gpt-4*"` instead" (What we learned) is superseded: once a phrase's earlier
  words count toward a wildcard's stem, canonical form prints `"gpt 4*"`, as decision-001 first wrote it.
- Commit 62dd486 in the first addendum was amended to 15e2294 before any push; 62dd486 no longer exists.
- The 200-record golden set has 44 queries, not 40, after the task-016 review added boundary rows.
