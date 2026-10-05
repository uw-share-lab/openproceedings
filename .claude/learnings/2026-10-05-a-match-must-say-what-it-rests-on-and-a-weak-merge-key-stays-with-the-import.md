# A match against an index that imported the compared set proves nothing until it says what it rests on, and a merge on a weak key is limited to the import that needs it

**Key lesson:** When an index can hold a record only because the very set you are comparing was imported into it, report for every match whether a crawl holds the record or only the import (a "matched" count is otherwise the import agreeing with itself); and when a merge needs weaker evidence than a title (an identical abstract), allow it only for the imported record that matched nothing, only on text read from that record's own page, and never to join two crawled records.

- **Date:** 2026-10-05 · **Task:** TASK-056, TASK-178, TASK-179 · **Area:** eval, ingest
- **Artifacts:** `backend/src/openproceedings/eval/scholar_compare.py` (`Row.independent`, `Row.abstract_source`), `backend/src/openproceedings/eval/scholar_report.py`, `docs/results/2026-10-05-scholar-comparison.md`, `backend/src/openproceedings/ingest/dedup.py` (`_abstract_group`, `_own_abstract`, `_abstract_aside`), decision-037, commits 8313b3ed, 06e029bc, a0e89046

## What we set out to do
Compare the review's Google Scholar set with one pinned index (spec 07 §B), then rebuild both reports once
the 2026 venues had been crawled, and stop imported copies of crawled papers from standing as second records.

## What we learned
- **Provenance decides what a match means.** Before the 2026 crawl, the index held some venue-years only as
  the import of the Scholar exports themselves. Matching the Scholar set to those records can't fail, so the
  matched total said nothing about coverage for them. The comparison now carries, per row, whether some crawl
  holds the index record or only an imported RIS row, and where its abstract came from; the report prints
  both, and its numbers before and after the crawl are in the two dated reports (commit 8313b3ed). Read
  alongside [a Scholar collection needs its sidecar and a separate corpus](2026-10-02-a-scholar-collection-needs-its-sidecar-and-a-separate-corpus.md).
- **`ris` is a route, not one source.** Two candidates that share only `ris` were refused as "one source's
  two candidates"; they are judged by the forum id and proceedings id they name (06e029bc).
- **An abstract is evidence only under four conditions.** Scholar's title can lose its math or be an earlier
  title, so an imported record that matched nothing merges on (venue, year, abstract key). Review then cut the
  rule down to what it was for (a0e89046): the abstract must be the one scholarmend read from the import's own
  page (a proceedings-id row can carry another page's text); the group holds at most one record that isn't
  imported, so it never bridges two crawled records; it never merges into a rejected or withdrawn note; it
  matches on the whole digest; and a set-aside rival is reported on the output records. Every refusal of the
  title step still holds. This extends
  [a forum link is identity evidence](2026-09-27-forum-link-dedup-is-identity-not-title.md) and
  [a rival that cannot be the listed paper is no rival](2026-09-29-a-rival-that-cannot-be-the-listed-paper-is-no-rival.md).

## Dead ends — don't repeat these
- Reading a high matched count as coverage without asking where the index's records came from.
- A general "same abstract merges" rule: two crawled records with one abstract are a finding for
  `conflicts.csv`, not a merge.

## Decisions (and what would change them)
- Decision-037 (the abstract step and why two `ris` rows are not an ambiguity) → would change if an import
  ever carries abstracts from a source that isn't the record's own page.

## Follow-ups
- Filed by the main session with the batch's follow-up tasks.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `scholar-comparison-protocol` (§What a match rests on), `dedup-rules`
  (step 3 and its own never-merge rules), spec 07 §B, decision-037.
- Test or hook added? — the dedup table and property tests for step 3 and the comparison's provenance rows
  (commits above).
