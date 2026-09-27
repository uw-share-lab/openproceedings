# Exact ties, a real test corpus and a quiet machine were each needed before the engine's claims held

**Key lesson:** Test the Tantivy engine on a corpus with a realistic vocabulary (rare terms, hapaxes, stems past the cap), build every Boolean as a balanced two-clause tree so identical texts score identically, and read benchmarks only on a quiet machine with enough rounds — each of the three first versions passed its own checks while being wrong.

- **Date:** 2026-09-26 · **Task:** task-025–031, task-070, task-074 · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/engine/compile.py` (`combine`), `backend/tests/fixtures/corpus/synthetic_5k.py`, `backend/tests/differential/test_differential.py`, `backend/src/openproceedings/engine/parity.py`, `backend/src/openproceedings/export.py`, `backend/tests/bench/report_80k.py`, `docs/results/2026-09-26-bench.md`; commits b16dd4c (balanced trees; 32a3f84 added the two-clause test), 5e89b91 (Zipfian corpus), b5441ef (parity read-back), 4590b33 (BibTeX), d993826 (benchmarks)

## What we set out to do
Finish M2: ranking, exclusion accounting, highlights, the differential suite, tokenizer parity, `op search`/`op export`, and benchmarks against spec 03's budgets.

## What we learned
- A flat Tantivy union of three or more clauses gives identical texts scores an ulp apart, because the union scorer drops a finished clause by swapping the last one into its place, which changes the summation order after a 4,096-document window (evidence: `test_identical_texts_score_equally_across_union_windows`, 4,300 documents; the flat mutant fails it, a 60-document segment test doesn't). A two-operand sum is order-free, so `compile.combine` builds balanced binary trees everywhere and a test pins "no Boolean has more than two clauses".
- The first synthetic 5k corpus had 78 distinct tokens: every query term was in 622+ records, no wildcard reached the 200-term cap, and the refusal branch of the differential could never fire, yet 2,000 examples passed with 0 counterexamples (evidence: task-028 review). A Zipfian pseudo-word vocabulary (6,374 terms, 788 hapaxes, stems past the cap) and trees drawn from the corpus's own dictionary fixed it; the suite's own distribution (refused / empty / 1–3 hits) is now measured in review.
- "Parity" that re-runs the analyzer over stored text only proves the text round-trips; the genuine read-backs are the term dictionary (both directions: a term Tantivy invented or dropped) and a phrase query per field for positions (evidence: an index built with Tantivy's `default` tokenizer passed the stored check and failed the dictionary check).
- BibTeX values need one rule every parser shares: BibTeX counts braces raw while refaudit/biber honour `\{`, so an escaped brace or a trailing backslash made one entry swallow the next while the count check still saw N entries (evidence: the task-030 review's `edge2.py` probe, kept in that session's scratchpad, not the repo; now `test_export.py`'s edge records). Braces now stay only when balanced and unescaped, judged by backslash parity.
- A 20-round p95 is the slowest round. Under other load it read 147 ms for `main-2-pop`'s warm search; quiet, 200 rounds gave 68.7 ms p95 (a separate probe: p95 95 ms, p99 148 ms). The gate's compiled-query memo then brought it to 27 ms p95, and exposed a second trap: a "cold" run that clears one cache but not another is warm (a 77 ms "cold" `match_ids` that is really 10.9 s). Evidence: `docs/results/2026-09-27-bench.md`; task-076.
- Operator math commands mark their name characters JOIN, so an offset rule keyed on "JOIN markup before a word" also caught operator names: `$n\leq5$` gave `5` the span `leq5` (evidence: task-074 review, 171 overlapping texts in a 300k differential). A span-never-overlaps property catches the class.

## Dead ends — don't repeat these
- Trusting a green differential without measuring what it draws: 0 counterexamples over a 78-token corpus meant nothing. Check the node-kind and hit-rate distribution first.
- Filing a performance task from a run taken while tests and reviewers were running (task-075, archived): re-measure quietly before acting.
- Using the reviewer's own "moved only over JOIN" check as the oracle for offsets: the bug's characters were JOIN too. Check the invariant the user sees (spans never overlap), not the mechanism.

## Decisions (and what would change them)
- Balanced binary trees for every Boolean → exact ties, so the id tie-break is real → a Tantivy release whose union sums in a fixed order (then test the flat form again).
- The 80k benchmark corpus is the synthetic generator at 80k with 120–250-word abstracts → reproducible and publishable → the real corpus becoming redistributable (decision-004, M6).
- The bench gate compares minimum times (`min:20%`) → least moved by runner noise → false failures on CI despite that.

## Follow-ups
- [ ] task-073 — highlights within the 50-hit page budget (M3, with task-035)
- [ ] task-075 — token spans overlap inside NFKC clusters with a combining slash (M3)
- [ ] task-076 — headroom for warm searches over wildcard phrases at 80k (M4)
- [ ] task-057 — nightly differential@50k in its own job (M4)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/field-weighted-bm25/SKILL.md` and `.claude/agents/ranking-engineer.md` (balanced trees), `.claude/agents/differential-tester.md` (corpus, regression recipe), `.claude/skills/tantivy-indexing/SKILL.md` (what parity reads back), `.claude/agents/performance-profiler.md` (quiet machine, rounds), `.claude/skills/task-hygiene/SKILL.md` (archived ids are reused)
- Test or hook added? — `test_no_compiled_boolean_has_more_than_two_clauses`, `test_identical_texts_score_equally_across_union_windows`, the differential's corpus hash pin, `test_check_parity_reads_positions_back`, `test_token_spans_are_valid_and_never_overlap`, the BibTeX edge records in `test_export.py`
