# Official accepted counts per venue × year × track (coverage gate sources)

This is the cited table behind spec 07 §C's coverage gate (TASK-108; `coverage-reporting` skill). It has one row
per main-track and D&B cell with an official count: ICLR, ICML and NeurIPS main 2013–2025 and NeurIPS D&B 2021–2025
(44 cells, all sourced, from decision-013's 2013 floor), the 2026 rows, and NeurIPS main 1987–2012 (decision-047). Every one of those numbers was read on
2026-09-27 from a public page, on the conference's own site or in its proceedings, with no login.
The 2026 crawl (TASK-178) adds two rows, ICLR 2026 main and ICML 2026 main: 46 rows in all. Both were fetched
and counted on 2026-10-05 by the AI assistant session working for the project owner, which recorded the sha256
of each fetched page below so the count can be repeated. NeurIPS 2026 has published nothing; §Not covered here says so.
Since decision-047 (2026-10-06) the corpus also holds NeurIPS from 1987 and ICML from 1988. The 26 NeurIPS main
rows for 1987–2012 are each year page's own count (`N papers`), read on 2026-10-06 by the crawl that indexed them
(TASK-204): 72 rows in all. ICML 1988–2012 has no row: its records come from the pinned dblp release, a
bibliography, and no ICML statement of accepted counts was found for those years (the official pages of 2001–2012
list papers, but not every year's full set), so those cells are reported, not gated.

**What the 1987–2012 NeurIPS rows check.** Each is the `N papers` the year page states, and the crawl indexes that
same page, so these 26 cells check the crawl against its own listing's stated count (every entry parsed and made a
record), not against an independent statement of accepted papers; their "what it counts" says "the page's own
count", and the coverage report says how many gated cells are of this kind. The same holds for NeurIPS 2013–2020,
whose proceedings index is also the only public count. The sha256 of each year page's text as the crawl cached it
(UTF-8; fetched 2026-10-07 UTC), so the count can be repeated against the very page read:

- NeurIPS 1987: `3e6384327d5de59bc05f4f40b81e7a67854fd4e911f59df8616e7d24c19e28b5` (fetched 2026-10-07)
- NeurIPS 1988: `369aed0c1937226780ffccda049e3d27ef97e021fd87d60bb04d18f5da108fb9` (fetched 2026-10-07)
- NeurIPS 1989: `7f0d77133c07bf4084482cbc451f25a3ec87013955d0bd24f4bcb22eb7e20a56` (fetched 2026-10-07)
- NeurIPS 1990: `c60ed75146205a81bff300d71d7b74283f4f65944b32f9c3f974d10e90a777a6` (fetched 2026-10-07)
- NeurIPS 1991: `42db09d0d308b6778ee95389d9510219dd4c6011d4308e9f03a1d0f07bdbb1f1` (fetched 2026-10-07)
- NeurIPS 1992: `5742a561e84af4865aaa7fb1170de427339ba166e1c4720b009b46022c646058` (fetched 2026-10-07)
- NeurIPS 1993: `82cd6a9d0b927fd6913881a61212b959f679c467510bb30011f8a5418a40342e` (fetched 2026-10-07)
- NeurIPS 1994: `68557afb931db50881dc1d7b9fff1100b3f6bc7814359e567d88189edd3ff256` (fetched 2026-10-07)
- NeurIPS 1995: `51dd5cfdea45503fcf7fdcb37977ec59a5fd54d76aca1ca51c4fc36ddf86b7b4` (fetched 2026-10-07)
- NeurIPS 1996: `0e8e1436764fda1f91d43a91d07264672948eb05b7b522760c4706c009061ca0` (fetched 2026-10-07)
- NeurIPS 1997: `901e63451a97455577224a5174f72903132f6f3a515846a8529f50b0d75e6112` (fetched 2026-10-07)
- NeurIPS 1998: `e0acaabcfcec8e4844c09658c924334ce74133e93ffeb5c2fb4cbdabce288ea2` (fetched 2026-10-07)
- NeurIPS 1999: `4a37cef3815ee97cb2cfa9f3526ec9553d7e7401ddf1fec97b5d4cfd9dba2208` (fetched 2026-10-07)
- NeurIPS 2000: `85cf2d4aa29c064602d93fe39dee7cf0e5244a59a3a091ff5c8cfd5f4d8b134e` (fetched 2026-10-07)
- NeurIPS 2001: `87a5ce6ed1e16b857a66a7ebafe86f2defd847421fad3b7ea4c6447c4e47cff0` (fetched 2026-10-07)
- NeurIPS 2002: `4eeaa1a865f9e7cb64651366e87ab5ee8624643f7a36da40a0b6f67603e985a9` (fetched 2026-10-07)
- NeurIPS 2003: `81681cbfaede49742c57aba71d2d7a57184d58a6b4546b2a6c6a094efb758d98` (fetched 2026-10-07)
- NeurIPS 2004: `45f577b378e2431edbd4ca9193212113dac8aed7bf98ac4eea43541909e2a73d` (fetched 2026-10-07)
- NeurIPS 2005: `55208ab1948369f26ddd6c51b3c397b6a682bb3359bd52cfe0827f563cc0bc5b` (fetched 2026-10-07)
- NeurIPS 2006: `9df3570a1c6d12b2df5ca7f6bb84f2690d0205f83c8d564b09d08aad1c8ed545` (fetched 2026-10-07)
- NeurIPS 2007: `a37b46a90d2c17bed0abe5c5ed4ab02079643e1384b60f25813f3f7b6ce0c066` (fetched 2026-10-07)
- NeurIPS 2008: `67fee009c1fd410d60bc233f510788045922cbf17504a1ceb84b216176d9739a` (fetched 2026-10-07)
- NeurIPS 2009: `a0863b2a70f98427e155b1d624c628afb6727c7eb20a0ef1e1e09ea5ea023e3b` (fetched 2026-10-07)
- NeurIPS 2010: `90fbc045c04f678428f23a963a9ca41c85892f37841322ed3b8e3eff4ecbf9c0` (fetched 2026-10-07)
- NeurIPS 2011: `2da06b422da875c54bd10182ac5813bfc036e7dc548e106cd986a00502441b6b` (fetched 2026-10-07)
- NeurIPS 2012: `e21f89a97f97cc035ba7c0f404bbf03c8fc0de77c04912834658e6587e530828` (fetched 2026-10-07)
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
| ICLR | 2026 | main | 5,351 | papers in the ICLR 2026 proceedings index (5,351 distinct Conference entries; fact sheet announced 5,357, retrospective 5,355) | https://proceedings.iclr.cc/paper_files/paper/2026 | 2026-10-05 |
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
| ICML | 2026 | main | 6,341 | papers on the ICML 2026 virtual-site paper list that link an OpenReview forum (6,554 of its 6,628 posters; the 74 TMLR/JMLR journal-track posters excluded) and are not among the 213 on the site's position-papers listing; both lists counted entry by entry | https://icml.cc/static/virtual/data/icml-2026-orals-posters.json and https://icml.cc/virtual/2026/events/2026-position-papers | 2026-10-05 |
| NeurIPS | 1987 | main | 90 | papers in the NeurIPS 1987 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1987 | 2026-10-06 |
| NeurIPS | 1988 | main | 94 | papers in the NeurIPS 1988 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1988 | 2026-10-06 |
| NeurIPS | 1989 | main | 101 | papers in the NeurIPS 1989 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1989 | 2026-10-06 |
| NeurIPS | 1990 | main | 143 | papers in the NeurIPS 1990 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1990 | 2026-10-06 |
| NeurIPS | 1991 | main | 144 | papers in the NeurIPS 1991 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1991 | 2026-10-06 |
| NeurIPS | 1992 | main | 127 | papers in the NeurIPS 1992 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1992 | 2026-10-06 |
| NeurIPS | 1993 | main | 158 | papers in the NeurIPS 1993 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1993 | 2026-10-06 |
| NeurIPS | 1994 | main | 140 | papers in the NeurIPS 1994 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1994 | 2026-10-06 |
| NeurIPS | 1995 | main | 152 | papers in the NeurIPS 1995 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1995 | 2026-10-06 |
| NeurIPS | 1996 | main | 152 | papers in the NeurIPS 1996 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1996 | 2026-10-06 |
| NeurIPS | 1997 | main | 150 | papers in the NeurIPS 1997 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1997 | 2026-10-06 |
| NeurIPS | 1998 | main | 151 | papers in the NeurIPS 1998 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1998 | 2026-10-06 |
| NeurIPS | 1999 | main | 150 | papers in the NeurIPS 1999 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/1999 | 2026-10-06 |
| NeurIPS | 2000 | main | 152 | papers in the NeurIPS 2000 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2000 | 2026-10-06 |
| NeurIPS | 2001 | main | 197 | papers in the NeurIPS 2001 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2001 | 2026-10-06 |
| NeurIPS | 2002 | main | 207 | papers in the NeurIPS 2002 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2002 | 2026-10-06 |
| NeurIPS | 2003 | main | 198 | papers in the NeurIPS 2003 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2003 | 2026-10-06 |
| NeurIPS | 2004 | main | 207 | papers in the NeurIPS 2004 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2004 | 2026-10-06 |
| NeurIPS | 2005 | main | 207 | papers in the NeurIPS 2005 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2005 | 2026-10-06 |
| NeurIPS | 2006 | main | 204 | papers in the NeurIPS 2006 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2006 | 2026-10-06 |
| NeurIPS | 2007 | main | 217 | papers in the NeurIPS 2007 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2007 | 2026-10-06 |
| NeurIPS | 2008 | main | 250 | papers in the NeurIPS 2008 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2008 | 2026-10-06 |
| NeurIPS | 2009 | main | 262 | papers in the NeurIPS 2009 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2009 | 2026-10-06 |
| NeurIPS | 2010 | main | 292 | papers in the NeurIPS 2010 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2010 | 2026-10-06 |
| NeurIPS | 2011 | main | 306 | papers in the NeurIPS 2011 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2011 | 2026-10-06 |
| NeurIPS | 2012 | main | 370 | papers in the NeurIPS 2012 proceedings index (every accepted paper; the page's own count) | https://proceedings.neurips.cc/paper_files/paper/2012 | 2026-10-06 |
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
- **ICLR 2026:** the proceedings index is published, so rule 1 applies. Its page
  (https://proceedings.iclr.cc/paper_files/paper/2026, fetched once on 2026-10-05, no login; response sha256
  `36eaea5ab6f769b96cdc370bb2c13273822cf7a7253e71c093bdcda451abc023`) lists 5,351 distinct
  `…-Abstract-Conference.html` entries, every one of track `Conference`, and each of the 381 proceedings hashes
  the index's records carry is among them. The row uses 5,351. Two announced figures disagree with it and with
  each other: the final fact sheet (https://media.iclr.cc/Conferences/ICLR2026/ICLR2026_Fact_Sheet.pdf) says
  5,357 accepted of 19,525 submissions (224 orals), and the program chairs' retrospective
  (https://blog.iclr.cc/2026/03/31/a-retrospective-on-the, read 2026-10-05) says 5,355. Like ICLR 2025's
  3,703 against 3,704, the proceedings probably leave out papers withdrawn after acceptance (an inference from
  the counts; no source states it).
- **ICML 2024:** the fact sheet gives the main track only as a rounded figure (over 2,600), and gives 75
  position papers. PMLR v235 has 2,610 papers, and 75 titles start with `Position:`, so v235 includes the
  position papers. The rounded figure fits 2,610 but not 2,535 (2,610 − 75), so the row uses 2,610. The
  index also counts these papers as `main`: spec 01 says ICML 2024 position papers carry
  `ICML.cc/2024/Conference` on OpenReview and have no marker in PMLR. If a later change classifies them as
  `position`, this row must become main-only, and no primary source gives that number.
- **ICML 2025:** the fact sheet gives 3,260 main and 73 position. PMLR v267 has 3,330 papers, with 73 titled
  `Position:`, which leaves 3,257 main. OpenReview also has 3,257 main (facts doc). PMLR does not separate
  the tracks, so rule 2 applies and the row uses 3,260. The difference is 3 papers (0.1%).
- **ICML 2026:** no source announces a main-track accepted count, and PMLR has not published the volume, so
  rule 3 applies: a count of the conference's own lists, fetched and counted on 2026-10-05 by the AI assistant
  session working for the project owner. The virtual-site paper list
  (https://icml.cc/static/virtual/data/icml-2026-orals-posters.json, the data behind
  icml.cc/virtual/2026/papers.html; fetched once on 2026-10-05, no login; sha256
  `83ace3eafd34f521baebe50c4b18bf27b0697cdea7dbf28a8086d3048191627b`) has 6,797 entries: 169 oral events and
  6,628 posters, all poster names distinct. 6,554 posters link a distinct OpenReview forum; the other 74 are
  journal-track posters (TMLR, JMLR) with no OpenReview paper and are not conference papers. The list does not
  mark the track. The site's position-papers listing
  (https://icml.cc/virtual/2026/events/2026-position-papers, fetched once the same day; sha256
  `ad126ae0ec821d4181ad09a21b7e671e349a8652e88c7ead9cb8702a92ba6058`) is headed "213 Events"
  and holds 213 distinct poster links, each an entry of the paper list. The main-track count is the papers on
  the first list that are not on the second: 6,554 − 213 = 6,341. It is a count of two lists, not an announced
  number, and the row says so. Checked against the index on snapshot `2026-10-05-47d4e190ca81`: the 6,554 forum
  ids are exactly the indexed ICML 2026 accepted main and position records (6,341 + 213), and the 213 listed
  position papers are exactly the indexed `position` ones; two further site titles begin with "Position" and
  are main-track by venueid. That agreement (Δ 0) confirms the classification, not the coverage: the
  virtual-site list is generated from OpenReview, the crawl's own upstream, so a paper OpenReview lacks would be
  missing from both. The fact sheet
  (https://media.icml.cc/Conferences/ICML2026/ICML2026_Fact_Sheet.pdf, read 2026-10-05) announces 6,552 accepted
  for main and position together (the program chairs' paper, arXiv:2609.19420, says 24,661 submissions are
  23,918 main plus 743 position and 6,552 the accepted total of both), 2 fewer than the list's 6,554. When PMLR
  publishes the volume, rule 1 replaces this row; until then the fact sheet's 6,552 is the only figure
  independent of OpenReview. A "6,352 of 23,918" figure repeated on secondary sites is not
  from the conference and is not used. Position cells are not gated and have no row; the 213 match is recorded
  here only.
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

2026: NeurIPS 2026 has no row because its main conference is not public yet. The index holds its workshop
submissions and 95 Creative_AI_Track notes (track `other`, status `unknown`), neither gated.

Other tracks are reported on the coverage page but not gated (spec 07 §C), so they have no rows here. These
are position, workshop, competition, Creative AI, Tiny Papers and blog posts. ICML 2013–2023 had no track
split, so each PMLR volume is that year's main cell. For ICLR 2013–2017, "main" means the conference
track, as opposed to the workshop track.
