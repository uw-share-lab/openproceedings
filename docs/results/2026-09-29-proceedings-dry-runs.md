# First live dry runs of the proceedings crawlers, and the NeurIPS 2021 D&B id collision (TASK-118), 2026-09-29

**Result:** every listing's entries match the page's own count. For every gated cell the listing can
settle, they also match the official count in `coverage-sources.md`: NeurIPS main 2013–2025, NeurIPS D&B
2021–2025, and ICML 2013–2023 in PMLR. ICML 2024–2025 PMLR entries are track `unknown` until OpenReview
supplies the track. v267's 3,330 include the 73 position papers that the official main count of 3,260
leaves out (3,257 main + 73 position on OpenReview, per the coverage-reporting skill). The NeurIPS 2025
year page's 64 `other` entries belong to no gated cell. One listing lost papers after the
count check: **NeurIPS 2021 D&B planned 120 of 174**, because 54 different papers shared a native id. That
was fixed by TASK-118. After the fix the same listing plans 174 of 174.

## What was run
A dry run reads only the index pages and reports what a crawl would fetch (no abstract pages):
```
uv run --project backend op ingest neurips --year 2013-2025 --dry-run   # 15 index requests
uv run --project backend op ingest pmlr --year 2013-2025 --dry-run      # 13 volume pages
```
`listed` is the entries parsed. `stated` is the page's own count. `planned by track` is what would be
crawled, after skips. The NeurIPS table is the run **before** the TASK-118 fix.

| venue | year | listing | listed | stated | planned by track | skipped | official (coverage-sources.md) |
|---|---|---|---|---|---|---|---|
| NeurIPS | 2013 | https://proceedings.neurips.cc/paper_files/paper/2013 | 360 | 360 | main 360 | — | main 360 |
| NeurIPS | 2014 | https://proceedings.neurips.cc/paper_files/paper/2014 | 411 | 411 | main 411 | — | main 411 |
| NeurIPS | 2015 | https://proceedings.neurips.cc/paper_files/paper/2015 | 403 | 403 | main 403 | — | main 403 |
| NeurIPS | 2016 | https://proceedings.neurips.cc/paper_files/paper/2016 | 569 | 569 | main 569 | — | main 569 |
| NeurIPS | 2017 | https://proceedings.neurips.cc/paper_files/paper/2017 | 679 | 679 | main 679 | — | main 679 |
| NeurIPS | 2018 | https://proceedings.neurips.cc/paper_files/paper/2018 | 1,009 | 1009 | main 1,009 | — | main 1,009 |
| NeurIPS | 2019 | https://proceedings.neurips.cc/paper_files/paper/2019 | 1,428 | 1428 | main 1,428 | — | main 1,428 |
| NeurIPS | 2020 | https://proceedings.neurips.cc/paper_files/paper/2020 | 1,898 | 1898 | main 1,898 | — | main 1,898 |
| NeurIPS | 2021 | https://proceedings.neurips.cc/paper_files/paper/2021 | 2,334 | 2334 | main 2,334 | — | main 2,334 |
| NeurIPS | 2021 | https://datasets-benchmarks-proceedings.neurips.cc/paper/2021 | 174 | — | datasets_benchmarks 120 | {"duplicate": 54} | datasets_benchmarks 174 |
| NeurIPS | 2022 | https://proceedings.neurips.cc/paper_files/paper/2022 | 2,834 | 2834 | datasets_benchmarks 163, main 2,671 | — | datasets_benchmarks 163; main 2,671 |
| NeurIPS | 2023 | https://proceedings.neurips.cc/paper_files/paper/2023 | 3,540 | 3540 | datasets_benchmarks 322, main 3,218 | — | datasets_benchmarks 322; main 3,218 |
| NeurIPS | 2024 | https://proceedings.neurips.cc/paper_files/paper/2024 | 4,493 | 4493 | datasets_benchmarks 459, main 4,034 | — | datasets_benchmarks 459; main 4,034 |
| NeurIPS | 2025 | https://proceedings.neurips.cc/paper_files/paper/2025 | 64 | 64 | other 64 | — | — |
| NeurIPS | 2025 | https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference | 5,823 | 5823 | datasets_benchmarks 497, main 5,286, position 40 | — | datasets_benchmarks 497; main 5,286 |
| ICML (PMLR v28) | 2013 | https://proceedings.mlr.press/v28/ | 283 | 283 | main 283 | — | main 283 |
| ICML (PMLR v32) | 2014 | https://proceedings.mlr.press/v32/ | 310 | 310 | main 310 | — | main 310 |
| ICML (PMLR v37) | 2015 | https://proceedings.mlr.press/v37/ | 270 | 270 | main 270 | — | main 270 |
| ICML (PMLR v48) | 2016 | https://proceedings.mlr.press/v48/ | 322 | 322 | main 322 | — | main 322 |
| ICML (PMLR v70) | 2017 | https://proceedings.mlr.press/v70/ | 434 | 434 | main 434 | — | main 434 |
| ICML (PMLR v80) | 2018 | https://proceedings.mlr.press/v80/ | 621 | 621 | main 621 | — | main 621 |
| ICML (PMLR v97) | 2019 | https://proceedings.mlr.press/v97/ | 773 | 773 | main 773 | — | main 773 |
| ICML (PMLR v119) | 2020 | https://proceedings.mlr.press/v119/ | 1,084 | 1,084 | main 1,084 | — | main 1,084 |
| ICML (PMLR v139) | 2021 | https://proceedings.mlr.press/v139/ | 1,183 | 1,183 | main 1,183 | — | main 1,183 |
| ICML (PMLR v162) | 2022 | https://proceedings.mlr.press/v162/ | 1,233 | 1,233 | main 1,233 | — | main 1,233 |
| ICML (PMLR v202) | 2023 | https://proceedings.mlr.press/v202/ | 1,828 | 1,828 | main 1,828 | — | main 1,828 |
| ICML (PMLR v235) | 2024 | https://proceedings.mlr.press/v235/ | 2,610 | 2,610 | unknown 2,610 | — | main 2,610 |
| ICML (PMLR v267) | 2025 | https://proceedings.mlr.press/v267/ | 3,330 | 3,330 | unknown 3,330 | — | main 3,260 |

After the fix (`op ingest neurips --year 2021 --dry-run`, same day): the main listing planned `main 2,334`,
the D&B listing planned `datasets_benchmarks 174`, and neither skipped anything.

## Why 54 of the 174 D&B papers were dropped
The NeurIPS proceedings path hash is md5 of a paper number. For example, the first D&B entry's hash is
`md5("138")`. The main proceedings site never reuses a number, so no other listing above skipped anything
as a duplicate. The 2021 D&B host (`datasets-benchmarks-proceedings.neurips.cc`) numbers round 1 (66
papers), round 2 (108) and the main track separately. The miner deduplicated on `nips-<hash>`, so these
were dropped. Counted over the cached index pages of that run:

| check | count |
|---|---|
| D&B entries / distinct hashes | 174 / 147 |
| hashes in both round 1 and round 2 | 27, **0** with the same title |
| D&B hashes also on 2021 main-track papers | 27, **0** with the same title |

The miner's `count_ok` compares entries with the stated count before any id exists, so it passed. The loss
showed only as `skipped: {"duplicate": 54}`. TASK-118 gives D&B-host papers the id
`nips-<hash>-round1`/`-round2` (`urls.proceedings_native`), which is used by the miner, the RIS importer and
dedup alike. The coverage report (TASK-054) must check each listing's `skipped`, not only `count_ok`.
