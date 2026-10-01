# ICLR 2017's 18 workshop copies of rejected papers move from main/rejected to workshop/unknown (TASK-152), 2026-10-01

**Result:** the TASK-152 crawler rule changes exactly 18 records of the 2026-09-29 crawl. They are ICLR 2017
workshop-listing notes whose `content.venue` says `Submitted to ICLR 2017`, and they move from `main`/`rejected` to
`workshop`/`unknown`. As a result:

- ICLR 2017 main/rejected goes from 262 to 244.
- ICLR 2017 workshop/unknown goes from 190 to 208.
- ICLR 2017 main/accepted stays at 198, which is `official_counts`' ICLR 2017 main.
- No record is added, removed or rekeyed.

Under the default filters, the result set and `excluded.total` are unchanged. A matched copy moves from the
`status.rejected` bucket to `track.workshop`. The section on non-default filters below covers what changes when a
user writes their own track filter.

## Why they are copies
`<cache>` is the main checkout's `data/cache`, read only. `tally.py` reads both 2017 listing pages from it:

```python
import collections, glob, json, re, sys
cache = sys.argv[1]
pages = {json.load(open(f))["key"]: json.load(open(f))["payload"]["json"]
         for f in glob.glob(f"{cache}/openreview/v1/http/*/*.json")}
def notes(inv):
    [body] = [b for k, b in pages.items() if f"invitation={inv}&" in k]
    return [n for n in body["notes"] if n["id"] == n["forum"]]
ws, conf = notes("ICLR.cc/2017/workshop/-/submission"), notes("ICLR.cc/2017/conference/-/submission")
key = lambda n: re.sub(r"\W", "", (n["content"].get("title") or "").lower())
by_title = {key(n): n for n in conf}
print("workshop", len(ws), dict(collections.Counter(n["content"].get("venue") for n in ws)))
print("conference", len(conf), dict(collections.Counter(n["content"].get("venue") for n in conf)))
for v in ("Submitted to ICLR 2017", "ICLR 2017 Invite to Workshop"):
    grp = [n for n in ws if n["content"].get("venue") == v]
    twin = [by_title.get(key(n)) for n in grp]
    bib = [re.search(r"forum\?id=([\w-]+)", n["content"].get("_bibtex") or "") for n in grp]
    same = sum(t is not None and b is not None and b.group(1) == t["id"] for t, b in zip(twin, bib))
    print(v, "title twins:", sum(t is not None for t in twin), "_bibtex names the title twin:", same)
```

Run with `uv run --frozen python tally.py <cache>`, it prints:

```
workshop 161 {None: 108, 'ICLR 2017 Invite to Workshop': 35, 'Submitted to ICLR 2017': 18}
conference 490 {'ICLR 2017 Poster': 183, 'ICLR 2017 Invite to Workshop': 47, 'Submitted to ICLR 2017': 245, 'ICLR 2017 Oral': 15}
Submitted to ICLR 2017 title twins: 18 _bibtex names the title twin: 18
ICLR 2017 Invite to Workshop title twins: 34 _bibtex names the title twin: 0
```

Each of the 18 shares its title with a conference-listing note that also says `Submitted to ICLR 2017`, and each
one's `_bibtex` url names that note's forum, for example `rkB_5hEKe` → `ryh_8f9lg`. So the string is the conference
twin's outcome. Nothing in the data states the workshop submission's own decision.

Main/rejected ends at 244, not 245, because one of the conference listing's 245 `Submitted to ICLR 2017` notes,
`SJUdkecgx`, is skipped for its empty title (`skipped.no_title: 1`).

**Which listings the rule can touch.** `scan.py` checks every v1 listing page in the cache. For each listing in
`openreview_v1.ADAPTERS`, it takes every submission note whose `content.venue` parses through `classify_v1_venue`
and counts the notes whose string names a track other than the listing's:

