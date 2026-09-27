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
- Errors use one shape: `{error: {code, message, diagnostics?: [Diagnostic]}}`. A query that doesn't parse
  is a `422` carrying 02's diagnostics (spans included) on every endpoint that **runs** it (`/search`,
  `/export`, `POST /records`). `POST /parse` **reports** a parse: any well-formed body is a `200` whose
  `errors` hold those same diagnostics; only a malformed body is a `422 API_BAD_PARAM`.
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
              "year": 2025, "track": "main", "status": "accepted", "presentation": "poster", "score": 12.3,
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

- **RIS:** `TY  - CPAPER`, `TI`, `AB` (full), `AU` (one line each), `PY`, `T2` (the venue string below), `UR` (forum, then pdf, then proceedings; each only if present), `DO` if present, `ID` (the openproceedings paper id, so exports round-trip), two `KW`
  lines (the track, then `status:<status>`), and `N1` = `openproceedings <index_version> · query <canonical_hash> · <UTC date>`. Checked against
  the reference RIS parser, `scholarmend.parse.parse_ris` (the pinned `scholarmend` PyPI package), plus one
  fixture imported into Covidence by hand (`docs/results/2026-09-27-covidence-check.md`, **pending**).
- **Status in every format** (task-004 review). The venue string names the conference a paper was
  *submitted to*, so a rejected or withdrawn paper still reads "ICLR 2024". A screener sees its status as
  RIS `KW  - status:rejected` (Covidence shows keywords), CSV and JSONL have the `status` column, and BibTeX has
  it in `keywords` and in the entry type below. RIS keeps `TY  - CPAPER` for every status, so one export
  imports as one reference type.
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
  proceedings volume contains. The table is `CONFERENCES` in `vocab.py`, read by `venue_name()` (both also
  importable from `export.py`), and its eras are checked for year order at import. A record for a year before
  its venue was held is refused when it is built (`PaperRecord`, spec 01 §Fields), so no index holds one and
  an export never meets one. `venue_name()` still raises, as a backstop, and it happens mid-stream: `op export
  --out` then leaves no file; `op export` to standard output has already written the records before it, and
  exits 1 with the error on stderr, so check the exit status when piping.

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
- **BibTeX:** `@inproceedings` for an `accepted` paper, with `booktitle` = the venue string. Any other status
  (`rejected`, `withdrawn`, `desk_rejected`, `unknown`) is `@unpublished`, BibTeX's type for a paper with an
  author and title that was not formally published, and has **no `booktitle`**. Its `note` starts
  `Submitted to <venue string>, status: <status>.` and then gives the provenance line, so the venue string is
  still the same string for every paper of a venue and year. Standard styles print `note` for `@unpublished`
  and require it. `@misc` with `howpublished` was the other option; `@unpublished` is the one that says "not
  published". `unknown` counts as not accepted, since an export must never cite a paper into proceedings on
  a guess. `keywords = {<track>, status:<status>}` on every entry. This is an export format, not stored
  data, so it can change without a decision record: a later export from the same index simply follows the
  new rule. Keys are `<firstauthorlast><year><firsttitleword>` for every entry type, de-duplicated with a/b:
  the first paper with a key keeps it bare, and each later one, in id order, takes the next suffix not yet
  issued in the file (decision-007: what Better BibTeX and JabRef do, and it streams). Keys are unique per file,
  not identifiers. A superset export keeps every earlier key when the added papers sort after them in id
  order; an added paper that sorts first takes the bare key and shifts the rest. Merge successive exports on
  `openproceedings_id`, not on the key.
  Provenance goes in `note = {openproceedings <index_version> · query <canonical_hash> · <UTC date>}` (after
  the `Submitted to …` sentence on an `@unpublished` entry).
  Every entry carries `openproceedings_id = {<id>}`, so a round-trip recovers the id of every record,
  proceedings-only (PMLR, NeurIPS) ones included. Output must pass `refaudit.bibtex.parse_string` (the pinned `refaudit` PyPI package).
- As built (task-030, `export.py`, used by `op export` and, byte for byte, by `GET /export` since task-036):
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

