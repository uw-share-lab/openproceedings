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
- Every response carries `index_version` and `tokenizer_version`.
- **Span units:** every span (`highlights`, diagnostic `span`) is a half-open `[start, end)` range of
  **Unicode code points** over the *raw* stored text (not the normalized text). The frontend converts to
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
| `GET` | `/export` | `q, mode, format=ris\|csv\|bibtex\|jsonl` → a stream of the **entire** matched set, in a stable order |
| `POST` | `/records` | Freezes a search as an immutable **search record** → `{record_id, url}` |
| `GET` | `/records/{id}` | The stored record, plus a replay check (see below) |
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
- **CSV:** one row per paper, the columns of the schema in 01, UTF-8 with a BOM (so Excel opens it
  correctly).
- **BibTeX:** `@inproceedings`. Keys are `<firstauthorlast><year><firsttitleword>`, de-duplicated with a/b.
  Output must pass refaudit's parser.
- Exports stream, and are not paginated or truncated. The response header `X-Total` equals the search's
  `total`.

## Search records (reproducibility, PRISMA)

`POST /records` stores the input, canonical string, mode, `index_version`, UTC timestamp, `total`,
`excluded`, and `ids_hash = sha256(sorted matched ids)`. It returns a short ID. `GET /records/{id}` replays
the query:
- Same `index_version` available: re-run, and assert `ids_hash` matches. The status is `reproduced`.
- Only a newer index available: run on the current one and report `drifted`, with `+added / −removed`
  counts and a link to the diff.
- Same `index_version` but a different `ids_hash`: status `mismatch`. This breaks guarantee 4, so it is
  logged as an error and treated as a bug. It is never shown as a normal outcome.
- The diff behind `drifted` is served by `GET /records/{id}/diff` (added and removed ids, with titles).

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
