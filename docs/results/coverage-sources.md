# Official accepted counts per venue × year × track (coverage gate sources)

This is the cited table behind spec 07 §C's coverage gate (TASK-108; `coverage-reporting` skill). It has
one row per main-track and D&B cell from 2013 (decision-013): ICLR, ICML and NeurIPS main 2013–2025, and
NeurIPS D&B 2021–2025. That is 44 cells, and **all 44 are sourced**. Every number was read on 2026-09-27
from a public page, on the conference's own site or in its proceedings, with no login.
`official_counts.OFFICIAL_ACCEPTED` is the machine-readable copy of this table, and
`tests/unit/test_official_counts.py` fails when the two differ. That test reads every line that starts with
`|` as a table row, so this file holds exactly one table.

**Which number a row uses:**

1. The proceedings index, where one exists and separates the track. It is the final published set, which
   is what the index should hold, and it leaves out papers withdrawn after acceptance.
2. Otherwise, the conference's own announced count for that track (fact sheet, press release or PC blog).
3. Otherwise, a count of the conference's own accepted-paper list (the iclr.cc archive, the virtual-site
   list, or the conference site's track listing).

No row is an estimate, and no row comes from an aggregator. Where sources differ, the row keeps the number
this rule picks, and the other values are listed under §Disagreements. To count a list, the page was
fetched once and its distinct paper entries were counted (by paper id or title).

