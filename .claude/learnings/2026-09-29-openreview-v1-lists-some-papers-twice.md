# OpenReview v1 lists 300 NeurIPS 2021 papers twice, which kept them from merging with the proceedings

**Key lesson:** When a coverage cell is far over its official count, split the cell's records by contributing source (merged / OpenReview-only / proceedings-only) before blaming the source definition. A proceedings-only record with an identical-title twin that is OpenReview-only is a merge dedup refused, and `conflicts.csv` says why.

- **Date:** 2026-09-29 · **Task:** task-125 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_v1.py` (`collapse_duplicate_submissions`), `backend/tests/unit/ingest/test_openreview_v1.py`, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`

## What we set out to do
Explain NeurIPS 2021 main at 2,929 accepted against the official 2,334 (+25.5%) in the first full coverage trial. This is also TASK-054's long-standing "OpenReview 2,630 accepted vs proceedings 2,334, unexplained".

## What we learned
- By source, the cell held 2,036 merged, 595 OpenReview-only and 298 proceedings-only records. All 298 proceedings-only records had an OpenReview-only twin with the same title key, and `conflicts.csv` had 403 `title_key ambiguous_not_merged` rows for them (evidence: the trial snapshot `f2ba9c975ae4`).
- The ambiguity came from OpenReview itself. 297 accepted papers (and 3 rejected ones) appear as two Blind_Submission notes with different ids and numbers (e.g. `-K4tIyQLaY` #292 and `BW2Z6B7S9KZ` #8244) and identical content: title, authors, abstract, keywords, pdf and venue. Only the id in `_bibtex` differs. 2,334 + 297 ≈ 2,630.
- Collapsing them at the crawl (lowest number kept, the rest counted as `duplicate_submission`) takes the cell to 2,335. No other venue-year has any, v1 or v2.
- "Lowest number kept" is a tie-break, not "the original": the NeurIPS 2021 proceedings pages link the kept forum for 177 of the 297 accepted pairs and the dropped one for 120 (e.g. `0hJ-U3aqUDf` #401 kept, `rvKD3iqtBdk` #3462 linked).
- Matching on track and status as well as content matters: ICLR 2018 lists 24 pdfs both as a blind and a withdrawn note, and a looser title/authors/abstract rule would have collapsed about 12 of them.

## Dead ends — don't repeat these
- Reading the +25.5% as "OpenReview accepts papers the proceedings dropped" (the TASK-072 source-definition story). The per-source split disproved it at once.

## Decisions (and what would change them)
- API v1 only: the v2 cache has no identical-pdf notes, and v2's test fixtures clone notes identically. Extend to v2 only if a v2 crawl's `conflicts.csv` shows the same pattern.
- The dropped note is counted, never silent: a non-routine skip in the crawl report and in `op eval coverage`.

## Follow-ups
- [ ] task-126 — dedup refuses title groups where a rejected or track-incompatible OpenReview note shares the title (NeurIPS 2021 D&B's 11 round-1 rejections; 2023/2024 workshop papers)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `docs/specs/01-ingestion.md`, `.claude/skills/openreview-api/SKILL.md`, `.claude/skills/dedup-rules/SKILL.md`, `.claude/skills/logging-standards/SKILL.md`
- Test or hook added? — the collapse tests in `test_openreview_v1.py`

## Addendum — 2026-09-30 (task-132)
**Key lesson:** `unknown` because a note carries no evidence is not a disagreement. Before recording two same-pdf notes as "not the same paper", diff them field by field: missing status evidence alone can't split a paper.

- TASK-125 kept NeurIPS 2021 `W6e384Lkjbw` and `rDdb26AQ0SO` apart as "same pdf but not the same paper by content", and a test row pinned it. A field-level diff of the cached notes shows the same pdf and supplementary sha1s, title, authors, author ids, abstract, keywords, TL;DR and paperhash. Only `venue`/`venueid` (absent on `W6e384Lkjbw`), `_bibtex`, `checklist`, `submission_history*` and `thumbnail` differ. The proceedings page even links `W6e384Lkjbw` (evidence: the offset-0 and offset-1000 Blind_Submission pages and `neurips/pages/ad/adb9a2ae…` in the 2026-09-29 cache).
- Its `unknown` came from absence (NeurIPS 2021 reads status only from `content.venue`), so it contradicted nothing. The crawler now drops such a silent note for its one accepted twin (`collapse_silent_twins`). An offline replay of every v1 venue-year collapses exactly this pair, and NeurIPS 2021 main goes from 2,335 to 2,334.
- The rule is narrow on purpose: only a `status_from="venue"` year, only with both keys absent (an empty or unmapped venue string is evidence nobody can read, not silence), only into an accepted twin, and never with two twins that carry evidence. Mutants of each condition are killed by `test_openreview_v1.py` or `test_openreview_v1_collapse_props.py`.
- Propagated to: `docs/specs/01-ingestion.md`, the `openreview-api`, `dedup-rules` and `neurips-proceedings` skills, the facts doc and `docs/results/coverage-sources.md`.

## Addendum — 2026-09-30 (task-147)
**Key lesson:** When one collapse pass feeds another, the second pass's per-record flags must describe every note the first pass folded into that record, not only the survivor's own note. Test the chain with the first pass's tie-break flipped: if the outcome changes, the flag is stale.

- The Hypothesis property `test_a_collapse_never_folds_two_papers_or_loses_an_acceptance` "flaked" on CI. Its failing example: rule 5 folded Note3 (`venue: ''`, a key, so not silent) into its identical Note2 (no venue key, silent) because Note2 had the lower number. The silent-twin pass then read Note2's `silent` flag, set before rule 5 ran, and folded it into the accepted Note4. With the two numbers swapped, rule 5 keeps Note3 and nothing more collapses. So an arbitrary tie-break decided which records exist (evidence: the `CHAINED` example and `test_a_survivor_that_stands_for_a_speaking_note_is_not_silent`, which swaps the numbers).
- The fix was in the code, not the oracle: rule 5 already said a record with evidence makes the group a choice. `crawl` now drops a survivor from `silent` when it absorbed a non-silent note. An offline replay of all 13 cached v1 crawls gives identical counts and record ids (NeurIPS 2021: 300 rule-5 folds plus `W6e384Lkjbw`), because the one real silent twin absorbed nothing.
- A property that fails only on some random draws is a real bug that is rare in the input space, not a flaky test. Reproduce it with the printed `@reproduce_failure` blob, then pin the input written out as an `@example`.
- Propagated to: the module docstring's rule 5, `docs/specs/01-ingestion.md`, and the `openreview-api` and `dedup-rules` skills.