As built (task-037; `backend/src/openproceedings/records.py` holds the record, `ids_hash`, the store and the
replay, so a later `op record` calls the same functions; `api/records.py` is the transport, `api/pinned.py`
loads older indexes):
- **`POST /records`** takes `{q, mode}` (no other keys) and answers **201** `{record_id, url, index_version,
  tokenizer_version, query_version}`. `url` is the record page's path, `/record/<record_id>` (05 §Pages),
  relative to the site. The query is refused exactly as `/search` refuses it (422 with diagnostics,
  `PARSE_TOO_LONG` before parsing) and nothing is written. It is re-run on the request's one engine:
  `search.run` (so `total`, `excluded` and `expansions` equal `/search`'s) plus `match_ids` for the ids.
- **The record** holds every field of the table, plus `record_id`, `schema_version` and `ranking_params`
  (the index's two other inputs, so a drifted replay can name a method change after the pinned index is
  gone). `crawl_dates` is `{"all": {"from", "to"}}`, the snapshot manifest's `crawl_window`: today's
  manifest has one corpus-wide window, and a source entry that carries its own `crawl_window` (the M4
  crawlers) adds a key of its own. `dedup` is `{merged: manifest merges.total, ambiguous_not_merged:
  manifest conflicts.ambiguous_not_merged}`. `searched_at` is UTC to the second (`…Z`). `semantic_version`
  is null until the near-miss panel exists (M5). `excluded` keeps the pinned bucket order.
- **`ids_hash`** is `sha256("\n".join(sorted(ids)))`, code-point order, no trailing newline, with
  known-answer tests (the empty set is `sha256("")`).
- **Record ids** are `secrets.token_urlsafe(9)`: 12 characters of `[A-Za-z0-9_-]`, 72 random bits, redrawn
  on a collision. Anything else is 422 `API_BAD_PARAM`; an unknown id is 404 `API_RECORD_NOT_FOUND`, and
  neither message repeats the id.
- **The store** is `<data_dir>/records.sqlite` (`ApiConfig.data_dir`), created on the first save (a read
  never creates it). Tables `schema_version` and `records (record_id, index_version, searched_at, body, ids)`,
  `body` being the record's JSON without `ids` and `ids` the zlib-compressed id list. `BEFORE UPDATE` and
  `BEFORE DELETE` triggers on both tables abort ("append-only"), and a `BEFORE INSERT` trigger refuses an
  id that exists, so `INSERT OR REPLACE` can't delete-then-insert from any client (SQLite's REPLACE skips
  DELETE triggers unless `recursive_triggers` is on, which the app's connections also set). WAL mode; one connection per
  call, so the thread pool never shares one. `RecordStore.pinned(index_version)` counts the records that
  pin a version (check it before retiring one).
- **Replay** (`GET /records/{id}`, 200 `{index_version, tokenizer_version, query_version, record, replay}`;
  the top-level versions are those the replay ran on) re-parses the stored `canonical` in native mode, never
  `input`. If the record's `query_version` is this code's and its `index_version` is served or loadable here,
  it runs there: `reproduced` if `ids_hash` and `excluded` both match (and the canonical re-parses to the
  same `canonical_hash`), otherwise `mismatch`, with one ERROR line `replay_mismatch` (`code`
  `API_REPLAY_MISMATCH`, `record_id`, the versions, and which of `ids_match`, `excluded_match` and
  `canonical_match` failed). Otherwise it is `drifted` and runs on the served index: `replay.changed` lists
  each differing input (`snapshot_hash` kind `corpus`; `tokenizer_version`, `schema_version`,
  `ranking_params`, `query_version` kind `method`) with its recorded and current value. `replay` also has
  `total`, `excluded`, `ids_hash`, `ids_match`, `excluded_match`, `added`, `removed` (counts) and
  `membership_identical` (true on `+0/−0`). A canonical string that no longer runs under a newer query
  version (it no longer parses, or a wildcard now expands past the cap) is `drifted` with `refused` set to
  the code and `total`, `excluded` and `ids_hash` null; every stored id is then `removed`.
- **Pinned indexes** load on demand, read-only, by the served index's rules (`state.index_path`: an
  index_version resolving to itself directly under `<data_dir>/indexes/`; never `resolve_snapshot`), and
  are opened (verified) by the same engine class, so "available" means loadable by this code: an index built
  with another tokenizer or schema version is not, and its records replay as `drifted`. Two are held
  (least recently used dropped). An unloadable one is one WARNING line `pinned_index_unavailable`.
