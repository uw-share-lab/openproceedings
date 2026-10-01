# ICLR 2017's 18 workshop copies of rejected papers move from main/rejected to workshop/unknown (TASK-152), 2026-10-01

**Result:** the TASK-152 crawler rule changes exactly 18 records of the 2026-09-29 crawl. They are ICLR 2017
workshop-listing notes whose `content.venue` says `Submitted to ICLR 2017`. Their track and status move from
`main`/`rejected` to `workshop`/`unknown`. ICLR 2017 main/rejected goes from 262 to 244 and workshop/unknown from
190 to 208. Main/accepted stays at 198, which is `official_counts`' ICLR 2017 main. No record is added, removed or
rekeyed. On a query that matches 5 of the 18, the result set and `excluded.total` are unchanged, and those 5 move
from the `status.rejected` bucket to `track.workshop`.

## Why they are copies
The workshop listing (`ICLR.cc/2017/workshop/-/submission`) has 161 notes:

| `content.venue` | notes |
|---|---|
| none (no venue, no venueid) | 108 |
| `ICLR 2017 Invite to Workshop` | 35 |
| `Submitted to ICLR 2017` | 18 |

All 53 notes that have a venue string carry venueid `ICLR.cc/2017/conference`. Each of the 18 shares its title with
a conference-listing note (`ICLR.cc/2017/conference/-/submission`) that also says `Submitted to ICLR 2017`. Each
one's `_bibtex` url names that conference note's forum, for example `rkB_5hEKe` → `ryh_8f9lg`. So the string is the
conference twin's outcome, and the workshop submission's own decision is stated nowhere.

Main/rejected becomes 244, not 245, because the conference listing's 245 `Submitted to ICLR 2017` notes include
`SJUdkecgx`, which is skipped for its empty title (`skipped.no_title: 1`).

Across every v1 listing in the cache, a string names a track other than its listing's in only two groups. One is
these 18. The other is 47 `ICLR 2017 Invite to Workshop` notes on the conference listing, which are each note's own
outcome and stay `workshop`/`unknown`.

## What was run
The cache is a clone (`cp -c`) of the main checkout's `data/cache`, read only. "Before" is `origin/dev`'s
`openreview_v1.py`, at bfa59e4; "after" is the branch's. `<scratch>` is a throwaway directory.
```
uv run --frozen op snapshot build --from <scratch>/cache --out <scratch>/snap-before   # origin/dev code
uv run --frozen op snapshot build --from <scratch>/cache --out <scratch>/snap-after    # branch code
uv run --frozen op snapshot diff <scratch>/snap-before/2026-09-29-333bf918c9b3 <scratch>/snap-after/2026-09-29-97b5096959c6
uv run --frozen op index build --snapshot <snapshot> --out <scratch>/idx-<before|after>
```
The snapshots are `2026-09-29-333bf918c9b3` → `2026-09-29-97b5096959c6`, and the indexes `6508b8cf66ff` →
`fd572dbf394c`. The review round added the venueid limit and the report's `twin_outcome` count. Rebuilt after
that round, the snapshot's `records.jsonl` is byte-identical and its hash is the same. The manifest gains
`twin_outcome: 18` in the ICLR 2017 crawl report.

## `op snapshot diff`
`added []`, `removed []`, `rekeyed {}`, `display_only 0`, `provenance_only 0`. `changed` holds exactly these 18,
each with `[track, status]`:

`op:iclr:2017:` `B1lyFkBKx`, `Bk9mxlSFx`, `BkDDM04Ke`, `BkL7bONFe`, `Bkv9FyHYx`, `By1eEXVFg`, `HJ4-rAVtl`,
`Hk6dkJQFx`, `HyhbYrGYe`, `S1AtgaPug`, `S1dJ1smFg`, `SJOQPR7Yl`, `r1IvyjVYl`, `r1QXQkSYg`, `rJV7l2VFg`,
`rkB_5hEKe`, `rkndY2VYx`, `rySCp-1Yg`.

## Manifest cells (before → after)

| cell | before | after |
|---|---|---|
| ICLR 2017 main/accepted | 198 | 198 |
| ICLR 2017 main/rejected | 262 | 244 |
| ICLR 2017 workshop/unknown | 190 | 208 |
| ICLR 2017 crawl report `unknown_status` | 190 | 208 |
| ICLR 2017 crawl report `twin_outcome` | absent | 18 |

Every other manifest value is identical, apart from the snapshot hash and the build time. `merges.csv` and
`conflicts.csv` are identical too: ICLR 2017 has only `openreview_v1` records, so a new track can't change a merge.

## A query over some of the 18 (AC #3)
```
uv run --frozen op search --index <scratch>/idx-<before|after>/<version> --limit 0 \
  'year:2017 AND (classless OR "combinatorial optimization" OR "confident output" OR "domain adaptation" OR "auxiliary classifier")'
```

| | before (`6508b8cf66ff`) | after (`fd572dbf394c`) |
|---|---|---|
| identified | 29 | 29 |
| removed by default filters | 13 | 13 |
| of which `track: workshop` | 2 | 7 |
| of which `status: rejected` | 11 | 6 |
| screened | 16 | 16 |

The 16 screened ids are the same set: the sha1 of `--ids` output is equal before and after.

## The RIS path
The RIS importer is unchanged, by the lead's decision of 2026-10-01. Feeding PR #47's method to `ris._identity` (the
543 notes with `ICLR.cc/2017/conference`, as scholarmend 0.1.4 claims) gives the same result as before:

| result | notes |
|---|---|
| `main`/`accepted` | 198 |
| `main`/`rejected` | 263, the 245 conference notes plus the 18 copies |
| `workshop`/`unknown` | 82 |

scholarmend's claims don't name a note's submission invitation, so a copy can't be told from a real rejection.
In a snapshot that also holds the v1 crawl, the record merges by forum id, and the crawl's claims win (decision-005).