```python
import collections, glob, json, sys
from openproceedings.ingest.classify import classify_v1_venue
from openproceedings.ingest.sources.openreview_v1 import ADAPTERS
listings = {l.invitation: l for ad in ADAPTERS.values() for l in ad.listings}
c = collections.Counter()
for f in glob.glob(f"{sys.argv[1]}/openreview/v1/http/*/*.json"):
    d = json.load(open(f))
    inv = d["key"].split("invitation=")[1].split("&")[0] if "invitation=" in d["key"] else None
    if inv not in listings:
        continue
    l = listings[inv]
    for n in d["payload"]["json"].get("notes", []):
        v = (n.get("content") or {}).get("venue")
        if n.get("id") == n.get("forum") and isinstance(v, str) and v:
            b = classify_v1_venue(v)
            if b.parsed and b.track != l.track:
                c[(inv, l.role, l.track, v, b.track, b.status)] += 1
for k, v in sorted(c.items()):
    print(v, k)
```

`uv run --frozen python scan.py <cache>` finds only two groups:

```
47 ('ICLR.cc/2017/conference/-/submission', 'submission', 'main', 'ICLR 2017 Invite to Workshop', 'workshop', 'unknown')
18 ('ICLR.cc/2017/workshop/-/submission', 'submission', 'workshop', 'Submitted to ICLR 2017', 'main', 'rejected')
```

The rule reads only a `main` outcome on a non-main listing as the twin's, so only the 18 are affected. The 47 are
each note's own outcome and stay `workshop`/`unknown`.

## What was run
The cache was cloned (`cp -c`) into a scratch directory, `<scratch>/cache`.

- **Before:** `origin/dev` at bfa59e4 (`backend/src` is unchanged between bfa59e4 and d905416, the base the branch
  was rebased onto). The build ran in the branch's worktree with the module swapped in:
  `git show origin/dev:backend/src/openproceedings/ingest/sources/openreview_v1.py > <that file>`.
- **After:** the branch at 2cea31f, rebuilt at 17ebe82 after review round 1.

```
uv run --frozen op snapshot build --from <scratch>/cache --out <scratch>/snap-<before|after>
uv run --frozen op snapshot diff <scratch>/snap-before/2026-09-29-333bf918c9b3 <scratch>/snap-after/2026-09-29-97b5096959c6
uv run --frozen op index build --snapshot <scratch>/snap-<before|after>/<snapshot> --out <scratch>/idx-<before|after>
shasum <scratch>/snap-*/*/records.jsonl
```

| build | snapshot | index | `records.jsonl` sha1 |
|---|---|---|---|
| before | `2026-09-29-333bf918c9b3` | `6508b8cf66ff` | `d6878a177bf92e74f04166870c6b91938da0ad40` |
| after (2cea31f) | `2026-09-29-97b5096959c6` | `fd572dbf394c` | `b3eabdfa980d817c7e898753d39b02c17dc0c071` |
| after (17ebe82) | `2026-09-29-97b5096959c6` | `fd572dbf394c` | `b3eabdfa980d817c7e898753d39b02c17dc0c071` |

Review round 1 narrowed the rule to venueids that name no track and added the report's `twin_outcome` count. The
records were byte-identical afterwards. The manifest gained `twin_outcome: 18` in the ICLR 2017 crawl report.

This "before" snapshot was rebuilt from the cache for this comparison. It is not the published coverage snapshot
(`2026-09-29-4cd2bba17cad`, index `b170674bcf49`). That snapshot's coverage report stays correct for its own index.
The next coverage run will show ICLR 2017 unknown-status 208 instead of 190.

## `op snapshot diff`
The diff reports `added []`, `removed []`, `rekeyed {}`, `display_only 0` and `provenance_only 0`. `changed` holds
exactly these 18, each with `[track, status]`:

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
`conflicts.csv` are byte-identical too: ICLR 2017 has only `openreview_v1` records, so a new track can't change a
merge.

## A query over some of the 18 (TASK-152 AC #3)
```
Q='year:2017 AND (classless OR "combinatorial optimization" OR "confident output" OR "domain adaptation" OR "auxiliary classifier")'
uv run --frozen op search --index <scratch>/idx-<before|after>/<version> --limit 0 "$Q"
uv run --frozen op search --index <scratch>/idx-<before|after>/<version> --ids "$Q" | grep '^op:' | shasum
```

