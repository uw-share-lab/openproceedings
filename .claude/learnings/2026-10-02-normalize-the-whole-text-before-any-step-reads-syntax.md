# A tokenizer that normalizes per character after a syntax scan is form-dependent; NFKC the whole text first

**Key lesson:** If any step of a tokenizer reads syntax (LaTeX here) before Unicode normalization, the same text in NFC and NFD (or NFKC) can tokenize differently; make the canonical form step 1 over the whole text, keep raw offsets with a per-character owner map (`normalize._View`), and when the change needs a `TOKENIZER_VERSION` bump, keep the old version served (`SERVED_TOKENIZERS`, a frozen copy of its code) and pass the index's version to every reader of text, the parser and `canonical_hash` included, or records pinned to old indexes stop reproducing.

- **Date:** 2026-10-02 · **Task:** n/a (owner decision 2026-10-02; TASK-168's finding) · **Area:** query
- **Artifacts:** `backend/src/openproceedings/query/normalize.py` (`_view`, `_owners`, `TokenizerForm`), `backend/tests/unit/test_tokenizer_versions.py`, `backend/tests/unit/tokenizer_v2/`, `backend/tests/contract/test_records.py::test_a_record_saved_on_a_tokenizer_2_index_reproduces_after_the_tokenizer_3_build`, `docs/results/2026-10-02-tokenizer-3.md`

## What we set out to do

Make every Unicode form of a text tokenize alike (NFD `Caf\é` gave `caf`, NFC `caf e`), without breaking the replay of records pinned to existing indexes.

## What we learned

- "All four forms alike" means `tokens(t) == tokens(NFKC(t))`, so the canonical step has to be NFKC, not NFC: NFC-first still splits `\ﬁ`, `$x^²$` and full-width `＼`. A consequence: full-width `＄`/`＼` become LaTeX (spec 02 said they were text).
- Token texts are exact by construction (the old loop run on `NFKC(text)`); only spans need care. Replaying NFKD, canonical ordering and composition on (character, raw range) pairs gives each NFKC character its raw characters; interleaved marks (`=` + U+0345 + U+0338) need the old task-075 rule (first span ends where the second starts) to keep spans disjoint.
- A tokenizer version is not only an index input: the parse (terms), `canonical_hash`, the highlighter and the lexer's LaTeX scan all depend on it, so the version must come from the engine's manifest (`TantivyEngine.tokenizer_version`), not the module constant. `replay` now parses with the tokenizer of the index it runs on.
- Recovery found that re-parsing a query on its target version is too late if its initial current-version parse refuses it. API exports and CLI search/export/save now check raw length, select the index, then validate once with its tokenizer. Source aliases, scope warnings and filter-edit splice/wrap probes must also pass that version.
- The editor needs the same version boundary: independent server-generated v2/v3 goldens caught 47 lexer/Lezer differences, and a live CodeMirror meta switch needs a language compartment to preserve selection and undo history. Missing or unsupported metadata defaults to the current lexer.
- The 95,877-record local corpus had no title/abstract token changes; all 14 historical saved records reproduced on their pins, and new-only replay reported tokenizer drift with no ID changes (result document).
- Hypothesis found two real bugs in the first draft: `first_math_end` answering for a `\(` region, and the lexer's own Pandoc checks reading raw characters where the tokenizer reads NFKC (a spacing accent after `$` is a space; `½` begins with a digit).

## Dead ends — don't repeat these

- Translating only the four `$`/`\` look-alikes in the tokenizer: compatibility characters next to them (`´`, `½`, `ﬁ`) still change LaTeX decisions; only whole-text NFKC is form-independent.
- Calling the raw scan as `math_regions(text, "2")` to mean "as it stands": a version string standing for a behaviour; use a helper (`_regions`) and branch on the form.

## Decisions (and what would change them)

- Tokenizer 3 = NFKC first; serve 2 and 3 (decision-033). Retire 2 once no record pins a tokenizer-2 index.

## Follow-ups

- Final tokenizer boundary recorded in decision-033 after performance and twins merged; dedup decision-031 and takedown decision-032 remain separate.

## Propagated to

- Skill / agent / CLAUDE.md updated? — `.claude/skills/token-contract/SKILL.md`, `.claude/skills/index-versioning/SKILL.md`, `.claude/skills/codemirror-lezer/SKILL.md`, specs 02/03/04
- Test or hook added? — `test_tokenizer_versions.py` (frozen-copy equality, four-form property, NFC/NFD parse property), golden `FORMS`/`CHANGED_IN_3`, nightly exhaustive four-form check, contract replay test; target-selection/source/filter regression tests; independent v2/v3 editor goldens and live meta-switch/undo test

## Addendum — 2026-10-02

The schema-3 performance branch and tokenizer-3 branch change independent inputs. Merging one version
selector over the other strands valid legacy indexes. Preserve both explicit build parameters and both
manifest dispatch tables, then test schema 2/3 × tokenizer 2/3: the schema-ranking property and verified
clause tests run for each tokenizer; tokenizer-pinned replay runs for each schema; schema-pinned replay
runs for each tokenizer. The integration focused run passed 227 tests (`/tmp/tokenizer-perf-integration-focused.log`).
Propagated to the index-versioning skill and the parametrized engine/record tests. Historical real-corpus
figures above describe the earlier replay run; this integration result uses synthetic snapshots.

## Addendum — 2026-10-03

Final integration changed the synthetic fixture's index hash to `d6a1476ee48b`. The retirement contract
sorted actual directory names but compared them with an unsorted expected list, assuming that every hash
sorts before `current`. The exact full run exposed this assumption (6,751 passed, one failure); the
isolated retirement case reproduced it. Compare both name collections in the same order, preserving
all assertions about the retired version, remaining index contents and current symlink. Propagated to
`backend/tests/contract/test_index_retire_cli.py::test_an_unpinned_version_is_retired`.

## Addendum — 2026-10-03: sparse normalization changes need sparse mapping work

PR93's unchanged 20% CI gate caught a 33% small-build regression and 22–33% highlight/endpoint regressions.
A profile of 500 synthetic records found 76 NFKC-changing fields among 1,000 fields, yet raw mapping called
`_owners` 97,065 times across five passes, including every unchanged ASCII character. Batch unchanged
ASCII runs into identity owner ranges, retaining the last ASCII base with following combining marks.
Text-only index normalization needs the same whole-text NFKC form but no reconstructed raw spans.

The focused four-form, frozen-v2, lexer golden and highlight controls passed 1,077 tests with two optional
skips. New explicit raw-span rows cover ASCII adjacent to combining marks, reordered marks, Hangul jamo
and full-width text; an independent property compares text-only normalization with raw-span token texts
for both versions. Local matched base/head benchmark runs retained the 20% minimum guard and all budgets:
72 passed on each side; small-build minimum149.48→148.32ms, narrow highlights4.46→4.88ms,
narrow endpoint6.58→6.89ms. These local numbers are distinct from Linux CI and do not certify an 80k budget.
Propagated to token-contract, spec03 and versioned tokenizer tests. Profiling call counts identify the
cause; frequency/noise makes the profile's total time unsuitable as a benchmark comparison.

## Addendum — 2026-10-03: admission assertions need room for the separate CPU debit

PR93's Linux test found that an exactly three-token bucket could not always fund a two-token verified
export followed by a one-token search: the correct post-request verification CPU debit leaves slightly
less than one token. A local deterministic RED freezes only limiter bucket clocks and injects a positive
1ms CPU measurement while delegating the real debit. The admission test now uses capacity3.1, checks
that both buckets paid exactly0.000001 CPU tokens, permits one search and refuses the second.
The0.1 reserve is below another admission token; a scratch control that debits an extra token in each
bucket fails the same assertion. Production CPU charging is unchanged. Focused selection plus CPU/rate
controls passed27 tests. Propagated to `test_pinned_export_charges_target_verification_once`.