- **`GET /records/{id}/diff`** answers `{…versions, record_id, status, recorded_index_version, changed,
  added: [{id, title}], removed: [{id, title}], membership_identical}` for any status. A title comes from the
  index the replay ran on, else the record's pinned index; null when no index here holds the paper.
- **For `/export?record_id=` (task-036)**: `api.records.require_citable(request, record_id, engine)`
  returns the stored record, or raises 409 `API_RECORD_MISMATCH` when its replay is a `mismatch` (422 and
  404 as above); `replay_status(request, record_id, engine)` returns just the status. Pass the route's
  `EngineDep` engine so a request never reads the served index twice.
- Access line: `canonical_hash`, `total` (the replay's) and `index_version` (the one the replay ran on).
  No log line carries the input, canonical or identification strings: the record stores them, the logs don't.

## Error handling

Every error uses the one envelope `{error: {code, message, diagnostics?}}`. Codes come from the registry in
`backend/src/openproceedings/diagnostics.py` (error-diagnostics skill), and a status/code pair never changes
once released: changing one is a breaking change under `/api/v1`.

| Situation | HTTP | `code` |
|---|---|---|
| Query does not parse, uses an unknown field or value, or has a bad wildcard (incl. more than 200 expansions) (on endpoints that run the query) | 422 | `PARSE_*`, `FIELD_*`, `WILDCARD_*` (diagnostics carry the spans); a query over 2,000 code points is `PARSE_TOO_LONG`, rejected before parsing |
| A query parameter is invalid (bad `sort`, `limit` > 200, unknown `format`, malformed `record_id`) | 422 | `API_BAD_PARAM` |
| Paper or search record not found | 404 | `API_PAPER_NOT_FOUND` / `API_RECORD_NOT_FOUND` |
| A pinned `index_version` is not available on this instance | 409 | `API_INDEX_VERSION_UNAVAILABLE` |
| Export requested for a record whose replay status is `mismatch` | 409 | `API_RECORD_MISMATCH` |
| Rate limit exceeded | 429 | `API_RATE_LIMITED` (with `Retry-After`) |
| No index loaded yet (startup, or the first load failed; a failed swap keeps serving the old index) | 503 | `API_INDEX_NOT_LOADED` |
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
    `X-Forwarded-For` hop that is not one. An IPv4-mapped IPv6 address (`::ffff:a.b.c.d`, as a dual-stack
    bind reports IPv4 peers) counts as its IPv4 address, both as a key and when matching trusted proxies.
    IPv6 clients are bucketed per /64. One host usually holds a whole /64, but an attacker holding a /48 gets
    65,536 buckets, so the per-/64 limit bounds one host, not a determined network. `/healthz` (GET or
    HEAD, for uptime monitors; HEAD is its own route, left out of the OpenAPI document so operation ids stay
    unique) costs nothing; `/export` costs `export_weight`, charged before routing. The
    429 carries `Retry-After` in whole seconds.
  - Access line: one `request` line per request (INFO; `/healthz` at DEBUG) with `request_id`, `method`,
    `route` (the template; null when nothing matched, a 429 included), `status`, `ms`, `index_version`, and
    what a route adds with `deps.annotate`/`annotate_parse`: `canonical_hash`, `total`, `token_count`,
    `n_errors`, `error_codes`, `warning_codes` (at most 10 distinct codes, then `+N`). Never `q`, the
    canonical or identification strings, messages or spans. An unexpected exception is one
    `request_failed` ERROR line with its type and frames (never its message) and a 500 whose message names
    the request id; nothing is re-raised to the server. Layers, outermost first: the access line, CORS,
    the last catch (`LastCatch`), the rate limit, then the app, so a 500 carries the CORS headers like any
    response. If the exception comes after the response started (a stream), the client has its status, so
    the access line keeps `status` as sent and adds `aborted: true`. A CORS preflight from an origin that
    isn't allowed is Starlette's plain-text 400 `Disallowed CORS origin`, not the envelope (it never reaches
    the app), and it still gets its access line.
  - Error mapping beyond the table: any other 4xx a framework raises is 422 `API_BAD_PARAM`, logged at DEBUG
    (nothing of ours raises one). A `PARSE_*`/`FIELD_*`/`WILDCARD_*` refusal from the engine carries
    `diagnostics`: `/search` locates each over-cap wildcard by its span in `q`
    (`search.run` sets `EngineInputError.diagnostics`; the exception type is unchanged, so `op search`
    still logs `EngineInputError`), and a refusal it can't locate has one diagnostic with `span: null`.
  - `op serve [--host] [--port] [--index] [--cors-origin …] [--trusted-proxy …] [--rate-capacity]
    [--rate-refill] [--export-weight] [--no-rate-limit] [--log-query-text]` runs one uvicorn process with
    its own access log off, `proxy_headers` off, and a 64 KiB request-head limit (uvicorn's 16 KiB would
    refuse a valid 2,000-code-point query in the URL). **Deploy note:** `GET /search?q=…` carries the query
    in the URL, so the reverse proxy in front (Caddy, task-065) must not log query strings. Log the path
    only, or turn its access log off; the app's own access line never holds `q`. uvicorn's loggers go
    through the JSON handler;
    httpx/httpcore are pinned to WARNING, and the root logger gets the same JSON handler at WARNING, so another
    library's warning (asyncio, fastapi) is JSON too. `--log-query-text` only lets the formatter keep
    query-text fields; no log call passes one today (the access line never carries `q`), so it changes nothing.
  - The OpenAPI document and Swagger UI are served under `/api/v1` (`openapi.json`, `docs`).
- As built (task-040, `api/openapi.py`): the served document is committed as
  `backend/tests/contract/openapi.json` (`op openapi`: sorted keys, two-space indent, no server URL, no
  timestamp, built from `create_app` without loading an index), and `frontend/src/api/schema.ts` is
  generated from that file by `openapi-typescript` (pinned in `frontend/package.json`, `npm run gen:api`).
  `make openapi` regenerates both; `test_openapi_snapshot.py` fails when the live document differs from the
  snapshot, and CI's `test` job runs `make openapi` and fails on any diff. To keep the document valid and
  stable: an operationId is the handler's name (FastAPI's default appends the first method of the route's
  set, which follows `PYTHONHASHSEED`), unique across routers (tested); every route documents the error
  envelope as its `default` response (replacing FastAPI's `HTTPValidationError` 422, which this app never
  sends); and the HEAD of a GET+HEAD route (`/healthz`) is left out of the document, because FastAPI
  would give it the GET's operationId.
