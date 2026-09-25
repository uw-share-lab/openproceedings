# 01 — Ingestion

Status: **draft for review** · depends on: nothing · consumed by: 03 (index build), 04 (coverage)

## Purpose

Produce a **corpus snapshot**: one normalized record per paper, with an exact venue, year, track and
acceptance status, from every source that holds these venues. The snapshot is the only input to the index
build.

## Record schema (`PaperRecord`, pydantic v2)

| Field | Type | Notes |
|---|---|---|
| `id` | str | Stable ID `op:<venue>:<year>:<native>`, e.g. `op:iclr:2024:iilhN2MycO`. `native` is the OpenReview forum ID, or `pmlr-v202-<key>` / `nips-<hash>` for proceedings-only papers. |
| `title` | str | Raw, whitespace-collapsed. Normalization for search happens in 03, not here. |
| `abstract` | str \| null | Raw. `null` if no source has it. Never a Scholar snippet (reject strings containing `…`). |
| `authors` | list[str] | Display order. |
| `venue` | enum | `NeurIPS` \| `ICLR` \| `ICML`. Extensible. |
| `year` | int | Conference year, not the arXiv year. |
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
| `datasets_benchmarks` | `NeurIPS.cc/<Y>/Track/Datasets_and_Benchmarks` or `…/Datasets_and_Benchmarks_Track`; NeurIPS ≤2023 proceedings `Datasets_and_Benchmarks` aliased to `_Track` (scholarmend fix) |
| `position` | ICML position-paper track |
| `workshop` | `<Venue>.cc/<Y>/Workshop/…`, including satellite paths like `Workshop_Mexico_City/…` |
| `competition` | NeurIPS Competition Track, PMLR competition volumes |
| `tiny_papers` | ICLR Tiny Papers (2023–2024) |
| `blogpost` | ICLR Blogpost track |
| `other` | A recognised track not listed above. Keeps `venue_id_raw` for audit. |
| `unknown` | No trustworthy signal. Always shown in coverage reports. |

The rule is carried over from scholarmend: **only `content.venueid` on the submission note decides the track
and status.** A venue must never be derived from an invitation. Doing that once turned a rejected ICLR paper
into an ICLR main-track paper (scholarmend note, `zkNCWtw2fd`).

## Sources

| Source | Covers | Access |
|---|---|---|
| OpenReview API v2 (`api2.openreview.net`) | ICLR 2024+, NeurIPS 2023+, ICML 2023+ | Authenticated with `.env` credentials. The anonymous API returns 429 quickly (verified 2026-09-23). |
| OpenReview API v1 (`api.openreview.net`) | ICLR 2018–2023, NeurIPS 2021–2022 | Status comes from decision notes or `content.venue`. A per-year adapter handles each schema. |
| NeurIPS proceedings (`proceedings.neurips.cc`) | NeurIPS main and D&B, all years; the only source before 2021 | HTML/JSON pages. Also cross-checks OpenReview acceptance. |
| PMLR (`proceedings.mlr.press`) | ICML 2020–2022 (v119, v139, v162); confirms 2023+ | Volume index plus per-paper pages. The volume → venue/year/track table lives in config and is checked in tests. |
| RIS importer | The Trust-Evals corpus (M2 bootstrap) | Reads scholarmend `mended.ris` (full abstracts, corrected PY/JF). Tags track from scholarmend's venueid claims. Imported records carry `provenance.source = "ris"`. |

The M2 bootstrap is deliberately the existing corpus (≈1,834 screened records plus workshop records
auto-removed). This lets the team use the engine for the live review before the full crawl lands in M4.

## Pipeline

1. **Fetch.** One crawler per source. Every HTTP call goes through a cache (a scholarmend-style disk
   cache keyed by URL and parameters, with a TTL). Rate limits and retries honour `Retry-After`. A crawl
   can resume.
2. **Normalize.** Map each source's shape to `PaperRecord`. Strip HTML. Keep LaTeX verbatim (03 decides
   how it is tokenized).
3. **Classify.** Derive `track`, `status` and `presentation` using the rules above. Every classification
   records its evidence claim.
4. **Deduplicate.** The same paper appears on OpenReview and in the proceedings (NeurIPS, ICML 2023+).
   Merge on (a) an identical forum ID, then (b) a normalized title with the same venue and year. Two
   records are merged **only** when venue and year agree. That lesson comes from venuetriage: records
   with no year must never merge on `(title, "")`. Merges are written to `merges.csv` for audit.
5. **Snapshot.** Write `data/snapshots/<date>-<shorthash>/records.jsonl` (sorted by `id`) and
   `manifest.json`. The manifest holds counts per venue × year × track × status, source versions,
   the crawl date and the snapshot hash. Snapshots are immutable. `data/` is gitignored.

## CLI

```
op ingest openreview --venue ICLR --years 2020-2026
op ingest proceedings --venue NeurIPS --years 2020-2025
op ingest ris <file.ris>...
op snapshot build [--from <cache>]      # merge sources → new immutable snapshot
op snapshot diff <a> <b>                # added / removed / changed records
```

## Error handling

- Missing abstract: keep the record with `abstract=null`. It is still matched on title. Count it in the
  manifest.
- Unparseable venueid: `track=unknown`, logged, and surfaced on the coverage page. Never guessed.
- A source disagrees with another (for example, OpenReview says accepted but the proceedings don't list
  it): keep both claims, set `status` from the higher-priority source, and write `conflicts.csv`.

## Testing

- Recorded HTTP fixtures (VCR-style) for each source and each year's schema variant.
- A venueid-parsing table test covering every venueid form seen in scholarmend's 90 validated cases, plus
  the known workshop forms.
- Dedup property tests. Never merge across venue or year. Merging is idempotent.
- Snapshot determinism: the same inputs give a byte-identical `records.jsonl` and hash.
