# 04 — Backend API

Status: **draft for review** · depends on: 02, 03 · consumed by: 05, external scripts

## Purpose

A stateless FastAPI service over a read-only index, plus a small SQLite store for search records. It is the
only thing the frontend talks to. It is also a documented public API, so scripts and notebooks can run
reviews without the UI.

## Conventions

- Base path `/api/v1`. JSON. Pydantic v2 models are the contract. The OpenAPI schema is exported to
  `frontend/src/api/schema.ts` via codegen, so the two sides can't drift. CI fails if the generated file is
  stale.
- Every response carries `index_version`, `tokenizer_version` and `query_version`. `query_version` versions
  the query *semantics* that live outside the index: the parser, the compiler (NEAR/slop, wildcard rules),
  the default-filter set and the `source:` alias table. It is bumped by the same rule as
  `TOKENIZER_VERSION` (03): whenever some query could mean something different.
- **Span units:** every span is a half-open `[start, end)` range of **Unicode code points** over the *raw
  source string*. For `highlights` that is the stored title or abstract. For diagnostic `span`s it is the
  query input `q`. Spans are never over normalized text: NFKC can change lengths, so `normalize()` returns an
  offset map that highlight computation uses. The frontend converts to
  UTF-16 indices exactly once, in one helper (`nextjs-conventions` skill). A golden contract test covers a
  title containing an astral-plane character.
- Errors use one shape: `{error: {code, message, diagnostics?: [Diagnostic]}}`. A parse error is a `422`
  with 02's diagnostics, spans included.
