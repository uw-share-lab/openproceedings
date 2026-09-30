# Official accepted counts per venue × year × track (coverage gate sources)

This is the cited table behind spec 07 §C's coverage gate (TASK-108; `coverage-reporting` skill). It has
one row per main-track and D&B cell from 2013 (decision-013): ICLR, ICML and NeurIPS main 2013–2025, and
NeurIPS D&B 2021–2025. That is 44 cells, and **all 44 are sourced**. Every number was read on 2026-09-27
from a public page, on the conference's own site or in its proceedings, with no login.
The `official_counts.OFFICIAL_ACCEPTED` machine-readable copy is kept equal to this table by a test, and
`GET /coverage` joins it to each matching cell to compute the gate verdict. This file deliberately holds
exactly one Markdown table so the equality test can read every line starting with `|` as a data row.

**Which number a row uses:**

1. The proceedings index, where one exists and separates the track. It is the final published set, which
   is what the index should hold, and it leaves out papers withdrawn after acceptance.
2. Otherwise, the conference's own announced count for that track (fact sheet, press release or PC blog).
3. Otherwise, a count of the conference's own accepted-paper list (the iclr.cc archive, the virtual-site
   list, or the conference site's track listing).

No row is an estimate, and no row comes from an aggregator. Where sources differ, the row keeps the number
this rule picks, and the other values are listed under §Disagreements. To count a list, the page was
fetched once and its distinct paper entries were counted (by paper id or title).

The denominator is the final proceedings population where one exists. Since TASK-072 (decision-005), the
numerator names the same population wherever reconcile runs: an OpenReview-accepted paper absent from the
crawled proceedings is demoted to `unknown` (`docs/results/2026-09-29-reconcile-real-data.md`). Reconcile
skipped NeurIPS 2021, because its D&B listing states no count, so no NeurIPS 2021 record is demoted.

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
| NeurIPS | 2025 | main | 5,286 | main-track (`conference`) papers in the published vol38 proceedings companion; D&B and position excluded | https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference | 2026-09-27 |
| NeurIPS | 2021 | datasets_benchmarks | 174 | D&B papers in the 2021 D&B proceedings, round 1 (66) + round 2 (108); equals the fact sheet | https://datasets-benchmarks-proceedings.neurips.cc/paper/2021 | 2026-09-27 |
| NeurIPS | 2022 | datasets_benchmarks | 163 | D&B papers in the NeurIPS 2022 proceedings index (equals the fact sheet) | https://proceedings.neurips.cc/paper_files/paper/2022 | 2026-09-27 |
| NeurIPS | 2023 | datasets_benchmarks | 322 | D&B papers in the NeurIPS 2023 proceedings index (equals the fact sheet) | https://proceedings.neurips.cc/paper_files/paper/2023 | 2026-09-27 |
| NeurIPS | 2024 | datasets_benchmarks | 459 | D&B papers in the NeurIPS 2024 proceedings index (fact sheet announced 460) | https://proceedings.neurips.cc/paper_files/paper/2024 | 2026-09-27 |
| NeurIPS | 2025 | datasets_benchmarks | 497 | D&B (`datasets_and_benchmarks_track`) papers in the published vol38 proceedings companion | https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference | 2026-09-27 |

## Disagreements between sources

Each row keeps the value the rule above picks. Three disagreements are larger than 1%: ICLR 2013 (1 paper
out of 24), ICLR 2023's virtual-site list, and NeurIPS 2025 D&B's former virtual-site count.

- **ICLR 2013:** the iclr.cc list has 24 conference papers. OpenReview decisions give 23: 67 submissions,
  minus 32 workshop, minus 12 reject (`docs/research/2026-09-27-openreview-and-proceedings-facts.md`). The
  row uses 24, the conference's own list. One paper is 4% of this cell, so the gate will flag any mismatch
  here. Resolved: the paper is "Factorized Topic Models" (`op:iclr:2013:11y_SldoumvZl`), on the conference list
  but a workshop poster on OpenReview. The record keeps OpenReview's decision, and the cell is an owner-accepted
  exception at exactly 23 vs 24 ([decision-016](../../backlog/decisions/decision-016%20-%20ICLR-2013-main-is-an-owner-accepted-coverage-exception-keep-OpenReviews-workshop-decision-for-Factorized-Topic-Models-TASK-054.md),
  `coverage-causes.toml`).
