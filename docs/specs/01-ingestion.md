# 01 — Ingestion

Status: **draft for review** · depends on: nothing · consumed by: 03 (index build), 04 (coverage)

## Purpose

Produce a **corpus snapshot**: one normalized record per paper, with an exact venue, year, track and
acceptance status, from every source that holds these venues. The snapshot is the only input to the index
build.

## Record schema (`PaperRecord`, pydantic v2)

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable ID `op:<venue>:<year>:<native>`, e.g. `op:iclr:2024:iilhN2MycO`. `native` is the OpenReview forum ID, or `pmlr-v202-<key>` (ICML) / `nips-<hash>` (NeurIPS) / `iclr-<hash>` (ICLR) for proceedings-only papers. |
| `title` | str | Raw, whitespace-collapsed. Normalization for search happens in 03, not here. |
| `abstract` | str \| null | Raw. `null` if no source has it. Never a Scholar snippet (reject values that start or end with `…`; an ellipsis inside is allowed). Never an empty string. |
| `authors` | list[str] | Display order. |
| `venue` | enum | `NeurIPS` \| `ICLR` \| `ICML`. Extensible. |
| `year` | int | Conference year, not the arXiv year. A year before the venue was held under its name (NeurIPS 1987, ICLR 2013, ICML 1988; `vocab.CONFERENCES`) is refused. |
| `track` | enum | See the taxonomy below. Never defaults to `main`. Unknown stays `unknown`. |
| `status` | enum | `accepted` \| `rejected` \| `withdrawn` \| `desk_rejected` \| `unknown` |
| `presentation` | str \| null | `oral` / `spotlight` / `poster`, when the source states it. |
| `venue_id_raw` | str \| null | OpenReview `content.venueid` verbatim, e.g. `NeurIPS.cc/2023/Track/Datasets_and_Benchmarks`. |
| `urls` | object | `forum`, `pdf`, `proceedings`, `doi`, each optional. |
| `keywords` | list[str] | Stored and displayed, **not searched** (guarantee 2). |
| `provenance` | list[Claim] | For each field: the source, URL, fetch time and evidence (scholarmend's claim/ledger pattern). |
| `content_hash` | str | sha256 of the canonical JSON of the searchable and filterable fields. |

## Track taxonomy

| `track` | Source signal |
|---|---|
| `main` | `<Venue>.cc/<Y>/Conference` (accepted), PMLR main ICML volume, NeurIPS main proceedings |
| `datasets_benchmarks` | `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` (2021 as `…/Round1`, `…/Round2`; 2022–2023) or `NeurIPS.cc/<Y>/Datasets_and_Benchmarks_Track` (2024–2025); NeurIPS ≤2023 proceedings `Datasets_and_Benchmarks` aliased to `_Track` (scholarmend fix); 2021 on its own host (`datasets-benchmarks-proceedings.neurips.cc`, `-round1`/`-round2`). NeurIPS 2026 renamed the track `NeurIPS.cc/2026/Evaluations_and_Datasets_Track` (a live group; TASK-094 maps it here as the same track under a new name) |
| `position` | `ICML.cc/<Y>/Position_Paper_Track` (2025+); `NeurIPS.cc/<Y>/Position_Paper_Track` (2025+, verified 2026-09-27; TASK-094). ICML 2024's position papers carry `ICML.cc/2024/Conference` with no marker, so they are `main` on OpenReview and `unknown` from PMLR v235 |
| `workshop` | `<Venue>.cc/<Y>/Workshop/…`, including satellite paths like `Workshop_Mexico_City/…` |
| `competition` | `NeurIPS.cc/<Y>/Competition_Track` (2024+; TASK-094), `NeurIPS.cc/<Y>/Track/Competition`, PMLR competition volumes (v123, v133, v176, v220) |
| `tiny_papers` | ICLR Tiny Papers (2023–2024) |
| `blogpost` | ICLR Blogpost track |
| `other` | A recognised track not listed above. Keeps `venue_id_raw` for audit. |
| `unknown` | No trustworthy signal. Always shown in coverage reports. |

The rule is carried over from scholarmend: **only `content.venueid` on the submission note decides the track
and status.** A venue must never be derived from an invitation. Doing that once turned a rejected ICLR paper
into an ICLR main-track paper (scholarmend note, `zkNCWtw2fd`). **In API v1 years the venueid is not status
evidence** (verified 2026-09-27, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`): ICLR 2017,
2022 and 2023, NeurIPS 2021–2022 and D&B 2021 put the bare venue path on rejected submissions too. There the
status comes from `content.venue` (`ICLR 2022 Submitted`, `Submitted to ICLR 2023`), the decision note, or
the withdrawn / desk-rejected invitation, and the venueid only confirms venue, year and track (TASK-095).
`classify_venueid` returns status `unknown` for any venueid in a v1 venue-year (ICLR 2013–2023, NeurIPS
2021–2022: `classify.is_v1`), and `classify_v1_venue` maps the exact `content.venue` strings seen live
(an unlisted string is `unknown`).

### Status handling (decision-012)

| `status` | v2 (2023/2024+) | v1 (≤2023) | Proceedings, PMLR |
|---|---|---|---|
| `accepted` | bare venueid (`ICLR.cc/2025/Conference`) | accept decision or venue string (`ICLR 2021 Poster`, `NeurIPS 2022 Accept`, ICLR 2013 `conferenceOral-iclr2013-conference`) | listed |
| `rejected` | `…/Rejected_Submission` | reject decision, `… Submitted` / `Submitted to …` venue | never |
| `withdrawn` | `…/Withdrawn_Submission` | the `…/-/Withdrawn_Submission` invitation | never |
| `desk_rejected` | `…/Desk_Rejected_Submission` | the `…/-/Desk_Rejected_Submission` invitation | never |
| `unknown` | `…/Submission` (under review) or no venueid | no decision (ICLR 2014: `submitted, no decision`; ICLR 2023 Tiny Papers) | never |

Every public submission is ingested and indexed whatever its status; the default `status:accepted`
(02 §Default filters) excludes the others and counts them. What is public differs: ICLR publishes every
rejected, withdrawn and desk-rejected submission; NeurIPS and ICML only rejected papers whose authors opt in
(NeurIPS 2024 main: 201; ICML 2025: 162; ICML 2023–2024: none), and almost no withdrawn ones. So a status
count is complete for ICLR and a floor elsewhere, and coverage (07 §C) says which.

## Sources

| Source | Covers | Access |
|---|---|---|
| OpenReview API v2 (`api2.openreview.net`) | ICLR 2024+, NeurIPS 2023+ (with 2023 D&B), ICML 2023+ | Authenticated with `.env` credentials (`OPENREVIEW_USERNAME`, `OPENREVIEW_PASSWORD`). Anonymous requests get HTTP 200 with an HTML browser-challenge page, never JSON (verified 2026-09-27), so a non-JSON response is an auth failure. `limit` ≤ 1000; `count` only when `offset` is sent. |
| OpenReview API v1 (`api.openreview.net`) | ICLR 2013, 2014, 2016–2023 (2016: workshop track only), NeurIPS 2021–2022 (main and D&B) | Same login. Status comes from decision notes, `content.venue` or `content.decision` (2013), never the bare venueid (§Track taxonomy). A per-year adapter handles each schema. ICLR 2014 has no decisions and ICLR 2015 is not on OpenReview (TASK-096). |
| NeurIPS proceedings (`proceedings.neurips.cc`) | NeurIPS main, 2013 to the latest published year (2024 on 2026-09-27), and D&B 2022+; 2021 D&B on `datasets-benchmarks-proceedings.neurips.cc`. The only source before 2021 | Year index pages plus abstract pages. The URL has no track token before 2022. Also cross-checks OpenReview acceptance. |
| PMLR (`proceedings.mlr.press`) | ICML 2013–2022 (v28, v32, v37, v48, v70, v80, v97, v119, v139, v162); confirms 2023–2025 (v202, v235, v267) | Volume index plus per-paper pages. The volume → year/track table is `ingest/volumes.py`, checked in tests; a volume that mixes main and position papers (v235, v267) gives track `unknown`. |
| RIS importer (`ingest/ris.py`) | The Trust-Evals corpus (M2 bootstrap): two searches, 2025–26 and 2020–24, one scholarmend output each | Reads a `mended.ris` with `scholarmend.parse.parse_file` (pinned `scholarmend` PyPI package) and the `resolved.json` beside it, entry by entry (a count or title mismatch is an error). Only scholarmend's identifying claims decide identity, track and status: a venueid plus its forum id; else a NeurIPS/ICLR `proceedings_url` claim (`nips-`/`iclr-<hash>`); else a `pmlr_url` claim in an ICML volume (`pmlr-v<N>-<key>`, track from `ingest/volumes.py`). `status` comes from a claim only: a venueid → its status, except that a v1 venue-year's venueid gives `unknown` (TASK-095: scholarmend's claims carry no `content.venue`; audit in `docs/results/2026-09-27-v1-status-audit.md`); a proceedings listing → `accepted`, overriding a venueid that names the same venue, year and track (decision-005); a listing that disagrees makes the record a `conflict`. Never inferred from appearing in Scholar. Abstract: OpenReview's, else the proceedings page's, else `null` (never Scholar's or Semantic Scholar's). Authors from `AU` without Scholar's `...`. Every claim has `source = "ris"`, its origin in `evidence`, and `fetched_at` from the `M1` Query date: Publish or Perish's local time, stored labelled UTC because the offset isn't recorded, so a crawl date can be a day off near midnight (task-077 records the offset). Skipped records are counted by reason (`out_of_scope`, `unresolved`, `no_id`, `ambiguous`, `conflict`, `no_query_date`) in an `ImportReport`; none is given a minted id. A proceedings listing whose URL year is before its venue was held under its name (`papers.nips.cc/paper/1986/…`, `proceedings.iclr.cc/paper/2012/…`) is `unresolved`: skipped and counted, never an abort of the whole file. |

The M2 bootstrap is deliberately the existing corpus: the Trust-Evals review's Scholar results as
scholarmend mended them: 1,834 records read and 1,805 imported, all accepted, since the review had already
screened them; 90% main track, the rest D&B (160), position (16), one other and one workshop
(`docs/results/2026-09-27-corpus.md`). This lets the team use the engine for the live review before the
full crawl lands in M4. **Its counts are not PRISMA identification numbers:** the corpus is already the
output of a search and a screening, so `identified` and `excluded` on an M2 index describe that corpus,
not a database; cite them only once the M4 crawl indexes the proceedings themselves.

**Crawl window (decision-013):** every venue from 2013, ICLR's first year, to the current year, wherever
a source above holds the venue-year; a year range is the query's `year:` filter, never a crawl limit. The
facts in this table were checked live on 2026-09-27 (`docs/research/2026-09-27-openreview-and-proceedings-facts.md`).

## Pipeline

1. **Fetch.** One crawler per source. Every HTTP call goes through a cache (a scholarmend-style disk
   cache keyed by URL and parameters, with a TTL). Rate limits and retries honour `Retry-After`. A crawl
   can resume.
2. **Normalize.** Map each source's shape to `PaperRecord`. Strip HTML. Keep LaTeX verbatim (03 decides
   how it is tokenized).
3. **Classify.** Derive `track`, `status` and `presentation` using the rules above. Every classification
   records its evidence claim.
4. **Deduplicate.** The same paper appears on OpenReview and in the proceedings (NeurIPS, ICML 2023+).
   `ingest/dedup.py`. Merge on (a) an identical id (the same forum ID in the same venue and year, or the
   same proceedings id), then (b) a normalized title (the token contract) with the same venue and year. Two
   records are merged **only** when venue and year agree. That lesson comes from venuetriage: records
   with no year must never merge on `(title, "")`. **Two OpenReview records with different forum IDs are
   never merged**: a main-track paper and its same-year workshop version can share a title. Title
   matching only links records *across* sources (OpenReview ↔ proceedings ↔ RIS), never joins two different
   proceedings papers, and never puts a paper whose track the proceedings don't host (workshop, other,
   `unknown`) into a proceedings listing. A merged record's fields
   are re-resolved from the union of its claims by the decision-005 precedence table. Merges are written
   to `merges.csv`, and disagreements and refused merges to `conflicts.csv`, for audit (dedup-rules skill).
5. **Snapshot.** Write `data/snapshots/<date>-<shorthash>/records.jsonl` (sorted by `id`) and
   `manifest.json`. The manifest holds counts per venue × year × track × status, source versions,
   the crawl date and the snapshot hash. Snapshots are immutable. `data/` is gitignored.

## CLI

```
op ingest openreview --venue ICLR --years 2020-2026
op ingest proceedings --venue NeurIPS --years 2020-2025
op ingest ris <mended.ris>...           # cache scholarmend outputs (resolved.json beside each)
op snapshot build [--from <cache>]      # merge sources → new immutable snapshot
op snapshot diff <a> <b>                # added / removed / changed records
```

As built (task-022): `ingest ris`, `snapshot build` and `snapshot diff`; the crawler sources are stubs
naming task-050/052. `op --data-dir <dir> <command>` (a global option; default `$OP_DATA_DIR`, else the repository's
`data/`, gitignored); results go to stdout as JSON, a refusal exits 1 with a one-line reason that never
quotes record text.

## Error handling

- Missing abstract: keep the record with `abstract=null`. It is still matched on title. Count it in the
  manifest.
- Unparseable venueid: `track=unknown`, logged, and surfaced on the coverage page. Never guessed.
- A source disagrees with another (for example, OpenReview says accepted but the proceedings don't list
  it): keep both claims, set `status` from the higher-priority source, and write `conflicts.csv`. The
  per-field precedence table is decision-005: OpenReview first for title, abstract and authors (the
  proceedings only where OpenReview lacks the paper); the official proceedings decide acceptance where
  they are published (OpenReview-accepted but unlisted → `unknown` + a conflict row; not yet built: task-072, M4); OpenReview's venueid
  decides track, and status elsewhere. A title that differs between merged sources is a conflict row too.

## Testing

- Recorded HTTP fixtures (VCR-style) for each source and each year's schema variant, recorded by hand
  and scrubbed of real text (titles, abstracts, authors replaced; structure kept), per decision-004.
- A venueid-parsing table test covering every venueid form seen in scholarmend's 90 validated cases, plus
  the known workshop forms.
- Dedup property tests. Never merge across venue or year. Merging is idempotent.
- Snapshot determinism: the same inputs give a byte-identical `records.jsonl` and hash.
