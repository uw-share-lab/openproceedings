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