| | before (`6508b8cf66ff`) | after (`fd572dbf394c`) |
|---|---|---|
| identified | 29 | 29 |
| removed by default filters | 13 | 13 |
| of which `track: workshop` | 2 | 7 |
| of which `status: rejected` | 11 | 6 |
| unclassified (track or status unknown) | 0 | 0 |
| screened | 16 | 16 |
| `--ids` sha1 | `775269789905a06873f21cba5468f3a7c250f873` | `775269789905a06873f21cba5468f3a7c250f873` |

## What a search sees
Spec 03 §Exclusion accounting checks track first, then status. Every case below assumes the query matches at least
one copy.

**Default filters.** The result set, `identified` and `excluded.total` are unchanged, but the buckets shift: a copy
that was removed as `status: rejected` is now removed as `track: workshop`. A stored search record whose query matches a copy
(so the copy is among its identified records) reproduces on its own pinned index. Replayed on the rebuilt index, it
gives `ids_match: true` and `excluded_match: false`, since `excluded_match` compares the whole `excluded` block,
buckets included; its status is `drifted`, as for every record on a new index.

**A user-written `track:` clause naming both main and workshop**, such as `track:(main OR workshop)`. The status
default stays, so the result set doesn't change. A matched copy now leaves through `status: unknown` instead of
`status: rejected`, so `unclassified_total` (the "unclassified records" the banner and methods text report) can rise
by up to 18. A stored record with such a filter likewise replays with `excluded_match: false`.

**A user-written `track:` clause naming only one of them.** That clause stays in the identification query, so the
copies move in or out of "identified":
- With `track:workshop`, `identified` and `excluded.total` can each rise by up to 18. The copies are removed as
  `status: unknown`, which also raises `unclassified_total`.
- With `track:main`, both counts can fall by up to 18.

The result set is still unchanged, because no copy is accepted.

**Membership** changes only when the status default is dropped as well, for example by a query that writes its own
`status:` clause including `rejected` or `unknown`. The copies now match `status:unknown` and `track:workshop`, and
no longer match `status:rejected` or `track:main`.

## Duplicates within the ICLR 2017 crawl (unchanged by this task)
The copies are separate OpenReview notes with their own forum ids, so they stay separate records from their
conference twins. That holds for these 18 and for the 34 `Invite to Workshop` workshop notes whose titles match a
conference note. A query with the default filters off counts each such paper twice under "identified". This was so
before TASK-152, which changes no merge. The defaults remove both copies, since none of them is accepted. Linking
such pairs, for example by the `_bibtex` forum id, is a follow-up, to be filed by the lead.

## The RIS path
The RIS importer is unchanged, by the lead's decision of 2026-10-01. PR #47's method feeds every note carrying
`ICLR.cc/2017/conference` (543 of them) to `ris._identity` as scholarmend 0.1.4 claims. The script reads both
listing pages as above and runs this on each such note `n`:

```python
from openproceedings.ingest import ris
vid = n["content"]["venueid"]
ev = f"venueid={vid}"
claims = [{"field": "venue_id", "value": vid, "source": "openreview_api", "evidence": ev},
          {"field": "forum_id", "value": n["id"], "source": "openreview_url",
           "evidence": f"https://openreview.net/forum?id={n['id']}"},
          {"field": "venue_string", "value": n["content"]["venue"], "source": "openreview_api", "evidence": ev}]
i = ris._identity({"claims": claims}, [])  # tally (listing, i.cls.track, i.cls.status)
```

It gives the same result as before the change:

```
543
198 ('conference', 'main', 'accepted')
245 ('conference', 'main', 'rejected')
47 ('conference', 'workshop', 'unknown')
18 ('workshop', 'main', 'rejected')
35 ('workshop', 'workshop', 'unknown')
```

scholarmend's claims don't name a note's submission invitation, so a copy can't be told from a real rejection. In a
snapshot that also holds the ICLR 2017 v1 crawl, the record merges by forum id and the crawl's claims win
(decision-005). In an RIS-only snapshot it keeps `main`/`rejected`, a known over-count of up to 18. The fix is for
scholarmend to emit the v1 note's invitation, a follow-up to be filed by the lead.
