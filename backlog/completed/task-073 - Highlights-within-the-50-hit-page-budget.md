---
id: TASK-073
title: Highlights within the 50-hit page budget
status: Done
assignee:
  - '@performance-profiler'
created_date: '2026-09-26 21:07'
updated_date: '2026-09-27 09:13'
labels:
  - engine
milestone: m-3
dependencies:
  - TASK-027
  - TASK-035
  - TASK-031
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-027 review: highlighting a 50-hit page with ~400-word abstracts costs ~174 ms (tokenize is 164 ms of it), ~1.3 s at 3,000 words, against spec 03's 100 ms p95 for a search returning 50 hits. Where highlights are computed is the API's page-assembly decision (task-035): precompute each record's token offsets at index build (in the stored record, a SCHEMA_VERSION bump) or cache tokenize per (index_version, id).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A 50-hit page's highlights fit the spec 03 budget at 80k (measured by task-031's benchmark)
- [x] #2 Spans are identical to engine/highlight.py's for every golden query
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Measure first: per-page highlight cost, every Trust-Evals string, real index a7cfd04b656f (read-only) and the 5k fixture; cProfile. 2. Optimise without changing a span: tokenize fast paths (whole-text plain ASCII; per-char ASCII branch in the loop), one Highlighter per page (leaf allowed-sets once per query), per-field token-position map instead of a scan per leaf, lazy per-field tokenize. 3. Differentials vs frozen copies of the old tokenizer and highlighter (Hypothesis + golden + Trust-Evals on 5k + every fixture text); NEAR/phrase/wildcard exact-span tests. 4. Bench row '50-hit page incl. highlights' (test_bench + report_80k column). 5. Record numbers in docs/results, spec 03, token-contract skill.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measured first (load 8-30 throughout: other agents' runs; the A/B alternates old/new per round in one process so ratios hold). cProfile on the real index (a7cfd04b656f, read-only): tokenize 2.15 of 2.82 s (_fold once per character), occurrences 0.64 s. Changes: tokenize shortcuts (plain-ASCII text gives its [A-Za-z0-9]+ runs; an ASCII char with no following mark skips _fold), no TOKENIZER_VERSION bump (identical tokens: frozen-copy differential, 3,610 real texts identical, op index parity 0 differences, OP_EXHAUSTIVE passes); one Highlighter per page (search.run), per-field token-position map, lazy per-field tokenize. Highlighting a 50-hit page, p95: real 146 to 21 ms (main-1), 217 to 28 (main-2-pop); 5k fixture about 46 to 9; 80k about 170 to 34. 80k report column 'search with highlights' (search + display + highlights; exclusions keep their 300 ms budget): 53-73 ms p95, all under 100. Bench row test_search_first_50_hits_with_highlights. 12 hand mutants, 11 killed; the survivor is the equivalent lookup-branch swap. Numbers: docs/results/2026-09-27-highlights.md. 2026-09-27-bench.md not regenerated (machine not quiet); the new column appears on its next quiet regeneration.

All ACs met. The worktree sandbox refused the CLI's task-completion command for this agent, so the status stays In Progress (a Done task left in backlog/tasks/ fails check_backlog); it only needs to be moved to completed/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Highlights for a 50-hit page now fit spec 03's 100 ms budget at 80k with no span changed. The cost was tokenize (three quarters of it), so tokenize got two exact shortcuts (plain-ASCII texts; ASCII characters with no mark after them), with no TOKENIZER_VERSION bump, and engine/highlight.py got a per-page Highlighter (each leaf's allowed tokens once per query), a per-field token-position map instead of a rescan per leaf, and lazy per-field tokenizing; search.run builds one Highlighter per page. Highlighting a page costs 5-7x less (80k: about 170 to 34 ms p95); the 80k report's new 'search with highlights' column reads 53-73 ms p95 for every Trust-Evals string. Identical output: test_highlight_speed.py differentials against frozen copies of the old tokenizer and highlighter (Hypothesis, 44 golden queries, Trust-Evals on 5k, every fixture text), NEAR/phrase/wildcard exact-span tests, real-corpus token identity and op index parity 0 differences. Bench row test_search_first_50_hits_with_highlights; report_80k column and optional OUT path; results in docs/results/2026-09-27-highlights.md; spec 03, token-contract and api-contract skills updated.
<!-- SECTION:FINAL_SUMMARY:END -->
