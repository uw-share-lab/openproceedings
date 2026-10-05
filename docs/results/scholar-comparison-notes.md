- **The Scholar set.** `mended.ris` is the Trust-Evals review's Scholar export after scholarmend: the 1,834 records of
  the review's `clean.ris` (sha256 `576c695db2361bdff68841d0f020f78b38647e9c8365c0bb5953f3c8aeb46f50`, which already
  holds the 443 records of the 2020–2024 delta), with the same titles, one for one. It is used in place of
  `clean.ris`, which spec 07 §B names, because scoping needs a year: `clean.ris` has no year on 99 records and gives
  1,059 the year 2026, Scholar's own guess. scholarmend replaced those with the year of the paper's proceedings
  or OpenReview page, and each truncated venue string with the venue's short name where a page settled it. It is a
  fixed export, dated by its Publish or Perish query dates (2026-09-19 and 2026-09-23); nothing was fetched from
  Scholar for this report.
- **Which string the set answers.** The review exported one file per `source:` value of `main-7-most-updated`, so
  the set is Scholar's answer to that string. `main-7-dollar` is the same string with `$` on six words and
  `year:2020..2026`, as it was run here on 2026-09-30; `main-2-pop` is the review's Publish or Perish variant. For
  those two the Scholar set is still `main-7-most-updated`'s: their sections show what each string keeps, drops
  and adds against the records the review already holds, not what Scholar returned for them.
- **Scholar's cap.** The review's 17 raw exports hold between 7 and 639 records each, all under Scholar's 1,000,
  so no search was cut at the cap. The set itself is de-duplicated across exports, which is why its largest
  query-date group is smaller.
- **Earlier counts.** On index `05a0541717f6` (snapshot `2026-09-29-d552baa07aed`, no 2026 crawl) the
  2026-09-30 runs gave 27 records for the literal string and 67 for the `$` string, 51 of them among the
  review's records and 16 not; `docs/results/2026-10-04-scholar-comparison.md` reproduces all four on that
  index (`main-7-most-updated` limited to 2020–2026 is the literal string). An index built after the 2026 crawl
  holds more records, so its counts are larger.
- **The set is in the index.** Every snapshot so far was built with the set imported as its `ris` source
  (1,805 of the set's records, their ids from scholarmend's claims). Where a crawl holds the paper too, the two
  are merged and the record has an independent source; where none does, the index record is the import alone.
  On the 2026-09-29 snapshot that was 530 of the matched papers, nearly all of them 2026, which no crawl had
  reached (`docs/results/2026-10-04-scholar-comparison.md`). The 2026 OpenReview crawl (TASK-178) merged all but
  7, and the dedup fix of TASK-179 merged those. "What the matches rest on" counts the two kinds apart for the
  index a report ran on.
- **The superseded run of 2026-10-05.** A report of this date first ran on index `5ec5231adae2` (snapshot
  `2026-10-05-47d4e190ca81`, 133,632 records), the first build after the 2026 crawl. That snapshot still held 7
  imported records as unmerged second copies of crawled papers (ICLR 2024 ×1, 2025 ×3, 2026 ×3), and lacked 4
  papers refused for a control character in their title. TASK-179 and TASK-180 fixed both, the snapshot was
  rebuilt (`2026-10-05-10b5a205a63f`, 133,629 records), and that report was replaced by this one. On the
  superseded index 1,800 matched papers rested on a crawled record and 7 on the import alone; the class counts
  differed only by those 7.
- **Matching.** This report matches the set by URL and title, as it would any RIS file, not by the import's
  ids.
- **Who made the human calls.** The 48 calls in the review file of the 2026-10-05 run were made on 2026-10-05 by an
  AI assistant at the project owner's direction, not by an independent reviewer; the file's `reviewer_role`
  says so on each row, and each `note` gives the evidence. Where this report says "a person", read it with
  that in mind. The checks behind them: for the 12 `scholar_missed` papers, no record with the title (exact,
  prefix or near match) in `mended.ris` or in the review's 20 other Scholar export files; for the 5 records with no
  venue string, the same title, year and authors as the named index record, then the class the tool gives once
  the venue is restored; for the 3 `coverage_gap` records, the venue named by Crossref or by the conference's
  own page (a Springer LNCS volume of another conference, an IEEE conference of another name, and a NeurIPS 2022
  tutorial). No spot-check row has a call. A reviewer who repeats any of these calls should replace the role on
  that row.