- **ICLR 2018:** the virtual-site list has 336. The OpenReview decision notes give 337 (23 oral + 314 poster,
  facts doc). The row uses 336. The extra one is ELMo (`S1p31z-Ab`, `Accept (Poster)`), whose pdf is also listed
  as the withdrawn note `SJTCsqMUf`: accepted, then withdrawn, not presented at ICLR 2018. Since TASK-113
  (decision-020) its status is `unknown` with an `unresolved:openreview_v1` row, and the index holds 336.
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
  strings say 2,630 accepted (facts doc). The gap was 300 papers OpenReview v1 lists twice (297 of them
  accepted), which the v1 crawler now collapses (TASK-125, facts doc); the index then had 2,335 accepted
  (`2026-09-29-coverage.md`). That +1 was one paper counted twice: "Stochastic Online Linear Regression: the
  Forward Algorithm to Replace Ridge" was `op:neurips:2021:rDdb26AQ0SO` (OpenReview only) and
  `op:neurips:2021:nips-cca289d2a4acd14c1cd9a84ffb41dd29` (proceedings only), kept apart because OpenReview
  also lists it as `W6e384Lkjbw`, a note with no venue. The crawler now drops that silent twin for its accepted
  note (TASK-132, facts doc), the pair merges, and the index has 2,334 accepted, the official number (a scratch
  build of 2026-09-30). The official number itself is not in doubt.
- **NeurIPS 2022 main:** the proceedings have 2,671, the same as OpenReview's `NeurIPS 2022 Accept`. The fact
  sheet gives 2,905 accepted papers but does not say which tracks that total covers. It is larger than main
  plus D&B (2,834), so the row uses the proceedings.
- **NeurIPS 2024:** the proceedings have 4,034 main and 459 D&B, and the fact sheet announced 4,037 and 460.
  OpenReview has 4,035 main (facts doc); the extra one, DEX (`op:neurips:2024:ftqjwZQz10`), is on no
  proceedings listing and is `unknown` since TASK-072. The conference site's D&B listing has 460 ids, and 459
  of them have a title. The rows use the proceedings.
- **NeurIPS 2025:** the base proceedings page lists Creative AI (64 papers) and links the published vol38
  companion, whose 5,823 paper entries split into 5,286 main, 497 D&B and 40 position. The fact sheet and
  PC chairs' blog announced 5,290 main (of 21,575 submissions):
  https://blog.neurips.cc/2025/09/30/reflections-on-the-2025-review-process-from-the-program-committee-chairs/.
  It was read through the Wayback Machine because the blog blocks scripted fetches. The former virtual-site
  D&B listing had 487 distinct papers, 10 fewer than the proceedings (about 2.0%); rule 1 therefore selects
  497. Reproduction: download the companion page, whose response SHA-256 was
  `48c2de5e5acae991a8b88eaa00174387a7ce066efeb337e30593989bd5015c9a`, then count `<li>` elements by
  `data-track`; the result is `conference=5286`, `datasets_and_benchmarks_track=497`,
  `position_paper_track=40`.

Cross-checks that agree:

- ICLR 2022: fact sheet 1,095 = virtual-site list 1,095.
- ICML 2023: PMLR 1,828 = OpenReview 1,828.
- NeurIPS 2020: fact sheet = proceedings (1,898).
- NeurIPS 2021 D&B: fact sheet = proceedings (174).
- NeurIPS 2022 D&B: fact sheet 163 = proceedings 163.
- NeurIPS 2023: fact sheet = proceedings (3,218 main, 322 D&B), and the conference site's D&B listing also
  has 322.

## Former ICLR acceptance gaps

OpenReview alone cannot establish acceptance for ICLR 2014–2016: the 2014 notes carry no decision, 2015
has no group, and the 2016 conference track is absent. TASK-096 resolved those cells with the public ICLR
archive's accepted-conference listings (`ingest/sources/iclr.py`). Their 35, 31 and 80 unique targets match
the official main-track counts above, so these cells are now ordinary ±1% gate cells rather than crawl gaps.

## Not covered here

Other tracks are reported on the coverage page but not gated (spec 07 §C), so they have no rows here. These
are position, workshop, competition, Creative AI, Tiny Papers and blog posts. ICML 2013–2023 had no track
split, so each PMLR volume is that year's main cell. For ICLR 2013–2017, "main" means the conference
track, as opposed to the workshop track.