| venue | year | track | official_accepted | what it counts | source (URL or citation) | accessed |
|---|---|---|---|---|---|---|
| ICLR | 2013 | main | 24 | conference-track papers on the ICLR 2013 accepted list (workshop track excluded) | https://iclr.cc/archive/2013/conference-proceedings.html | 2026-09-27 |
| ICLR | 2014 | main | 35 | conference-track papers on the ICLR 2014 accepted list (workshop track excluded) | https://iclr.cc/archive/2014/conference-proceedings | 2026-09-27 |
| ICLR | 2015 | main | 31 | distinct conference-track papers on the accepted list (11 orals also listed as posters, counted once; workshop papers excluded) | https://iclr.cc/archive/www/doku.php%3Fid=iclr2015:accepted-main.html | 2026-09-27 |
| ICLR | 2016 | main | 80 | conference-track papers on the accepted list: 15 orals + 65 posters (workshop track excluded) | https://iclr.cc/archive/www/doku.php%3Fid=iclr2016:accepted-main.html | 2026-09-27 |
| ICLR | 2017 | main | 198 | conference-track papers in the conference poster sessions C1-C198 (orals included; workshop invitations excluded) | https://iclr.cc/archive/www/doku.php%3Fid=iclr2017:conference_posters.html | 2026-09-27 |
| ICLR | 2018 | main | 336 | conference papers on the ICLR 2018 virtual-site paper list (orals + posters) | https://iclr.cc/virtual/2018/papers.html | 2026-09-27 |
| ICLR | 2019 | main | 501 | conference papers on the ICLR 2019 virtual-site paper list (orals + posters) | https://iclr.cc/virtual/2019/papers.html | 2026-09-27 |
| ICLR | 2020 | main | 687 | conference papers on the ICLR 2020 virtual-site paper list (orals + spotlights + posters) | https://iclr.cc/virtual/2020/papers.html | 2026-09-27 |
| ICLR | 2021 | main | 860 | posters in the fact sheet, one per accepted paper (orals and spotlights included); the virtual-site list also has 860 | https://iclr.cc/media/Press/ICLR_2021_Fact_Sheet.pdf | 2026-09-27 |
| ICLR | 2022 | main | 1,095 | total accepted papers in the fact sheet (orals + spotlights + posters) | https://iclr.cc/media/Press/ICLR_2022_Fact_Sheet.pdf | 2026-09-27 |
| ICLR | 2023 | main | 1,574 | accepted papers in the fact sheet: 91 top-5% + 280 top-25% + 1,203 posters | https://media.iclr.cc/Conferences/ICLR2023/ICLR2023-Fact_Sheet.pdf | 2026-09-27 |
| ICLR | 2024 | main | 2,260 | papers in the ICLR 2024 proceedings index (equals the fact sheet's accepted count); Tiny Papers and blog posts excluded | https://proceedings.iclr.cc/paper_files/paper/2024 | 2026-09-27 |
| ICLR | 2025 | main | 3,703 | papers in the ICLR 2025 proceedings index (fact sheet announced 3,704); blog posts excluded | https://proceedings.iclr.cc/paper_files/paper/2025 | 2026-09-27 |
| ICML | 2013 | main | 283 | papers in PMLR volume 28 (every accepted paper; ICML 2013 had no separate tracks) | https://proceedings.mlr.press/v28/ | 2026-09-27 |
| ICML | 2014 | main | 310 | papers in PMLR volume 32 (every accepted paper) | https://proceedings.mlr.press/v32/ | 2026-09-27 |
| ICML | 2015 | main | 270 | papers in PMLR volume 37 (every accepted paper) | https://proceedings.mlr.press/v37/ | 2026-09-27 |
| ICML | 2016 | main | 322 | papers in PMLR volume 48 (every accepted paper) | https://proceedings.mlr.press/v48/ | 2026-09-27 |
| ICML | 2017 | main | 434 | papers in PMLR volume 70 (every accepted paper) | https://proceedings.mlr.press/v70/ | 2026-09-27 |
| ICML | 2018 | main | 621 | papers in PMLR volume 80 (every accepted paper) | https://proceedings.mlr.press/v80/ | 2026-09-27 |
| ICML | 2019 | main | 773 | papers in PMLR volume 97 (every accepted paper) | https://proceedings.mlr.press/v97/ | 2026-09-27 |
| ICML | 2020 | main | 1,084 | papers in PMLR volume 119 (every accepted paper) | https://proceedings.mlr.press/v119/ | 2026-09-27 |
| ICML | 2021 | main | 1,183 | papers in PMLR volume 139 (every accepted paper) | https://proceedings.mlr.press/v139/ | 2026-09-27 |
| ICML | 2022 | main | 1,233 | papers in PMLR volume 162 (every accepted paper) | https://proceedings.mlr.press/v162/ | 2026-09-27 |
| ICML | 2023 | main | 1,828 | papers in PMLR volume 202 (every accepted paper) | https://proceedings.mlr.press/v202/ | 2026-09-27 |
| ICML | 2024 | main | 2,610 | papers in PMLR volume 235, including the 75 position papers (fact sheet), which ICML 2024 did not publish as a separate track | https://proceedings.mlr.press/v235/ | 2026-09-27 |
| ICML | 2025 | main | 3,260 | main-track accepted papers in the fact sheet; the 73 position papers are counted separately | https://media.icml.cc/Conferences/ICML2025/ICML2025_Fact_Sheet.pdf | 2026-09-27 |
| NeurIPS | 2013 | main | 360 | papers in the NeurIPS 2013 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2013 | 2026-09-27 |
| NeurIPS | 2014 | main | 411 | papers in the NeurIPS 2014 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2014 | 2026-09-27 |
| NeurIPS | 2015 | main | 403 | papers in the NeurIPS 2015 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2015 | 2026-09-27 |
| NeurIPS | 2016 | main | 569 | papers in the NeurIPS 2016 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2016 | 2026-09-27 |
| NeurIPS | 2017 | main | 679 | papers in the NeurIPS 2017 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2017 | 2026-09-27 |
| NeurIPS | 2018 | main | 1,009 | papers in the NeurIPS 2018 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2018 | 2026-09-27 |
| NeurIPS | 2019 | main | 1,428 | papers in the NeurIPS 2019 proceedings index (every accepted paper) | https://proceedings.neurips.cc/paper_files/paper/2019 | 2026-09-27 |
| NeurIPS | 2020 | main | 1,898 | papers in the NeurIPS 2020 proceedings index (equals the 2020 fact sheet) | https://proceedings.neurips.cc/paper_files/paper/2020 | 2026-09-27 |
| NeurIPS | 2021 | main | 2,334 | main-track papers in the NeurIPS 2021 proceedings index (equals the fact sheet); D&B is on its own site | https://proceedings.neurips.cc/paper_files/paper/2021 | 2026-09-27 |
| NeurIPS | 2022 | main | 2,671 | main-track (Conference) papers in the NeurIPS 2022 proceedings index; D&B excluded | https://proceedings.neurips.cc/paper_files/paper/2022 | 2026-09-27 |
| NeurIPS | 2023 | main | 3,218 | main-track (Conference) papers in the NeurIPS 2023 proceedings index (equals the fact sheet); D&B excluded | https://proceedings.neurips.cc/paper_files/paper/2023 | 2026-09-27 |
| NeurIPS | 2024 | main | 4,034 | main-track (Conference) papers in the NeurIPS 2024 proceedings index (fact sheet announced 4,037); D&B excluded | https://proceedings.neurips.cc/paper_files/paper/2024 | 2026-09-27 |
| NeurIPS | 2025 | main | 5,290 | main-track accepted papers in the fact sheet (the PC chairs' blog gives the same); D&B and position tracks excluded | https://media.neurips.cc/Conferences/NeurIPS2025/press/NeurIPS2025-Fact_Sheet.pdf | 2026-09-27 |
| NeurIPS | 2021 | datasets_benchmarks | 174 | D&B papers in the 2021 D&B proceedings, round 1 (66) + round 2 (108); equals the fact sheet | https://datasets-benchmarks-proceedings.neurips.cc/paper/2021 | 2026-09-27 |
| NeurIPS | 2022 | datasets_benchmarks | 163 | D&B papers in the NeurIPS 2022 proceedings index (equals the fact sheet) | https://proceedings.neurips.cc/paper_files/paper/2022 | 2026-09-27 |
| NeurIPS | 2023 | datasets_benchmarks | 322 | D&B papers in the NeurIPS 2023 proceedings index (equals the fact sheet) | https://proceedings.neurips.cc/paper_files/paper/2023 | 2026-09-27 |
| NeurIPS | 2024 | datasets_benchmarks | 459 | D&B papers in the NeurIPS 2024 proceedings index (fact sheet announced 460) | https://proceedings.neurips.cc/paper_files/paper/2024 | 2026-09-27 |
| NeurIPS | 2025 | datasets_benchmarks | 487 | distinct papers on the conference site's D&B track listing; no announced count exists and the proceedings are not yet published | https://neurips.cc/virtual/2025/events/datasets-benchmarks-2025 | 2026-09-27 |

## Disagreements between sources

Each row keeps the value the rule above picks. Only two disagreements are larger than 1%: ICLR 2013 (1
paper out of 24) and ICLR 2023's virtual-site list.

- **ICLR 2013:** the iclr.cc list has 24 conference papers. OpenReview decisions give 23: 67 submissions,
  minus 32 workshop, minus 12 reject (`docs/research/2026-09-27-openreview-and-proceedings-facts.md`). The
  row uses 24, the conference's own list. One paper is 4% of this cell, so the gate will flag any mismatch
  here. Resolve it by title when the ICLR v1 crawl runs.
- **ICLR 2018:** the virtual-site list has 336. The OpenReview decision notes give 337 (23 oral + 314 poster,
  facts doc). The row uses 336. One paper may have been withdrawn after acceptance; this is not verified.
- **ICLR 2019:** the virtual-site list has 501. No count announced on iclr.cc was found (the 2019 press page
  has no numbers). Secondary sites quote 502 (24 oral + 478 poster), but no primary source for it was found.
- **ICLR 2021:** the fact sheet's 860 posters equal the virtual-site list (860). OpenReview has 859 accepted
  venue notes, plus 1 withdrawn note that carries `ICLR 2021 Poster` (facts doc).
- **ICLR 2023:** the fact sheet gives 1,574 (91 + 280 + 1,203). OpenReview has 1,573 (90 + 281 + 1,202, facts
  doc). The virtual-site list has 1,584, which is 10 more than the fact sheet; those 10 extra entries were not
  identified. The row uses the fact sheet.
- **ICLR 2024:** the proceedings (2,260) equal the fact sheet (2,260). The virtual-site list has 2,296
  because it lists other entries as well, and it is not used.
- **ICLR 2025:** the proceedings have 3,703, the same as OpenReview (3,703, facts doc). The fact sheet
  announced 3,704. The row uses 3,703.
- **ICML 2024:** the fact sheet gives the main track only as a rounded figure (over 2,600), and gives 75
  position papers. PMLR v235 has 2,610 papers, and 75 titles start with `Position:`, so v235 includes the
  position papers. The rounded figure fits 2,610 but not 2,535 (2,610 − 75), so the row uses 2,610. The
  index also counts these papers as `main`: spec 01 says ICML 2024 position papers carry
  `ICML.cc/2024/Conference` on OpenReview and have no marker in PMLR. If a later change classifies them as
  `position`, this row must become main-only, and no primary source gives that number.
- **ICML 2025:** the fact sheet gives 3,260 main and 73 position. PMLR v267 has 3,330 papers, with 73 titled
  `Position:`, which leaves 3,257 main. OpenReview also has 3,257 main (facts doc). PMLR does not separate
  the tracks, so rule 2 applies and the row uses 3,260. The difference is 3 papers (0.1%).
- **NeurIPS 2021 main:** the proceedings (2,334) equal the fact sheet (2,334). The OpenReview v1 `venue`
  strings say 2,630 accepted (facts doc). That gap is unexplained and is TASK-054's to resolve. The official
  number itself is not in doubt.
- **NeurIPS 2022 main:** the proceedings have 2,671, the same as OpenReview's `NeurIPS 2022 Accept`. The fact
  sheet gives 2,905 accepted papers but does not say which tracks that total covers. It is larger than main
  plus D&B (2,834), so the row uses the proceedings.
- **NeurIPS 2024:** the proceedings have 4,034 main and 459 D&B, and the fact sheet announced 4,037 and 460.
  OpenReview has 4,035 main (facts doc). The conference site's D&B listing has 460 ids, and 459 of them have
  a title. The rows use the proceedings.
- **NeurIPS 2025:** the proceedings list only the Creative AI track so far (64 papers on 2026-09-27). The
  main-track count comes from the fact sheet. The PC chairs' blog gives the same 5,290 (of 21,575
  submissions):
  https://blog.neurips.cc/2025/09/30/reflections-on-the-2025-review-process-from-the-program-committee-chairs/.
  It was read through the Wayback Machine because the blog blocks scripted fetches. For D&B, the chairs'
  blog gives 1,995 submissions but no accepted count, and the fact sheet gives none. The D&B row (487) is
  therefore a count of the conference site's own D&B track listing (rule 3). When the proceedings are
  published, replace it with their count if the two differ.

Cross-checks that agree:

- ICLR 2022: fact sheet 1,095 = virtual-site list 1,095.
- ICML 2023: PMLR 1,828 = OpenReview 1,828.
- NeurIPS 2020: fact sheet = proceedings (1,898).
- NeurIPS 2021 D&B: fact sheet = proceedings (174).
- NeurIPS 2022 D&B: fact sheet 163 = proceedings 163.
- NeurIPS 2023: fact sheet = proceedings (3,218 main, 322 D&B), and the conference site's D&B listing also
  has 322.

## Cells with a count the index cannot reach yet

The gate compares each row with the index's `status:accepted` records in that cell, and it does not tell a
missing source apart from a crawl bug. The three rows below have an official count, but spec 01 has no
source for accepted status in that year. Each of these cells will show ✗, with the cause "crawl gap",
until TASK-096 adds a source (decision-013). They stay in the table because a gap is reported, never
hidden.

- ICLR 2014 (35): the OpenReview notes carry no decision, so the records are indexed as `status:unknown`.
- ICLR 2015 (31): OpenReview has no group for this year.
- ICLR 2016 (80): the conference track is not on OpenReview; only the workshop track is.

## Not covered here

Other tracks are reported on the coverage page but not gated (spec 07 §C), so they have no rows here. These
are position, workshop, competition, Creative AI, Tiny Papers and blog posts. ICML 2013–2023 had no track
split, so each PMLR volume is that year's main cell. For ICLR 2013–2017, "main" means the conference
track, as opposed to the workshop track.
