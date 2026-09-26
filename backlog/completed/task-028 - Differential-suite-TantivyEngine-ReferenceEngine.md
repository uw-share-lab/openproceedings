---
id: TASK-028
title: 'Differential suite: TantivyEngine == ReferenceEngine'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 22:24'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
  - TASK-017
  - TASK-006
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §A (differential-tester, reference-oracle skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 0 counterexamples in 2,000 examples per CI run on the fixture snapshot
- [x] #2 Counterexamples are minimised and saved as golden cases
- [x] #3 Runs in the test workflow; 50k nightly job planned in M4
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: tests/fixtures/corpus/synthetic_5k.py (5,000 records generated in memory, deterministic; vocabulary and n-grams shared with tests/strategies.py so random trees hit documents; LaTeX, NFKC forms, marks, CJK, astral, invisible separators; every venue × year × track × status; some missing abstracts) and tests/differential/test_differential.py over engine_asts() (parser-valid, bare and all-negative trees): match sets, expand results or refusals, disjunctive facets (oracle only for fields with their own top-level conjunct; the rest counted from the known match set, which cut 85 s to 15 s at 200 examples), and total for every sort. CI profile: 0 counterexamples in 2,000 examples, 2.5 min. Regressions file seeded with 11 hard shapes, replayed every run. Teeth: 5 engine mutants (NEAR slop, one NEAR order, phrase slop, $ as *, empty expansion as all) all fail it. filters() now draws every track/status of the vocabulary (it missed tiny_papers, blogpost, competition, other, desk_rejected). Nightly: the properties job ignores the differential until task-057's own 50k job (it would take ~1 h locally, over that job's limit); task-057 gained that AC.

Review fixes (13 more engine mutants all caught; the harness sound). Must: the corpus had 78 distinct tokens, so rare terms and the 200-cap refusal were never reached. Now a Zipfian vocabulary: the strategy vocabulary and oddities first, then ~8,000 pseudo-words on shared roots (6,374 terms, 788 hapaxes, 2,669 with df <= 3; re*/tr*/co* expand past 200), and trees draw from the corpus's own dictionary (synthetic_5k.vocab(): the 600 most frequent terms, rare terms a third of the time, an over-cap stem one wildcard in twenty; 300 draws: 8% refused, 29% empty, 10% matching 1-3 records). tests/strategies.py tree strategies take a Vocab (default the golden fixture's). Shoulds: oddity tokens are queried (they're in the dictionary); exclusion counts are compared for trees that parse (excluded() vs a record-by-record count; the bucket-order mutant is caught); every failure message ends with the AST JSON and the docstring/agent say how to add it to differential-regressions.json. Nits: year_asc order and page membership checked; the text length is drawn once per field; the corpus is hash-pinned. Generation 2 s (cumulative weights precomputed). CI profile: 0 counterexamples in 2,000 examples, 4.8 min.

Verification (APPROVE; brute_excluded's shortcut sound over ~34,000 cases; 10/10 mutants killed; 4.8 min at ci) nits fixed: two regressions (cado AND status:accepted; bare status:accepted) exercise brute_excluded's oracle and whole-corpus branches every run; exclusion counts are compared as JSON, so spec 04's bucket order is checked; brute_excluded's docstring says it trusts parse() for identification and defaults; vocab() adds three absent terms to the rare draws. synthetic_5k.records also takes a size and abstract length now (task-031's 80k report; the defaults and the pinned hash are unchanged).
<!-- SECTION:NOTES:END -->