- As built (task-035, `api/search.py`, `api/papers.py`, `api/meta.py`, `api/models.py`; the models are the
  contract):
  - Each router is declared with `prefix="/api/v1"` and included directly, because FastAPI 0.141 leaves
    `scope["route"].path` relative to the router that declared a route, and a prefix added by nesting
    routers drops out of the access line's `route`.
  - `GET /search` calls `openproceedings.search.run`, the function `op search` calls, on the one engine
    the request read. It expands every wildcard first, then collects the match set once for `total` and the
    page, then does exclusion accounting with that `total`, then reads the page's display records. The API
    also asks for the facets (`TantivyEngine.facets`) and each hit's highlights (`engine/highlight.py`), so
    its ids, order, `total` and `excluded` equal `op search`'s for the same query and index (a contract
    test compares them). Parameters: `q` (required), `mode` (`native` | `scholar`, default `native`),
    `sort` (`relevance` | `year_desc` | `year_asc` | `title`, default `relevance`), `offset` (≥ 0,
    default 0; past the end gives an empty page), and `limit` (0 to 200, default 50). A value outside these
    ranges is a 422 `API_BAD_PARAM`. It is never clamped. A query that doesn't parse is a 422 whose `code`
    is its first error's and whose `diagnostics` are every error. `query.expansions` is keyed
    `<stem><op>` (`calibrat*`), each with its full sorted term list. `facets` has all four filter fields
    (`venue`, `year`, `track`, `status`), and only values that occur. Years are strings, and values are sorted by name. A hit
    carries exactly the fields in the `SearchResponse` example. Its `urls` has `forum`, `pdf`,
    `proceedings` and `doi`, and a missing one is null.
  - `POST /parse` takes `{q, mode}` (no other keys) and answers **200 even when the query has errors**:
    that is the ParseResult as spec 02 defines it (`errors` non-empty, every Optional null), which the
    editor draws as squiggles. That includes an over-long query: `parse` checks the 2,000-code-point cap
    first, in O(1), and returns `errors=[PARSE_TOO_LONG]` without lexing. Only a malformed body is refused
    (422 `API_BAD_PARAM`). The 422-on-parse-error rule applies to endpoints that run the query (`/search`,
    `/export`, `POST /records`). **Correction to TASK-035 AC #2** (the task is completed, so the CLI can't
    edit it): the AC says "Parse errors are 422", but that holds only for endpoints that run the query.
    `/parse` reports them in a 200 (task-035 review, Should 5).
  - `GET /papers/{id}` answers `{index_version, tokenizer_version, query_version, paper}`, where `paper` is
    the spec 01 `PaperRecord` (provenance and `content_hash` included). The served index decides whether the
    id exists. Otherwise the answer is 404 `API_PAPER_NOT_FOUND`, whose message never repeats the id. An id
    that isn't shaped `op:<venue>:<year>:<native>` gets that 404 without the index being asked. The index
    stores only the display record, so the full one comes from the snapshot it was built from:
    `<data_dir>/snapshots/<the index manifest's snapshot>`, which must hash to the manifest's
    `snapshot_hash`. That snapshot is verified **when the index is loaded**
    (`api/state.py::snapshot_records`, next to opening the engine and before the swap).
    `ingest.snapshot.RecordFile` makes one verifying pass and holds each record's byte range, for the
    served index and the one before it. **A deployment must ship that snapshot beside the index.** If it is
    missing or different, the load fails (`index_load_failed`, ERROR). At startup that means 503
    `API_INDEX_NOT_LOADED`; on SIGHUP the old index keeps serving. It is never a record without its
    provenance, and never a re-hash per request. Only a snapshot file that becomes unreadable after the load
    is a per-request 500 `API_INTERNAL`.
  - `GET /meta` answers the three versions, plus `index_versions` (every index directory on the instance,
    sorted, with the served one included), `text_fields` (`title`, `abstract`), `filter_fields` (`venue`,
    `year`, `track`, `status`), and `values` (`venue`, `track` and `status`: the vocabularies the parser checks
    filter values against, so autocomplete never offers a value it refuses).
  - Every route that reports `index_version` needs a loaded engine, `/parse` and `/meta` included (503
    `API_INDEX_NOT_LOADED` before the first load).
