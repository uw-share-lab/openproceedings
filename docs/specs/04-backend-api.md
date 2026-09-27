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
| `POST` | `/parse` | `{q, mode}` → 02's `ParseResult`: `mode`, `ast`, `effective_ast` (the UI tree shows the defaults), `canonical`, `canonical_hash`, `identification_query`, `defaults`, `warnings`, `errors`, `translations` (`identification_ast` stays server-side). Called as you type, debounced. |
| `GET` | `/search` | `q, mode, sort, offset, limit(≤200)` → `SearchResponse` |
| `GET` | `/papers/{id}` | The full record, provenance included |
| `GET` | `/export` | `q, mode, format=ris\|csv\|bibtex\|jsonl`, optional `record_id` **or** `index_version` → a stream of the **entire** matched set, ordered by `id`, served from the pinned index. A `record_id` whose replay status is `mismatch` is refused (409 `API_RECORD_MISMATCH`) |
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
  "query": { "input": "...", "canonical": "...", "canonical_hash": "…", "identification_query": "...",
             "warnings": [], "translations": [],
             "expansions": { "benchmark*": ["benchmark","benchmarking","benchmarks"] } },
  "index_version": "a1b2c3d4e5f6",
  "tokenizer_version": "…",
  "query_version": "…",
  "total": 412,
  "excluded": { "total": 304,
                "track": { "workshop": 212, "competition": 4, "unknown": 0 },
                "status": { "rejected": 88, "unknown": 0 } },
  "facets": { "venue": {...}, "year": {...}, "track": {...} },
  "hits": [ { "id": "...", "title": "...", "abstract": "...", "authors": [...], "venue": "ICLR",
              "year": 2025, "track": "main", "presentation": "poster", "score": 12.3,
              "highlights": { "title": [[0,5]], "abstract": [[102,114]] }, "urls": {...} } ]
}
```

`excluded` always has this shape: `total` (= the `identification_ast` count − `total`, 03 §Exclusion
accounting) plus a `track` and a `status` map whose buckets sum to it. Each map always carries an `unknown`
key, even when 0, so unclassified records are itemised and never folded into another bucket. Buckets are
ordered by count, largest first, ties by name, with `unknown` last, so a stored record's JSON is stable.

`facets` are disjunctive: each facet field is counted over the matched set with every filter applied **except that field's own top-level conjuncts** (a filter nested under an `OR` stays applied; decision-001). So the track facet still shows how many workshop papers you would get by including them. Clicking a facet in the UI
rewrites the query (guarantee 3). No hidden facet state exists.

## Exports (built to be imported into Covidence)

- **RIS:** `TY  - CPAPER`, `TI`, `AB` (full), `AU` (one line each), `PY`, `T2` (the venue string below), `UR` (forum then pdf), `DO` if present, `ID` (the openproceedings paper id, so exports round-trip), `KW`
  track, and `N1` = `openproceedings <index_version> · query <canonical_hash> · <UTC date>`. Checked against
  the RIS parser venuetriage already uses, plus one fixture imported into Covidence by hand
  (`docs/results/2026-09-27-covidence-check.md`, **pending**).
- **`TY` is `CPAPER`, not `JOUR`** (task-004). Every exported paper is a conference paper. Zotero's RIS
  translator (`RIS.js`, 2026-01-05) imports `CPAPER` as `conferencePaper` and puts `T2` in its
  `conferenceName`; a `JOUR` would become a `journalArticle` with the conference in `publicationTitle`.
  EndNote reads `CPAPER` as *Conference Paper*. EndNote's default duplicate check compares Author, Year and
  Title *within one reference type*, so a copy of the same paper exported as `JOUR` or `CONF` by another
  database is only caught if the Reference Type box is unticked in its Duplicates preferences. Covidence
  matches duplicates on title, year, volume and authors, not on type
  ([Covidence FAQ](https://support.covidence.org/help/how-does-covidence-detect-duplicates)). Whether
  Covidence shows every `CPAPER` field, and whether our empty volume blocks a match against a copy that has
  one, is the hand check above. Its fixture is pinned byte for byte by
  `backend/tests/unit/test_covidence_fixture.py`.
- **Venue string** (`T2`, and BibTeX `booktitle`; task-004): `<conference name> (<acronym that year> <year>)`,
  one string per venue and year whatever the track or status, so every copy of a venue-year reads alike and
  `PY` equals the year it names. It is the conference's name, not a proceedings title ("Advances in Neural
  Information Processing Systems 36", "Proceedings of the 40th International Conference on Machine
  Learning"): an export also holds workshop, rejected and withdrawn papers, and all of ICLR, which no
  proceedings volume contains. The table is `CONFERENCES` in `export.py`; `venue_name()` refuses a year before
  the venue was held, so an `op export --out` leaves no file.

  | Venue | Years | String |
  |---|---|---|
  | NeurIPS | 1987–2017 | `Conference on Neural Information Processing Systems (NIPS <year>)` |
  | NeurIPS | 2018 on | `Conference on Neural Information Processing Systems (NeurIPS <year>)` |
  | ICLR | 2013 on | `International Conference on Learning Representations (ICLR <year>)` |
  | ICML | 1988 on | `International Conference on Machine Learning (ICML <year>)` |

  This covers every year the sources can yield, and every year each venue was held under its name (spec 01
  §Sources: NeurIPS proceedings for all years, from 1987; ICLR from 2018 on OpenReview; ICML from 2020 on PMLR,
  whose first ICML volume is 2013's v28; the crawl's earliest year is TASK-049, proposed 2018). Sources,
  checked 2026-09-27: [proceedings.neurips.cc](https://proceedings.neurips.cc/) labels 1987–2017 "NIPS" and
  2018 on "NeurIPS"; the board announced the new acronym on 16 November 2018, before that December's
  meeting ([Synced, 2018-11-19](https://syncedreview.com/2018/11/19/name-flip-flop-nips-is-now-neurips/));
  [neurips.cc](https://neurips.cc/) calls 2026 "The Fortieth Annual Conference on Neural Information
  Processing Systems" (so 1987 is the first). [iclr.cc](https://iclr.cc/About) lists its conferences from 2013.
  [icml.cc](https://icml.cc/) calls 2026 the "Forty-Third International Conference on Machine Learning" and
  PMLR's v202 is the 40th (2023), so, counting back annually, 1988 is the 5th, the first held as a conference
  (the earlier meetings were workshops). `backend/tests/unit/test_export.py` pins each era's first year, the
  rename and recent years by hand, and every venue from 2013 to 2026.
- **CSV:** one row per paper, the columns of the schema in 01 plus `index_version` and `canonical_hash`
  provenance columns, UTF-8 with a BOM (so Excel opens it
  correctly).
- **BibTeX:** `@inproceedings`. Keys are `<firstauthorlast><year><firsttitleword>`, de-duplicated with a/b:
  the first paper with a key keeps it bare, and each later one, in id order, takes the next suffix not yet
  issued in the file (decision-007: what Better BibTeX and JabRef do, and it streams). Keys are unique per file,
  not identifiers. A superset export keeps every earlier key when the added papers sort after them in id
  order; an added paper that sorts first takes the bare key and shifts the rest. Merge successive exports on
  `openproceedings_id`, not on the key. `booktitle` is the venue string above.
  Provenance goes in `note = {openproceedings <index_version> · query <canonical_hash> · <UTC date>}`.
  Every entry carries `openproceedings_id = {<id>}`, so a round-trip recovers the id of every record,
  proceedings-only (PMLR, NeurIPS) ones included. Output must pass `refaudit.bibtex.parse_string` (the pinned `refaudit` PyPI package).
- As built (task-030, `export.py`, used by `op export`; the endpoints are task-036):
  - **RIS:** `TY  - CPAPER`, with `UR` forum, then pdf, then proceedings. Each record ends `ER  - `. Line breaks
    inside a value become single spaces and control characters are dropped, since RIS is line-based. URLs
    are validated at ingest as one-line http(s) addresses, so none can carry a forged record.
  - **CSV:** UTF-8 with a BOM (Excel); every field of the stored display record plus the facets and the
    provenance columns `index_version`, `canonical_hash` and `exported_at` (the UTC date). Two fields of
    spec 01 are left out: `provenance` (per-field claims, a nested list) and `content_hash`. Both stay in the
    snapshot that `index_version` pins. Lists are joined with "; " (ambiguous if a value holds one; JSONL
    keeps lists). A text cell starting, after leading spaces, with `=`, `+`, `-` or `@` (full-width forms
    too), or with a tab or a carriage return, is prefixed with `'`, so a spreadsheet never runs it (OWASP's
    CSV-injection guard); control characters are dropped.
  - **BibTeX:** keys are ASCII and lower-case: the first author's last name, the year and the first run of
    letters and digits in the title (`anon` without authors, `untitled` without a word; `ø`, `ß`, `ł`, `æ` …
    are spelled out first). A repeat key takes the next unused suffix, so a suffixed key never meets a real
    one. Braces are kept when they nest both as BibTeX counts them (every brace) and as parsers that honour
    `\{` do; otherwise every brace is dropped with the backslash that escaped it, since an entry the two read
    differently can swallow the next. `&`, `%` and `#` are escaped. A value never ends on a backslash. An
    author name holding a standalone `and`, or `others`, is braced, so it isn't split or read as et al.
  - **JSONL:** one object per record, with `index_version`, `canonical_hash` and `exported_at`: the lossless
    format (CSV's formula guard adds a `'` to some cells). U+2028, U+2029 and U+0085 are escaped, so a record
    stays one line for every reader.

  Each format is checked round-trip to its ids; BibTeX also against the pinned `refaudit==0.4.9`. `op
  export` counts what it wrote against the query's total before renaming its temporary file into place.
- Exports stream, and are not paginated or truncated. The response headers `X-Total` (equal to the search's
  `total`) and `X-Index-Version` say exactly which set was exported. An export started during an index
  hot-swap finishes on the index it began on.
- An export pinned by `record_id` to a record whose replay status is `mismatch` is refused with 409
  `API_RECORD_MISMATCH` (§Error handling): a set that breaks guarantee 4 is never handed to screening.

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
| `dedup` (`merged`, `ambiguous_not_merged` counts from the manifest) | the PRISMA-S item 16 deduplication-process statement (corpus-wide ingest merges, never a per-search removal count) |
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

## Error handling

Every error uses the one envelope `{error: {code, message, diagnostics?}}`. Codes come from the registry in
`backend/src/openproceedings/diagnostics.py` (error-diagnostics skill), and a status/code pair never changes
once released: changing one is a breaking change under `/api/v1`.

| Situation | HTTP | `code` |
|---|---|---|
| Query does not parse, uses an unknown field or value, or has a bad wildcard (incl. more than 200 expansions) | 422 | `PARSE_*`, `FIELD_*`, `WILDCARD_*` (diagnostics carry the spans); a query over 2,000 code points is `PARSE_TOO_LONG`, rejected before parsing |
| A query parameter is invalid (bad `sort`, `limit` > 200, unknown `format`, malformed `record_id`) | 422 | `API_BAD_PARAM` |
| Paper or search record not found | 404 | `API_PAPER_NOT_FOUND` / `API_RECORD_NOT_FOUND` |
| A pinned `index_version` is not available on this instance | 409 | `API_INDEX_VERSION_UNAVAILABLE` |
| Export requested for a record whose replay status is `mismatch` | 409 | `API_RECORD_MISMATCH` |
| Rate limit exceeded | 429 | `API_RATE_LIMITED` (with `Retry-After`) |
| No index loaded yet (startup, failed swap) | 503 | `API_INDEX_NOT_LOADED` |
| Anything unexpected | 500 | `API_INTERNAL` (logged at ERROR with the request id; message never echoes input) |
| No such endpoint (task-034) | 404 | `API_NOT_FOUND` |
| An endpoint that exists, called with another method (task-034) | 405 | `API_METHOD_NOT_ALLOWED` (with `Allow`) |

A replay `mismatch` is **not** an HTTP error. It is a `200` with `status: "mismatch"`, logged as
`API_REPLAY_MISMATCH` (§Search records).

## Implementation notes

- The app loads the index once at startup. Hot-swapping to a new `index_version` is an atomic pointer
  swap. Handlers are sync functions (Tantivy is CPU-bound), run in the thread pool.
- Logging: structured JSON with request ID, canonical hash, latency and total. **Neither `q` nor the
  canonical or identification strings are logged by default**, in case they contain unpublished review
  designs. This is set in config.
- As built (task-034, `backend/src/openproceedings/api/`):
  - `create_app(ApiConfig)` (`app.py`). `ApiConfig` (`config.py`) holds the data directory, the index name
    (`current` or an index_version: only `[0-9a-f-]`, and it must resolve, through the `current` symlink, to a
    directory directly under `<data_dir>/indexes/`), the rate limit (`capacity` 60, `refill_per_second` 1,
    `export_weight` 10, per client), the exact CORS origins (no `*`, no path; `allow_credentials=False`),
    the trusted proxies (addresses or networks) and `log_query_text` (default false). The query-length cap
    is not configurable: it is the parser's 2,000 code points, so the API refuses what `op search` refuses.
  - The lifespan loads the index in a background thread, so `GET /api/v1/healthz` answers `{index_loaded,
    index_version, tokenizer_version, query_version}` (`index_version` null) meanwhile, and routes that need
    the engine answer 503 `API_INDEX_NOT_LOADED`. SIGHUP (main thread) reloads in a background thread and
    swaps the one engine reference; a failed reload logs `index_load_failed` at ERROR and keeps serving the
    engine it had, so 503 means only that no index was ever loaded. Reloading the version already served
    keeps the engine.
  - Routes take the engine through `deps.EngineDep`: read once per request, so a request or a stream in
    flight finishes on the index it started on. `deps.checked_query(q)` raises 422 `PARSE_TOO_LONG` (the
    parser's own diagnostic, `parser.too_long`) before anything reads the query.
  - The client for the rate limit is the TCP peer, or, when the peer is a trusted proxy, the right-most
    `X-Forwarded-For` hop that is not one (IPv6 per /64). `/healthz` costs nothing; `/export` costs
    `export_weight`, charged before routing. The 429 carries `Retry-After` in whole seconds.
  - Access line: one `request` line per request (INFO; `/healthz` at DEBUG) with `request_id`, `method`,
    `route` (the template; null when nothing matched, a 429 included), `status`, `ms`, `index_version`, and
    what a route adds with `deps.annotate`/`annotate_parse`: `canonical_hash`, `total`, `token_count`,
    `n_errors`, `error_codes`, `warning_codes` (at most 10 distinct codes, then `+N`). Never `q`, the
    canonical or identification strings, messages or spans. An unexpected exception is one
    `request_failed` ERROR line with its type and frames (never its message) and a 500 whose message names
    the request id; nothing is re-raised to the server.
  - `op serve [--host] [--port] [--index] [--cors-origin …] [--trusted-proxy …] [--rate-capacity]
    [--rate-refill] [--export-weight] [--no-rate-limit] [--log-query-text]` runs one uvicorn process with
    its own access log off, `proxy_headers` off, and a 64 KiB request-head limit (uvicorn's 16 KiB would
    refuse a valid 2,000-code-point query in the URL). uvicorn's loggers go through the JSON handler;
    httpx/httpcore are pinned to WARNING.
  - The OpenAPI document and Swagger UI are served under `/api/v1` (`openapi.json`, `docs`); the snapshot
    and codegen are task-040.

## Testing

- Contract tests for each endpoint using an in-process `TestClient` over the 5k-record fixture index.
- Export round-trips: parse the RIS/CSV/BibTeX output back and get the same IDs and fields.
- Search-record replay tests for the reproduced, drifted and mismatch paths. The mismatch path uses a
  fixture record inserted with a wrong `ids_hash` or `excluded` (the store stays append-only), and asserts a `200` with
  `status: "mismatch"` plus one `API_REPLAY_MISMATCH` ERROR log line.
- An export with `record_id` of a `mismatch` record returns 409 `API_RECORD_MISMATCH` and streams nothing.
- An OpenAPI snapshot test, so any contract change shows up in the PR diff.