- No authentication in v1. Rate limiting is per IP (a token bucket in the app, set in config). CORS
  allowlist comes from config.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/parse` | `{q, mode}` → 02's `ParseResult` (AST, canonical, warnings, translations). Called as you type, debounced. |
| `GET` | `/search` | `q, mode, sort, offset, limit(≤200)` → `SearchResponse` |
| `GET` | `/papers/{id}` | The full record, provenance included |
| `GET` | `/export` | `q, mode, format=ris\|csv\|bibtex\|jsonl`, optional `record_id` **or** `index_version` → a stream of the **entire** matched set, ordered by `id`, served from the pinned index |
| `POST` | `/records` | Freezes a search as an immutable **search record** → `{record_id, url}` |
| `GET` | `/records/{id}` | The stored record, plus a replay check (see below) |
| `GET` | `/records/{id}/diff` | For a `drifted` record: added and removed ids (with titles), and which `index_version` inputs changed |
| `GET` | `/coverage` | Counts per venue × year × track × status, abstract-missing counts, snapshot date |
| `GET` | `/meta` | Current and available `index_version`s, the field and track vocabularies (these feed the UI's autocomplete) |
| `GET` | `/healthz` | Liveness and whether the index is loaded |
| `GET` | `/near-misses` | **M5 only**: the semantic suggestion panel, a separate resource (see 06) |

### `SearchResponse`

```jsonc
{
  "query": { "input": "...", "canonical": "...", "canonical_hash": "…", "warnings": [], "translations": [],
             "expansions": { "benchmark*": ["benchmark","benchmarking","benchmarks"] } },
  "index_version": "a1b2c3d4e5f6",
  "total": 412,
  "excluded": { "track": { "workshop": 212, "competition": 4 }, "status": { "rejected": 88 } },
  "facets": { "venue": {...}, "year": {...}, "track": {...} },
  "hits": [ { "id": "...", "title": "...", "abstract": "...", "authors": [...], "venue": "ICLR",
              "year": 2025, "track": "main", "presentation": "poster", "score": 12.3,
              "highlights": { "title": [[0,5]], "abstract": [[102,114]] }, "urls": {...} } ]
}
```

`facets` are disjunctive: each facet field is counted over the matched set with every filter applied **except that field's own**. So the track facet still shows how many workshop papers you would get by including them. Clicking a facet in the UI
rewrites the query (guarantee 3). No hidden facet state exists.

## Exports (built to be imported into Covidence)

- **RIS:** `TY JOUR`/`CPAPER`, `TI`, `AB` (full), `AU` (one line each), `PY`, `T2` (for example "International
  Conference on Learning Representations (ICLR 2025)"), `UR` (forum then pdf), `DO` if present, `ID` (the openproceedings paper id, so exports round-trip), `KW`
  track, and `N1` = `openproceedings <index_version> · query <canonical_hash> · <UTC date>`. Checked against
  the RIS parser venuetriage already uses, plus one fixture imported into Covidence by hand.
- **CSV:** one row per paper, the columns of the schema in 01 plus `index_version` and `canonical_hash`
  provenance columns, UTF-8 with a BOM (so Excel opens it
  correctly).
- **BibTeX:** `@inproceedings`. Keys are `<firstauthorlast><year><firsttitleword>`, de-duplicated with a/b.
  Provenance goes in `note = {openproceedings <index_version> · query <canonical_hash> · <UTC date>}`.
  Output must pass refaudit's parser.
- Exports stream, and are not paginated or truncated. The response headers `X-Total` (equal to the search's
  `total`) and `X-Index-Version` say exactly which set was exported. An export started during an index
  hot-swap finishes on the index it began on.

## Search records (reproducibility, PRISMA)

`POST /records` freezes everything a methods section needs to cite and a replay needs to check:

| Field | Why |
|---|---|
| `input`, `mode`, `canonical`, `canonical_hash`, `identification_query` | what was searched, and the string that reproduces "identified" |
| `index_version`, `tokenizer_version`, `query_version`, `snapshot_hash`, `crawl_dates` (per source, from the manifest) | the database version and when its contents were collected |
| `searched_at` (UTC) | the search date, which is separate from the crawl date |
| `total`, `excluded` (with `unknown` itemised) | the counts cited in PRISMA |
| `expansions`, `translations`, `warnings` | how the query was interpreted (PRISMA-S) |
| `ids` (sorted) and `ids_hash = sha256(ids)` | membership, for replay and for the diff |
| `dedup` (`merged`, `ambiguous_not_merged` counts from the manifest) | the dedup process, for PRISMA-S |
| `semantic_version` (if the near-miss panel was open) | the audit trail for query revisions it prompted |

It returns a short id. `GET /records/{id}` replays the query and returns HTTP 200 with a `status`:
- **`reproduced`**: same `index_version` and `query_version` are available, and both `ids_hash` **and**
  `excluded` match.
- **`drifted`**: only a different index or query version is available. The response names *which* inputs
  changed (`snapshot_hash` = corpus drift; tokenizer, schema, ranking or query version = method drift) and
  gives `+added / −removed`. `+0 / −0` is reported as "membership-identical", not hidden.
- **`mismatch`**: same `index_version` and `query_version`, but `ids_hash` or `excluded` differ. This breaks
  guarantee 4, so it is logged at ERROR with code `API_REPLAY_MISMATCH` and treated as a bug. The record page
  shows it as "do not cite" (05).

The record page (05) is what a methods section cites. Records are stored in `data/records.sqlite`
(append-only, backed up with the snapshots).

## Implementation notes

- The app loads the index once at startup. Hot-swapping to a new `index_version` is an atomic pointer
  swap. Handlers are sync functions (Tantivy is CPU-bound), run in the thread pool.
- Logging: structured JSON with request ID, canonical hash, latency and total. **Raw query text is not
  logged by default**, in case it contains unpublished review designs. This is set in config.

## Testing

- Contract tests for each endpoint using an in-process `TestClient` over the 5k-record fixture index.
- Export round-trips: parse the RIS/CSV/BibTeX output back and get the same IDs and fields.
- Search-record replay tests for both the reproduced and the drifted paths.
- An OpenAPI snapshot test, so any contract change shows up in the PR diff.