- As built (task-038, `api/coverage.py`, `coverage.py`): `GET /coverage` answers the three versions plus
  `snapshot` (`name`, `snapshot_hash`, `crawl_date`, `crawl_from` and `crawl_to` (the first and last fetch),
  `built_at`, `sources`), `totals` (`records`, `abstract_missing`, `unknown_track`, `unknown_status`) and
  `venue_years`: one entry per venue-year, ordered by venue name then year, with the same four counts and
  `cells`, a `{track, status, count}` per non-empty cell in vocabulary order (`vocab.py`; `unknown` last).
  - The numbers are the manifest of the snapshot the served index was built from (`counts`,
    `abstract_missing`, `unknown_track`, `record_count`: counted from the records once, at snapshot build),
    reshaped by `coverage.breakdown`, which never recounts. `unknown` is never folded: it is its own cell,
    and every venue-year carries `unknown_track` and `unknown_status`, 0 included. Missing abstracts are per
    venue-year, the manifest's granularity (the M4 abstract threshold is per venue-year too).
  - Computed **when the index is loaded** (`IndexState._load` → `api/coverage.py::compute`, right after the
    snapshot is verified and before the swap; task-038 review). It is stored beside the snapshot's records,
    for the served index and the one before it (`IndexState.coverage`). The load's one pass over the records
    also counts them per (venue, year, track, status) and counts missing abstracts per venue-year. These
    counts must equal the manifest's cells and `abstract_missing`, and the records must number the index's
    documents. Any of these failures makes the load fail, logged as `index_load_failed` (ERROR) with a
    `reason` constant and never a path: a manifest whose maps disagree, a track or status outside the
    vocabulary, a manifest that disagrees with the records, a missing or different snapshot, or a record
    count that differs from the index's document count. The reasons are `snapshot_missing`,
    `snapshot_hash_mismatch`, `manifest_invalid`, `counts_mismatch`, `abstract_missing_mismatch` and
    `doc_count_mismatch`. At startup the failure is 503 `API_INDEX_NOT_LOADED`; on SIGHUP the old index and
    its coverage keep serving. Coverage is never partial and never recomputed per request. One
    `coverage_computed` INFO line is written per load.
  - Not yet: which statuses a venue-year's sources *can* contain (spec 07 §C "statuses indexed") and crawl
    dates per source; neither is in the manifest (task-082).
- As built (task-036, `api/export.py`):
  - `GET /export` takes `q` (required), `format` (`ris` | `csv` | `bibtex` | `jsonl`, required), `mode`
    (default `native`) and `index_version` (optional). Its body is the bytes `op export` writes for the same
    query, index and UTC date: both run `export.header` and `export.entries` over
    `TantivyEngine.documents`, and a contract test compares them for every format. Records are sent in
    chunks of about 64 KiB.
  - Everything that can refuse happens before the first byte, in the one envelope: the length cap and the
    parse (422 with diagnostics), the pin, every wildcard's expansion (422 `WILDCARD_TOO_MANY_EXPANSIONS`,
    each over-cap wildcard located in `q` by `search.expanded`, as `/search` does), then the one collection
    of the match set that gives `X-Total`. Then a sync generator streams from the engine the request took,
    so an export started before a hot swap finishes on its index (contract test). A failure after the
    first byte is logged by the last catch and marks the access line `aborted: true`. A stream whose
    record count differs from `X-Total` fails the same way after its last record; it never ends as if
    complete.
  - Headers: `X-Total`, `X-Index-Version`, `Content-Disposition: attachment;
    filename="openproceedings-<index_version>-<first 12 of canonical_hash>.<ext>"` (`ris`, `csv`, `bib`,
    `jsonl`), and `Content-Type` `application/x-research-info-systems`, `text/csv`, `application/x-bibtex`
    or `application/x-ndjson`, each with `; charset=utf-8`. The access line carries `canonical_hash`,
    `total` and the `index_version` exported.
  - `index_version` must look like one (`[0-9a-f][0-9a-f-]{0,63}`; `current` is not a version), else 422
    `API_BAD_PARAM`. The served version is the served engine. Any other is `IndexState.pinned`: it resolves
    `<data_dir>/indexes/<v>` exactly as the configured index is (`state.index_path`; never
    `cli.resolve_snapshot`), refuses a name that resolves to another directory (an alias symlink) or whose
    manifest names another version, opens it read-only once (`index_pinned_opened` INFO) and keeps one such
    engine besides the served one. Not on this instance: 409 `API_INDEX_VERSION_UNAVAILABLE`. A pinned
    index that fails verification is a 500.
  - `record_id` is not accepted yet (task-037): it will resolve to the record's `index_version` in
    `export.pinned_engine`, before the stream starts, with 409 `API_RECORD_MISMATCH` for a `mismatch`
    record.

## Testing

- Contract tests for each endpoint using an in-process `TestClient` over the 5k-record fixture index.
- Export round-trips: parse the RIS/CSV/BibTeX output back and get the same IDs and fields.
- Search-record replay tests for the reproduced, drifted and mismatch paths. The mismatch path uses a
  fixture record inserted with a wrong `ids_hash` or `excluded` (the store stays append-only), and asserts a `200` with
  `status: "mismatch"` plus one `API_REPLAY_MISMATCH` ERROR log line.
- An export with `record_id` of a `mismatch` record returns 409 `API_RECORD_MISMATCH` and streams nothing.
- An OpenAPI snapshot test, so any contract change shows up in the PR diff.
