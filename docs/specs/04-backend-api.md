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
- Every response carries `index_version`, `tokenizer_version` and `query_version`. A JSON response carries
  them in the body. A non-JSON response (an export) carries them as `X-Index-Version`, `X-Tokenizer-Version`
  and `X-Query-Version` headers, exposed to CORS. `query_version` versions
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
  `/export`, `POST /records`, and `GET /papers/{id}` given a `q`). `POST /parse` **reports** a parse: any well-formed body is a `200` whose
  `errors` hold those same diagnostics; only a malformed body is a `422 API_BAD_PARAM`.
- No authentication in v1. Rate limiting is per IP (a token bucket in the app, set in config). CORS
  allowlist comes from config.
- **Shapes, as frozen for the first `/api/v1` release** (M3a review-gate; `backend/tests/contract/test_contract_v1.py`):
  - **Every field a response sends is required** in the schema, a null or defaulted one too (response models,
    `Urls`, `PaperRecord`, `Diagnostic`, the AST nodes, a stored record: `json_schema_serialization_defaults_required`),
    so a client may rely on the key being there. The one optional key is an error's `diagnostics`: present
    (non-empty) on a query refusal, **absent otherwise, never null**. A hit and its paper agree field by field.
  - **Clients ignore unknown keys.** Adding a response field is non-breaking within v1, so no response schema
    says `additionalProperties: false` (`api/openapi.py::open_response_objects`; the server itself never sends
    a key its model doesn't declare). Request bodies (`ParseRequest`, `RecordRequest`) stay closed: an
    unknown key there is 422 `API_BAD_PARAM`. Integer bounds are integers (`minimum: 1000`, never `1000.0`).
  - **Counts are `*_total`**: `added_total`/`removed_total` in a replay and in a diff (where `added`/`removed`
    are the id lists), beside `total`.
  - **One timestamp form**: an RFC 3339 date-time in UTC with a `Z` suffix, `YYYY-MM-DDTHH:MM:SS[.ffffff]Z`
    (fractional seconds only when the source had them), typed `format: date-time`: a record's `searched_at`,
    every `crawl_dates` end, `/coverage`'s `built_at`, a provenance claim's `fetched_at`. Manifests store
    `…+00:00`; the API renders them in this form (`openproceedings/timestamps.py`) and never rewrites the
    files. A calendar date (`crawl_date`) is `YYYY-MM-DD`, `format: date`.
  - **Crawl windows have one shape**, `crawl_dates: {"*": {from, to}, <source>: {from, to}…}`, in a record and in
    `/coverage`'s `snapshot`: `*` is the corpus-wide window, a source that carries its own adds its key.
  - **Parameters are exact.** Every route refuses a query parameter it doesn't declare, or one given twice,
    with 422 `API_BAD_PARAM` naming it (`/search?limt=5`, `/search?index_version=…`, `?q=a&q=b`), so a typo is
    never answered as if the parameter were absent. The exceptions are FastAPI's own `/api/v1/openapi.json`
    and `/api/v1/docs` (not API routes; they ignore any parameter). A trailing slash is not redirected: `/search/` is 404
    `API_NOT_FOUND`. A path id has its `pattern` in the schema; a **malformed paper id or record id is 422
    `API_BAD_PARAM`**, an unknown well-formed one 404, and neither message repeats it. The paper-id pattern
    is `^op:[a-z][a-z0-9]*:[0-9]{4}:[A-Za-z0-9_-]+$`: `venue` is an open enum, so a venue this code doesn't
    know is well-formed and a 404, never a 422. Every parameter is
    described in the schema (`q` names its 2,000-code-point cap).
  - **Open and closed enums** (decision-009; `OPEN_ENUMS`/`CLOSED_ENUMS` in `api/openapi.py`, and a test fails
    on an enum in neither). **Open** — a new value may appear within v1, and a client handles one it doesn't
    know (the schema says "Open set"): error codes, diagnostic codes (a stored record's are plain strings),
    `venue`, `track`, `status`, `presentation`, a provenance claim's `source` and `field`, the text and filter
    field names, `ChangedInput.input`, and a `/parse` filter clause's `reason` (decision-011). **Closed** — a new value is a breaking change: `mode`, `sort`, the
    export `format`, the replay `status`, `ChangedInput.kind`, a wildcard's `op`, `include`.
  - **`ErrorBody.code` is its own schema, `ErrorCode`**: exactly the registry's codes that have an HTTP status
    (`PARSE_*`, `FIELD_*`, `WILDCARD_*`, the `API_*` ones but the log-only `API_REPLAY_MISMATCH`), derived from
    the registry and tested against it. `diagnostics` is present on the `PARSE_*`, `FIELD_*` and `WILDCARD_*`
    refusals and on `API_TOO_MANY_VERIFIED_CLAUSES` and `API_QUERY_TOO_COSTLY` (decision-010), the two
    `API_*` codes that point into `q`.
  - **Headers are in the contract**: an export's 200 declares `X-Total`, `X-Index-Version`,
    `X-Tokenizer-Version`, `X-Query-Version` (this code's, on a `record_id` export too) and
    `Content-Disposition`; every route's 405 declares `Allow` and its 429 `Retry-After` (not `/healthz`'s,
    which is never limited; the 429's description names every bucket that can refuse: the client's, its
    network's, a query's position-verified clauses, the save ceilings); every route that runs a query
    (`/search`, `/export`, `/papers/{id}`, `POST /records`, `GET /records/{id}`, `/diff`) declares its 503 with `Retry-After`
    (sent with `API_BUSY`); `POST /records`'s 201 declares `Location`. CORS exposes all of them.
  - `info.version` is the API version, `v1`. operationIds are `verb_noun`: `search`, `parse_query`, `export`,
    `get_paper`, `get_coverage`, `get_meta`, `get_healthz`, `create_record`, `get_record`, `get_record_diff`.
  - A request body over `ApiConfig.max_body_bytes` (64 KiB; the longest valid body, 2,000 astral code points
    as JSON escapes, is ~24 KB) is 413 `API_BODY_TOO_LARGE`, refused before it is read (task-079).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/parse` | `{q, mode}` → 02's `ParseResult`: `mode`, `ast`, `effective_ast` (the UI tree shows the defaults), `canonical`, `canonical_hash`, `identification_query`, `defaults`, `warnings`, `errors`, `translations` (`identification_ast` stays server-side), plus `filters`: each filter field's top-level clause (span, values, `toggleable`, `reason`) for facet clicks (02 §Filter clauses; decision-011). Called as you type, debounced. |
| `GET` | `/search` | `q, mode, sort, offset, limit(≤200)` → `SearchResponse` |
| `GET` | `/papers/{id}` | The full record, provenance included; with an optional `q` (and `mode`), whether that query matches it and its `highlights`, exactly as `/search` gives them for that paper (task-087) |
| `GET` | `/export` | `format=ris\|csv\|bibtex\|jsonl` and either `q` (with `mode` and an optional `index_version`) or `record_id` (with `mode` at most `native`) → a stream of the **entire** matched set, ordered by `id`, served from the pinned index; with `record_id`, exactly the record's stored ids from its index (409 `API_INDEX_VERSION_UNAVAILABLE` if that index is gone, 409 `API_RECORD_MISMATCH` if its replay is a `mismatch`) |
| `POST` | `/records` | Freezes a search as an immutable **search record** → 201 `{record_id, page}` plus the three versions, with `Location: /api/v1/records/<record_id>` |
| `GET` | `/records/{id}` | The stored record, plus a replay check (see below) |
| `GET` | `/records/{id}/diff` | For a record of any status: added and removed ids (with titles), paged, and which `index_version` inputs changed (empty unless `drifted`) |
| `GET` | `/coverage` | Counts per venue × year × track × status, abstract-missing counts, snapshot date |
| `GET` | `/meta` | Current and servable `index_version`s, the field names and the venue, track and status vocabularies (these feed the UI's autocomplete), and this instance's query `limits` |
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
  "facets": { "venue": {...}, "year": {...}, "track": {...}, "status": {...} },
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
  lines (the track, then `status:<status>`), and the provenance `N1` = `openproceedings <index_version> · query
  <canonical_hash> · exported <UTC date>` (for an export pinned by a search record, `/export?record_id=`,
  followed by ` · record <record_id> · searched <UTC date of searched_at>`), always the last `N1`. A paper that
  is not `accepted` has one more `N1` before it: `Submitted to <venue string>; status: <status in words> (not
  in its proceedings).` (`unknown` reads "not known to be in its proceedings"; `desk_rejected` reads "desk
  rejected"), so the Notes a screener sees say it plainly; `TY` and `T2` are unchanged. Checked against
  the reference RIS parser, `scholarmend.parse.parse_ris` (the pinned `scholarmend` PyPI package), plus one
  fixture imported into Covidence by hand (`docs/results/2026-09-27-covidence-check.md`, done 2026-09-27).
- **Status in every format** (task-004 review). The venue string names the conference a paper was
  *submitted to*, so a rejected or withdrawn paper still reads "ICLR 2024". A screener sees its status as
  RIS `KW  - status:rejected` and the status `N1` sentence, but **Covidence shows neither to screeners**
  (the 2026-09-27 hand check: its screening card has no keywords, notes or URL), so a review screening in
  Covidence must exclude by status before import: keep the default `status:accepted` filter, or filter the
  CSV's `status` column. Zotero and EndNote do show both. CSV and JSONL have the
  `status` column, and BibTeX has
  it in `keywords` and in the entry type below. RIS keeps `TY  - CPAPER` for every status, so one export
  imports as one reference type.
- **`TY` is `CPAPER`, not `JOUR`** (task-004). Every exported paper is a conference paper. Zotero's RIS
  translator (`RIS.js`, 2026-01-05) imports `CPAPER` as `conferencePaper` and puts `T2` in its
  `conferenceName`; a `JOUR` would become a `journalArticle` with the conference in `publicationTitle`.
  EndNote reads `CPAPER` as *Conference Paper*. EndNote's default duplicate check compares Author, Year and
  Title *within one reference type*, so a copy of the same paper exported as `JOUR` or `CONF` by another
  database is only caught if the Reference Type box is unticked in its Duplicates preferences. Covidence
  matches duplicates on title, year, volume and authors, not on type
  ([Covidence FAQ](https://support.covidence.org/help/how-does-covidence-detect-duplicates)). The hand
  check above found `CPAPER` imports cleanly (title, abstract, authors, year, source line, DOI, our `ID` as
  Ref ID), and that Covidence matches our record against copies with a volume, another type (`CONF`,
  `JOUR`), another source string, or initials-only authors, but **not** against a copy dated a different
  year, which screeners merge by hand. Its fixture is pinned byte for byte by
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
  §Sources: NeurIPS proceedings for all years, from 1987; ICLR on OpenReview from 2013; ICML on PMLR from
  2013's v28; the crawl starts in 2013, decision-013). Sources,
  checked 2026-09-27: [proceedings.neurips.cc](https://proceedings.neurips.cc/) labels 1987–2017 "NIPS" and
  2018 on "NeurIPS"; the board announced the new acronym on 16 November 2018, before that December's
  meeting ([Synced, 2018-11-19](https://syncedreview.com/2018/11/19/name-flip-flop-nips-is-now-neurips/));
  [neurips.cc](https://neurips.cc/) calls 2026 "The Fortieth Annual Conference on Neural Information
  Processing Systems" (so 1987 is the first). [iclr.cc](https://iclr.cc/About) lists its conferences from 2013.
  [icml.cc](https://icml.cc/) calls 2026 the "Forty-Third International Conference on Machine Learning" and
  PMLR's v202 is the 40th (2023), so, counting back annually, 1988 is the 5th, the first held as a conference
  (the earlier meetings were workshops). `backend/tests/unit/test_export.py` pins each era's first year, the
  rename and recent years by hand, and every venue from 2013 to 2026.
- **CSV:** one row per paper, the columns of the schema in 01 plus the provenance columns `index_version`,
  `canonical_hash`, `exported_at`, `record_id` and `searched_at` (the last two empty unless the export is
  pinned by a search record; JSONL has the same five fields, null when not pinned), UTF-8 with a BOM (so
  Excel opens it correctly).
- **BibTeX:** `@inproceedings` for an `accepted` paper, with `booktitle` = the venue string. Any other status
  (`rejected`, `withdrawn`, `desk_rejected`, `unknown`) is `@unpublished`, BibTeX's type for a paper with an
  author and title that was not formally published, and has **no `booktitle`**. Its `note` starts
  `Submitted to <venue string>, status: <status in words>.` (`desk rejected`: a bare `_` breaks LaTeX when
  a style typesets `note`; every other `_` in `note`, e.g. a record id's, is written `\_`) and then gives
  the provenance line, so the venue string is
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
  Provenance goes in `note = {openproceedings <index_version> · query <canonical_hash> · exported <UTC date>}`
  (plus ` · record <record_id> · searched <date>` when pinned by a record; after
  the `Submitted to …` sentence on an `@unpublished` entry).
  Every entry carries `openproceedings_id = {<id>}`, so a round-trip recovers the id of every record,
  proceedings-only (PMLR, NeurIPS) ones included. Output must pass `refaudit.bibtex.parse_string` (the pinned `refaudit` PyPI package).
- As built (task-030, `export.py`, used by `op export` and, byte for byte, by `GET /export` since task-036):
  - **RIS:** `TY  - CPAPER`, with `UR` forum, then pdf, then proceedings. Each record ends `ER  - `. Line breaks
    inside a value become single spaces and control characters are dropped, since RIS is line-based. URLs
    are validated at ingest as one-line http(s) addresses, so none can carry a forged record.
  - **CSV:** UTF-8 with a BOM (Excel); every field of the stored display record plus the facets and the
    provenance columns `index_version`, `canonical_hash`, `exported_at` (the UTC date), `record_id` and
  `searched_at` (empty unless pinned by a record). Two fields of
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
    differently can swallow the next. `&`, `%` and `#` are escaped. Every `@` is written `{@}` (BibTeX
    and refaudit open an entry at a bare `@` anywhere, so `@article{x,` in a title would become an entry;
    an odd backslash run before it loses one backslash). A value never ends on a backslash. An
    author name holding a standalone `and`, or `others`, is braced, so it isn't split or read as et al.
  - **JSONL:** one object per record, with `index_version`, `canonical_hash`, `exported_at`, `record_id` and
    `searched_at` (null unless pinned by a record): the lossless
    format (CSV's formula guard adds a `'` to some cells). U+2028, U+2029 and U+0085 are escaped, so a record
    stays one line for every reader.

  Each format is checked round-trip to its ids; BibTeX also against the pinned `refaudit==0.4.9`. `op
  export` counts what it wrote against the query's total before renaming its temporary file into place.
- Exports stream, and are not paginated or truncated. The response headers `X-Total` (equal to the search's
  `total`) and `X-Index-Version` say exactly which set was exported (with `X-Tokenizer-Version` and
  `X-Query-Version`). An export started during an index
  hot-swap finishes on the index it began on.
- An export pinned by `record_id` hands over exactly the cited set: the record's **stored** ids (sorted),
  read from the index the record names. The query is never re-run, so a later `query_version` changes
  nothing about what is exported (task-037 review). It is refused with 409 `API_INDEX_VERSION_UNAVAILABLE`
  when that index isn't on this instance, and with 409 `API_RECORD_MISMATCH` (§Error handling) when the
  record's replay status is `mismatch` or its stored list doesn't hash to its `ids_hash`: a set that breaks
  guarantee 4 is never handed to screening. `X-Total` is the stored list's length, which the record's `total` must equal (409 `API_RECORD_MISMATCH` otherwise).

## Search records (reproducibility, PRISMA)

`POST /records` freezes everything a methods section needs to cite and a replay needs to check:

| Field | Why |
|---|---|
| `input`, `mode`, `canonical`, `canonical_hash`, `identification_query` | what was searched, and the string that reproduces "identified" |
| `index_version`, `tokenizer_version`, `query_version`, `snapshot_hash`, `crawl_dates` (per source, from the manifest; only `*`, the corpus-wide from–to window, until M4) | the database version and when its contents were collected |
| `crawl_dates_kind` (per `crawl_dates` key: `crawl`, `scholar_query_dates` or `mixed`) | what those dates are: a bootstrap source's window is when its Scholar searches were run (Publish or Perish's local time, stored labelled UTC), not a crawl |
| `sources` (the manifest's source names) and `identification_citable` | whether `total` can be cited as a PRISMA identification number: `false` when every source is a bootstrap one (`vocab.bootstrap_only`, the test `op search`'s "bootstrap corpus" note uses), since the corpus is then an earlier search's output, not a database |
| `searched_at` (UTC) | the search date, which is separate from the crawl date |
| `total`, `excluded` (with `unknown` itemised) | the counts cited in PRISMA |
| `expansions`, `translations`, `warnings` | how the query was interpreted (PRISMA-S) |
| `ids` (sorted) and `ids_hash = sha256(ids)` | membership, for replay and for the diff |
| `dedup` (`merged`, and the manifest's not-merged conflicts by resolution: `ambiguous_not_merged`, `track_not_merged`, `venue_year_not_merged`) | the PRISMA-S item 16 deduplication-process statement (corpus-wide ingest merges, never a per-search removal count) |
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

The record page (05) is what a methods section cites. Records are stored in `data/records/records.sqlite`
(append-only, backed up with the snapshots).

As built (task-037 and its review fixes; `backend/src/openproceedings/records.py` holds the record,
`ids_hash`, the store and the replay, so `op record save`/`replay` (task-083) call the same functions; `api/records.py` is the
transport, `IndexState.pinned` in `api/state.py` loads older indexes):
- **`POST /records`** takes `{q, mode}` (no other keys) and answers **201** `{record_id, page, index_version,
  tokenizer_version, query_version}` with `Location: /api/v1/records/<record_id>` (the API resource). `page`
  is the record page's path, `/record/<record_id>` (05 §Pages), relative to the site (renamed from `url`
  before the first release: it is not the resource's URL). The query is refused exactly as `/search` refuses it (422 with diagnostics,
  `PARSE_TOO_LONG` before parsing, or after canonicalising when the canonical form is over the cap,
  decision-008) and nothing is written. It is re-run on the request's one engine:
  `search.run` (so `total`, `excluded` and `expansions` equal `/search`'s) plus `match_ids` for the ids.
- **Cost and capacity.** `POST /records`, `GET /records/{id}` and `/diff` each run a whole query, so each
  costs the rate limit's `export_weight`. A save is refused with 503 `API_RECORDS_STORE_FULL` (nothing
  written) once the store holds `ApiConfig.records_max_bytes` (default 1 GiB; `None` for no cap) or its disk
  has less than `records_min_free_bytes` free (default 256 MiB). An empty store always takes its first save.
  Reads are never refused. The store logs `records_store_full` (WARNING) when it fills and
  `records_store_recovered` (INFO) when a save fits again: one line per change of state, not per refusal.
  Saves are also held to two ceilings (`api/records.py::SaveCeiling`), taken together (a refusal by one
  spends nothing from the other): each client **network** (IPv4 /24, IPv6 /48, by the rate limit's client
  rule) to `ApiConfig.record_saves_network_burst` (default 10) at once, refilled at
  `record_saves_network_per_hour` (default 60), and every client together to `record_saves_burst` (default
  60), refilled at `record_saves_per_hour` (default 600), the backstop. Beyond either a save is 429
  `API_RATE_LIMITED` with `Retry-After` (the message says whether the instance or the client's network is
  at its ceiling), checked after the parse (a query that doesn't parse costs no save) and before the query
  runs; a save whose query then fails to run, or whose store is full, is refunded to both. A ceiling's first
  refusal logs `record_saves_throttled` (`scope` `instance` or `network`, `burst`, `per_hour`; never the
  network itself) and its next allowed save `record_saves_recovered`: WARNING and INFO for the instance
  ceiling (everyone's), DEBUG for a network's (one network throttling itself is not the operator's
  concern). The store is append-only, so its growth is bounded in time as well as in bytes, and one network
  can't spend the whole instance's ceiling. **Residual (accepted):** the instance ceiling is a backstop, so
  about ten /24 networks, each saving at its own ceiling (10 × 60 an hour is the instance's 600), can keep
  it empty for everyone; the network ceiling bounds one network, not a client spread over many.
- **The record** holds every field of the table, plus `record_id`, `body_version` (2), `schema_version` and
  `ranking_params` (the index's two other inputs, so a drifted replay can name a method change after the
  pinned index is gone). `crawl_dates` is keyed by source: `*` is the snapshot manifest's corpus-wide
  `crawl_window` (today's manifests have only that; a manifest must name its `sources`, or the save is a
  500: no sources named is not evidence of a crawl), and a source entry that carries its own
  `crawl_window` (the M4 crawlers) adds its own key. Every end is checked to be an ISO 8601 date-time and is
  sent in the one timestamp form (§Conventions; a stored `…+00:00` reads back as `…Z`).
  `crawl_dates_kind` has the same keys: a source in `vocab.BOOTSTRAP_SOURCES` (`ris`) gives
  `scholar_query_dates`, any other `crawl`, and `*` is the one kind of all the manifest's sources, or `mixed`.
  `sources` is the manifest's `sources` keys, sorted; `identification_citable` is `not
  bootstrap_only(sources)` (false for today's RIS-only corpus; the record page then shows the CLI's caution
  and no methods text, 05). `dedup` is `{merged: manifest merges.total, ambiguous_not_merged,
  track_not_merged, venue_year_not_merged: manifest conflicts.<each>, 0 when absent}`.
  `searched_at` is UTC to the second (`…Z`). `semantic_version` is null until the near-miss panel exists
  (M5). `excluded` keeps the pinned bucket order.
- **`ids` are left out of `GET /records/{id}`** (`record.ids` is null) unless `?include=ids`; to fetch the
  papers themselves use `GET /export?record_id=` (§Exports).
- **`ids_hash`** is `sha256("\n".join(sorted(ids)))`, code-point order, no trailing newline, with
  known-answer tests (the empty set is `sha256("")`).
- **Record ids** are `secrets.token_urlsafe(9)`: 12 characters of `[A-Za-z0-9_-]`, about 72 random bits,
  redrawn when the drawn id is taken or doesn't start with a letter or digit (an id starting with `-` would
  be written to a CSV cell with the formula guard's `'` and not read back as itself). Anything else is 422 `API_BAD_PARAM` (the path parameter's `pattern`, as
  for a paper id); an unknown id is 404 `API_RECORD_NOT_FOUND`, and neither message repeats the id.
- **The store** is `<data_dir>/records/records.sqlite`: its own directory (mode 0700, file 0600), because
  WAL mode writes `-wal` and `-shm` files beside the database, so the directory, not just the file, must be
  writable. Created on the first save (a read never creates it; a removed file is re-created). Tables
  `schema_version`, `id_sets (ids_hash, ids)` and `records (record_id, index_version, searched_at, id_set,
  body)`. Id lists are content-addressed: `id_sets.ids` is the zlib-compressed `\n`-joined list under its
  own `ids_hash` (checked on every read), so saving the same set again costs one body (~1 KB). `body` is the
  record's JSON without `ids`. Every table has `BEFORE UPDATE` and `BEFORE DELETE` triggers that abort
  ("append-only"), and `records` and `id_sets` a `BEFORE INSERT` trigger refusing an existing key (SQLite's
  REPLACE deletes without firing DELETE triggers unless `recursive_triggers` is on). The triggers stop
  mistakes; they are not a security boundary against someone with the file. A store with a newer
  `schema_version` is refused. One connection per call. `RecordStore.pinned(index_version)` counts the
  records that pin a version (check it before retiring one).
- **Stored bodies are read with frozen, tolerant types** (a diagnostic's `code` is a plain string, unknown
  keys are ignored), so a later change to the live enums never makes an old record unreadable; a body whose
  `body_version` is newer than this code's is a 500. `backend/tests/fixtures/records/record-v1.json` is a
  committed v1 body that must stay readable. **Body version 2** added `sources`, `identification_citable`,
  `crawl_dates_kind` and `dedup.track_not_merged` / `venue_year_not_merged`: a v1 body reads them as null
  ("not recorded", never guessed; the record page treats a null `identification_citable` as not citable),
  and a v2 body missing them, or whose `crawl_dates_kind` keys aren't its `crawl_dates` keys, is unreadable (500). Citability is checked against `sources` on write only (a record whose `identification_citable` contradicts them is never written): which sources are bootstrap ones is this code's `vocab.BOOTSTRAP_SOURCES`, and a stored body must outlive a change there, read and replayed with its citability as saved.
- **Replay** (`GET /records/{id}`, 200 `{index_version, tokenizer_version, query_version, record, replay}`;
  the top-level versions are those the replay ran on) re-parses the stored `canonical` in native mode, never
  `input`. It runs on the record's own index when this instance has it (served, or loaded on demand; an
  engine handed back for another version counts as unavailable), else on the served index. On its own index
  and under its own `query_version`, it is `reproduced` if `ids_hash` and `excluded` both match, the
  canonical re-parses to the same canonical string, `canonical_hash` and `identification_query`, the
  re-run's `expansions` are the stored ones, the index's manifest gives the stored `snapshot_hash`,
  `tokenizer_version`, `schema_version` and `ranking_params`, and the stored id list hashes to `ids_hash`
  and has `total` ids (an export sends that list and its length); otherwise
  `mismatch`: ERROR `replay_mismatch` (`code` `API_REPLAY_MISMATCH`, `record_id`, the versions, which of
  `ids_match`, `excluded_match`, `canonical_match`, `identification_match`, `expansions_match`,
  `inputs_match` and `stored_ids_match` failed, and `refused`: the refusal
  code when the canonical no longer runs, else null) the first time this process sees that record mismatch, DEBUG after that. A
  record naming an `index_version` this instance doesn't hold, whose index inputs are nonetheless the served
  index's own (whatever its query version), was forged or corrupted (a different version always has
  different index inputs): also `mismatch`,
  logged the same way with `index_version_match: false` and `ran_on`, never a 500. Any
  other case is `drifted`: when only the query version differs and the record's own index is here, the replay
  runs on that index, so `changed` holds just `query_version`; otherwise `replay.changed` lists each
  differing input (`snapshot_hash` kind `corpus`; `tokenizer_version`, `schema_version`, `ranking_params`,
  `query_version` kind `method`) with its recorded and current value. `replay` also has `total`,
  `excluded`, `ids_hash`, `ids_match`, `excluded_match`, `added_total`, `removed_total` (counts, named as
  in the diff), `membership_identical` (true on `+0/−0`) and `verified_clauses` (the canonical's
  position-verified clauses; null when it doesn't parse).
- **A refused replay** (the canonical string no longer parses, or a wildcard now expands past the cap) has
  `refused` set to that code and compares nothing: `total`, `excluded`, `ids_hash`, `ids_match`,
  `excluded_match`, `added_total`, `removed_total` and `membership_identical` are null. Its status stays `drifted`, or `mismatch` under the record's own versions.
- **A withheld replay** is one this instance won't run: its canonical has more position-verified clauses
  than `ApiConfig.max_verified_clauses`, or its position checks would read more than
  `max_verification_candidates` documents on the index it runs on (§Rate limit; decision-010). It is
  still a 200, never a 422, so the record itself stays readable: nothing is compiled or charged for its
  clauses, `refused` is `API_TOO_MANY_VERIFIED_CLAUSES` or `API_QUERY_TOO_COSTLY` ("not re-run on this
  instance: its limit is below what the record's query needs"), and every count is null as for a refused
  replay. It is never `reproduced` and never `membership_identical`. On the record's own index under its own
  query version its status is `drifted` with `changed: []` (the status enum is closed; `refused` says why),
  unless a check that needs no run fails (the canonical re-parse, the index's inputs, the stored list),
  which is a `mismatch`, logged as any other; elsewhere it is `drifted` with its changed inputs. The
  withholding is not a mismatch and logs no `replay_mismatch`, and `/export?record_id=` still streams the
  stored ids (it never re-runs the query; only a `mismatch` blocks it). Raising the limit replays it.
- **Pinned indexes** load on demand, read-only, by the served index's rules (`state.index_path`: an
  index_version resolving to itself directly under `<data_dir>/indexes/`; never `resolve_snapshot`), and
  are opened (verified) by the same engine class, so "available" means loadable by this code: an index built
  with another tokenizer or schema version is not, and its records replay as `drifted`. The loader is
  `IndexState.pinned` (§Implementation notes, pinned indexes: the LRU, the remembered refusals and the log
  level per reason).
- **`GET /records/{id}/diff?offset=&limit=`** answers `{…versions, record_id, status, recorded_index_version,
  refused, changed, offset, limit, added_total, removed_total, added: [{id, title}], removed: [{id, title}],
  membership_identical}` for any status. Each list is the page `[offset, offset + limit)` of its id-sorted
  list (`limit` 0–200, default 50; out of range is 422 `API_BAD_PARAM`, never clamped); the totals are always
  in full. A title comes from the index the replay ran on, null when it doesn't hold the paper. A refused
  replay has empty lists and null totals.
- **For `/export?record_id=` (task-036)**: `api.records.stored_record(request, record_id)` (422/404) and
  `refuse_mismatch(request, record, engine)` (409 `API_RECORD_MISMATCH` on a `mismatch` replay), which
  `/export` calls after pinning the record's index (the only production callers; the `require_citable` and
  `replay_status` wrappers were removed at the M3a gate as unused). Pass the route's `EngineDep` engine so a
  request never reads the served index twice. A `reproduced` replay also requires
  the stored id list to hash to the record's `ids_hash`, since that list is what `/export` hands over.
- Access line: `canonical_hash`, `total` (the replay's) and `index_version` (the one the replay ran on).
  No log line carries the input, canonical or identification strings: the record stores them, the logs don't.

## Error handling

Every error uses the one envelope `{error: {code, message, diagnostics?}}`. Codes come from the registry in
`backend/src/openproceedings/diagnostics.py` (error-diagnostics skill), and a status/code pair never changes
once released: changing one is a breaking change under `/api/v1`.

| Situation | HTTP | `code` |
|---|---|---|
| Query does not parse, uses an unknown field or value, or has a bad wildcard (incl. more than 200 expansions) (on endpoints that run the query) | 422 | `PARSE_*`, `FIELD_*`, `WILDCARD_*` (diagnostics carry the spans); a query over 2,000 code points is `PARSE_TOO_LONG`, rejected before parsing, and so is one whose canonical form is over 2,000 code points, refused after canonicalising (decision-008) |
| A parameter is invalid (bad `sort`, `limit` > 200, unknown `format`, a malformed paper or record id), unknown to the route, or given twice; or a body is malformed | 422 | `API_BAD_PARAM` |
| Paper or search record not found (a well-formed id) | 404 | `API_PAPER_NOT_FOUND` / `API_RECORD_NOT_FOUND` |
| A pinned `index_version` is not available on this instance | 409 | `API_INDEX_VERSION_UNAVAILABLE` |
| Export requested for a record whose replay status is `mismatch` | 409 | `API_RECORD_MISMATCH` |
| A request body over `max_body_bytes` (64 KiB), by `Content-Length` or by the bytes of a chunked body, refused before it is read and before any other check (task-079) | 413 | `API_BODY_TOO_LARGE` |
| Rate limit exceeded: the client's or its network's bucket, a position-verified query's extra weight, or the record-save ceiling (its network's or the instance-wide one) | 429 | `API_RATE_LIMITED` (with `Retry-After`) |
| A search record can't be saved: the record store is over its size cap or its disk under the free-space floor (task-037) | 503 | `API_RECORDS_STORE_FULL` |
| A query needs a cold position verification and every verification slot is taken (refused, never queued) | 503 | `API_BUSY` (with `Retry-After`) |
| A query has more position-verified clauses than `ApiConfig.max_verified_clauses` (default 16, a backstop), refused before it compiles (decision-010; a replay over it is withheld, 200, §Search records) | 422 | `API_TOO_MANY_VERIFIED_CLAUSES` (diagnostics: one per clause, spanning it in `q`) |
| A query's position checks would read more than `ApiConfig.max_verification_candidates` (default 300,000) candidate documents, summed over its verified clauses and their fields, refused before any is verified (decision-010; a replay over it is withheld, 200) | 422 | `API_QUERY_TOO_COSTLY` (diagnostics: one per verified clause, spanning it in `q`, with its count per field) |
| No index loaded yet (startup, or the first load failed; a failed swap keeps serving the old index) | 503 | `API_INDEX_NOT_LOADED` |
| Anything unexpected | 500 | `API_INTERNAL` (logged at ERROR with the request id; message never echoes input) |
| No such endpoint (task-034) | 404 | `API_NOT_FOUND` |
| An endpoint that exists, called with another method (task-034) | 405 | `API_METHOD_NOT_ALLOWED` (with `Allow`) |

A replay `mismatch` is **not** an HTTP error. It is a `200` with `status: "mismatch"`, logged as
`API_REPLAY_MISMATCH` (§Search records).

**The only responses that are not the envelope** come from outside the app, before it runs: a CORS
preflight from an origin that isn't allowed (Starlette's plain-text 400 `Disallowed CORS origin`), uvicorn's
own plain-text 503 once `limit_concurrency` connections or tasks are held, and uvicorn's 400 for a request
head (request line and headers) over 64 KiB. A client treats a non-JSON 5xx as "busy, retry" (spec 05
§Error states).

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
    swaps the one reference to the served bundle (`state.Served`: the engine, its snapshot's records and its
    coverage, built and checked together); a failed reload logs `index_load_failed` at ERROR (with `error`,
    a `reason` constant — `not_found`, `outside_indexes`, `files_mismatch`, `manifest_changed`,
    `doc_count_mismatch`, `unreadable`, `tokenizer_version_mismatch` and the other `*_mismatch` of an index
    this code can't serve, a snapshot's reasons below, or an OSError's errno name — `index_version_attempted`
    and `index_version_kept`, never a path) and keeps serving the bundle it had, so 503 means only that no
    index was ever loaded. Reloading the version already served keeps the engine.
  - Routes take the served bundle through `deps.ServedDep` (and its engine through `deps.EngineDep`): read
    once per request, so a request or a stream in flight finishes on the index it started on, with that
    index's records (`/papers`) and coverage, however many swaps happen before it ends (M3a review). `deps.checked_query(q)` raises 422 `PARSE_TOO_LONG` (the
    parser's own diagnostic, `parser.too_long`) before anything reads the query; a query within the cap
    whose canonical form is over it is `PARSE_TOO_LONG` too, from `parse` after canonicalising
    (decision-008), so a saved canonical string always re-parses.
  - The client for the rate limit is the TCP peer, or, when the peer is a trusted proxy, the right-most
    `X-Forwarded-For` hop that is not one. An IPv4-mapped IPv6 address (`::ffff:a.b.c.d`, as a dual-stack
    bind reports IPv4 peers) counts as its IPv4 address, both as a key and when matching trusted proxies.
    IPv6 clients are bucketed per /64. One host usually holds a whole /64, but an attacker holding a /48 gets
    65,536 buckets, so every request is also charged to its client's **network** bucket (IPv4 /24, IPv6 /48;
    `network_capacity` and `network_refill_per_second`, default 4 × the client's): a request passes only if
    both hold its cost, and a refusal by one spends nothing from the other. `/healthz` (GET or
    HEAD, for uptime monitors; HEAD is its own route, left out of the OpenAPI document so operation ids stay
    unique) costs nothing; `/export` and every record route (`POST /records`, `GET /records/{id}`, `/diff`)
    cost `export_weight`, charged before routing. A
    query's **position-verified clauses** (spec 03: a phrase with a wildcard, a NEAR the index can't answer)
    are counted from the AST (`engine.compile.verified_clauses`, by `verifies`'s rule; a test holds the
    count equal to the compiler's own): more than `ApiConfig.max_verified_clauses` (default 16: a backstop, admitting every Trust-Evals string) is 422
    `API_TOO_MANY_VERIFIED_CLAUSES` (decision-010), one diagnostic per clause, before anything compiles;
    otherwise the query costs `ApiConfig.verified_cost` **per clause**: `verified_weight` when set, else
    `export_weight` lowered to the smaller bucket's capacity over the cap (default min(10, 60 / 16) = 3.75), and
    `max_verified_clauses` × a set `verified_weight` must fit the smaller bucket (the config refuses it
    otherwise), so every clause up to the cap costs its share and a query at the cap can always be paid. The
    rest is charged after the parse and before compiling (`deps.charge_verified` from `deps.searchable`,
    `middleware.charge`). The clause count doesn't measure the work, though: a clause's cold verification
    reads every **candidate** (each document holding all its items in the field, 37-56 µs each by shape, wildcard-phrase NEARs the
    dearest), and a word
    NEAR itself makes every document holding it one (M3a round 3: 8 such clauses held the slot 63 s on 80k).
    So once the route has its engine, and after the wildcard cap, `deps.check_candidates` counts each
    verified clause's candidates per field from the inverted index (`TantivyEngine.candidates`; no document
    is read, and every clause counts, cached or not, so a refusal never depends on the memos): more than
    `ApiConfig.max_verification_candidates` (default 300,000, up to about 16 s of verification idle at 80k and more under load, which the deadline
    below bounds; above the heaviest real review query:
    Trust-Evals `main-2-pop`, 247,793 on the synthetic 80k index) is 422
    `API_QUERY_TOO_COSTLY`, one diagnostic per clause with its counts, before any is verified (`/search`,
    `/export`, `POST /records`). A refusal after the charge, `API_QUERY_TOO_COSTLY` or `API_BUSY`, gives the
    verified charge back (`middleware.refund_charged`; the route's own weight is kept). A replay
    (`GET /records/{id}`, `/diff`, `/export?record_id=`) is counted, capped and charged the same way on its
    re-parsed canonical string (parsed once, `deps.admit_replay`, on the engine it runs on), but over a limit
    it is withheld, not refused (§Search records). Within a request, every compile (the page, the facet
    worker's base, exclusion accounting) shares the ids of every verified clause it read, cold or from a memo
    (`tantivy_engine.Scope`; a compiled-memo hit brings its tree's ids along, round 4), so a memo trimmed
    meanwhile never makes it verify a clause twice, and the facet worker never verifies at all
    (`Scope.reader`): only the calling thread holds a slot. Should the worker miss a clause anyway (a bug),
    the caller recounts the facets itself and logs `facet_worker_recounted` (WARNING), never a 500. A clause's
    cost per candidate doesn't depend on its width or expansions (its token sets are built once per clause,
    round 4: a 300-item `rel*` phrase at 80k took 84 s before, 3.1 s after, like a 2-item one), so the
    candidate count is the whole bound. **The slot time used is charged after the fact**: a request that
    held a verification slot is debited one token per `RateLimit.verify_token_ms` (default 100 ms) of the
    verifying thread's **CPU** time in it (`time.thread_time`, round 5: wall time, which other requests'
    load on the GIL stretches, billed one main-2-pop query 155 tokens idle and 1,090 under contention), to
    its client's and its network's buckets, when it finishes (`RateLimit.debit_verification`; the access
    line's `verify_cpu_ms` and `verify_tokens`). A bucket may go below zero; the client then waits (429 with
    `Retry-After`) until the refill repays the debt (a bucket in debt is skipped when the least recently seen
    are dropped at `max_clients`, so the debt isn't forgiven; only if every other bucket were in debt would the
    oldest go), so a client sending cold queries back to back (each
    NEAR distance is a new, cold clause) holds the slot at most refill × `verify_token_ms` of the time: 10%
    a client and 40% a network at the defaults. The up-front per-clause charge stays, as the admission cost.
    **A deadline bounds the wall time** (round 5: the candidate ceiling bounds work, not wall time, and
    pure-Python verification competes for the GIL, so one admitted near-ceiling query held the slot 15.5 s
    idle, 35 s beside 4 busy clients and 109 s beside 8): a request's cold verifications together get
    `ApiConfig.max_verification_seconds` (default 30, `--max-verification-seconds`) of wall time from its
    first slot, checked every 1,000 candidates (`compile.CHECK_EVERY`: tens of ms apart, no measurable cost)
    and before each clause. Past it the loop stops and the request is 503 `API_BUSY` with `Retry-After`
    and a message naming the limit: the partial id list is dropped (no memo, scope or compiled query holds
    any of it), the per-clause charge is refunded, and the CPU time used is still debited. 30 s because
    main-2-pop, the heaviest real query, needs 10.2 s idle at 80k: it is served under paced load (idle 9.8 s;
    two clients at 1–2 requests/s each: 13.8 s and 21.1 s), but two clients paging as fast as their own rate
    limit allows pushed it past 30 s in 2 of 3 runs (round 6); a retry then finishes, since the clauses
    verified before the deadline were kept. No query holds the
    slot for minutes. The 503's `Retry-After` is the slot's; the CPU debit lands after the response, so the
    retry may be a 429 with its own, longer `Retry-After`. A replay past it is the same 503, not
    a withheld replay: the deadline depends on the moment's load, so it is the client's retry, not the
    record's `refused`. A verified clause with no candidates takes no slot and verifies nothing. Cold verification (a cache miss: seconds of pure Python per clause) runs in at most
    `ApiConfig.verification_slots` (default 1) at a time, on every engine the state opens
    (`TantivyEngine.verification_gate`); a query that needs another slot is refused at once with 503
    `API_BUSY` and `Retry-After: busy_retry_seconds` (default 5), never queued, so it can't hold a worker
    thread or stall `/healthz`. A query that needs no verification, or whose clauses are cached, never waits.
    Every 429 carries `Retry-After` in whole seconds.
  - Access line: one `request` line per request (INFO; `/healthz` at DEBUG) with `request_id`, `method`,
    `route` (the template; null when nothing matched, a 429 included), `status`, `ms`, `index_version`, and
    what a route adds with `deps.annotate`/`annotate_parse`: `canonical_hash`, `total`, `token_count`,
    `n_errors`, `error_codes`, `warning_codes` (at most 10 distinct codes, then `+N`), `verified_clauses`
    (the query's, a replay's too), `verification_candidates` (their candidates, summed; absent with none),
    `verify_ms` (the wall time the request held a verification slot; absent when it held none),
    `verify_cpu_ms` (the verifying thread's CPU in those holds), `verify_tokens` (what that CPU time was
    debited; absent likewise), and `code`, the error
    envelope's code, on every refusal (the body cap's 413, the rate limit's 429, a routing 404, `API_BUSY`, …)
    and every 500 (`errors.note_code`). Never `q`, the
    canonical or identification strings, messages or spans. `ms` is milliseconds to one decimal, the one form
    of every log line's `ms` (`logs.elapsed_ms`). An unexpected exception is one
    `request_failed` ERROR line with its type and frames (never its message), its cause's type, the cause's
    frames (`cause_frames`: Starlette wraps an exception its handler catches after a stream started in a
    RuntimeError whose own frames stop at the handler) and the cause's reason constant (`cause_reason`: a
    `SnapshotError`'s reason or an OSError's errno name, e.g. `ENOENT` for a snapshot that vanished under
    `/papers`), and a 500 whose message names the request id; nothing is re-raised to the server. Layers,
    outermost first: the access line, CORS, the last catch (`LastCatch`), the body cap (`BodyLimit`), the
    rate limit, then the app (whose app-wide `strict_query` dependency refuses unknown or repeated
    parameters), so a 500 or a 413 carries the CORS headers like any response. If the exception comes after the response started (a stream), the client has its status, so
    the access line keeps `status` as sent and adds `aborted: true`. A CORS preflight from an origin that
    isn't allowed is Starlette's plain-text 400 `Disallowed CORS origin`, not the envelope (it never reaches
    the app), and it still gets its access line.
  - Error mapping beyond the table: any other 4xx a framework raises is 422 `API_BAD_PARAM`, logged at DEBUG
    (nothing of ours raises one). A `PARSE_*`/`FIELD_*`/`WILDCARD_*` refusal from the engine carries
    `diagnostics`: `/search` locates each over-cap wildcard by its span in `q`
    (`search.run` sets `EngineInputError.diagnostics`; the exception type is unchanged, so `op search`
    still logs `EngineInputError`), and a refusal it can't locate has one diagnostic with `span: null`.
  - A request whose slot holds pass `ApiConfig.slow_verification_seconds` (default 5) logs one
    `verification_slow` WARNING (`verify_ms`, `threshold_ms`, and the request id from the log context): while
    it held the slot every other cold verification was 503 `API_BUSY`.
  - `op serve [--host] [--port] [--index] [--cors-origin …] [--trusted-proxy …] [--rate-capacity]
    [--rate-refill] [--export-weight] [--no-rate-limit] [--max-verified-clauses]
    [--max-verification-candidates] [--max-verification-seconds] [--log-query-text]` refuses an invalid combination as usage, naming each
    option and the validator's reason (never the value pydantic would quote), and runs one uvicorn process with
    its own access log off, `proxy_headers` off, and a 64 KiB request-head limit (uvicorn's 16 KiB would
    refuse a valid 2,000-code-point query in the URL). **Deploy note:** `GET /search?q=…` carries the query
    in the URL, so the reverse proxy in front (Caddy, task-065) must not log query strings. Log the path
    only, or turn its access log off; the app's own access line never holds `q`. The proxy's timeouts and
    request buffering are required settings (spec 08 §Deploy). uvicorn's loggers go
    through the JSON handler;
    httpx/httpcore are pinned to WARNING, and the root logger gets the same JSON handler at WARNING, so another
    library's warning (asyncio, fastapi) is JSON too. `--log-query-text` only lets the formatter keep
    query-text fields; no log call passes one today (the access line never carries `q`), so it changes nothing.
    uvicorn runs with `limit_concurrency` (`ApiConfig.limit_concurrency`, default 256: behind the proxy
    these are its pooled upstream connections) and `timeout_keep_alive` (`keep_alive_seconds`, default 5),
    so an idle connection doesn't hold a slot. A trusted proxy wider than /8 (IPv4) or /32 (IPv6) is refused
    (every client inside it could then set its own address), and so is `--no-rate-limit`
    with a non-loopback `--host`; `op serve` must sit behind the reverse proxy (spec 08 §Deploy: uvicorn has
    no header timeout of its own).
  - The OpenAPI document is served at `/api/v1/openapi.json`. Swagger UI (`/api/v1/docs`) loads its script
    and styles from a CDN, so it is off unless `ApiConfig.serve_docs` is set: `op serve` sets it for a
    loopback `--host` only (a local instance), `--docs`/`--no-docs` override. A production instance serves no
    third-party script.
  - Pinned opens: `IndexState.pinned` resolves the name (a stat or two) before it takes the one open slot, so
    a version this instance doesn't hold is `absent` at once, never queued behind another version's re-hash.
    A failed load's `index_load_failed` line names the configured `index_name` (`current` or a version); a
    directory named like a version whose manifest can't be read is left out of `/meta` with a DEBUG
    `index_manifest_unreadable` line (`index_version`, `error`, `reason`: the errno name). A `request_failed`
    line has `cause` only when there is one (never `cause: null`).
- As built (task-040, `api/openapi.py`): the served document is committed as
  `backend/tests/contract/openapi.json` (`op openapi`: sorted keys, two-space indent, no server URL, no
  timestamp, built from `create_app` without loading an index), and `frontend/src/api/schema.ts` is
  generated from that file by `openapi-typescript` (pinned in `frontend/package.json`, `npm run gen:api`).
  `make openapi` regenerates both; `test_openapi_snapshot.py` fails when the live document differs from the
  snapshot, and CI's `test` job runs `make openapi` and fails on any diff. To keep the document valid and
  stable: an operationId is the handler's name, `verb_noun` (§Conventions; FastAPI's default appends the
  first method of the route's set, which follows `PYTHONHASHSEED`), unique across routers (tested); every
  route documents the error envelope as its `default` response (replacing FastAPI's `HTTPValidationError`
  422, which this app never sends), plus its 405 with `Allow` and its 429 with `Retry-After`; the HEAD of a
  GET+HEAD route (`/healthz`) is left out of the document, because FastAPI would give it the GET's
  operationId; and every open enum's schema is marked open (`mark_open_enums`).
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
    first, in O(1), and returns `errors=[PARSE_TOO_LONG]` without lexing; and a query whose canonical form
    is over the cap, which `parse` refuses with `PARSE_TOO_LONG` after canonicalising (decision-008). Only a malformed body is refused
    (422 `API_BAD_PARAM`). The 422-on-parse-error rule applies to endpoints that run the query (`/search`,
    `/export`, `POST /records`). **Correction to TASK-035 AC #2** (the task is completed, so the CLI can't
    edit it): the AC says "Parse errors are 422", but that holds only for endpoints that run the query.
    `/parse` reports them in a 200 (task-035 review, Should 5).
  - `POST /parse`'s `filters` (TASK-078, decision-011) is `query.clauses.filter_clauses(q, result)`, the one
    call the route adds: `{venue, year, track, status}`, each `{field, negated, span, toggleable, reason}`
    plus `values` (venue, track, status) or `ranges` (year), every key always sent (a null included); null
    exactly when `errors` is non-empty. The rules (the flattened canonical tree, the zero-width span of a
    default or unrestricted field, the reasons, the widest-edit cap check) are 02 §Filter clauses. Goldens:
    `frontend/src/lib/filter-clause-golden.json` (`tests/contract/test_parse_filters.py`).
  - `GET /papers/{id}` answers `{index_version, tokenizer_version, query_version, paper}`, where `paper` is
    the spec 01 `PaperRecord` (provenance and `content_hash` included). The served index decides whether the
    id exists. Otherwise the answer is 404 `API_PAPER_NOT_FOUND`, whose message never repeats the id. An id
    that isn't shaped `op:<venue>:<year>:<native>` is 422 `API_BAD_PARAM` (the path's `pattern`, as a
    malformed record id is; M3a review), without the index being asked. The index
    stores only the display record, so the full one comes from the snapshot it was built from:
    `<data_dir>/snapshots/<the index manifest's snapshot>`, which must hash to the manifest's
    `snapshot_hash`. That snapshot is verified **when the index is loaded**
    (`api/state.py::snapshot_records`, next to opening the engine and before the swap).
    `ingest.snapshot.RecordFile` makes one verifying pass and holds each record's byte range; it is part of
    the served bundle, so a request reads the records of the engine it took. The index manifest → snapshot
    directory rule (a plain directory name, whose manifest names the index's `snapshot_hash`) is one helper,
    `ingest.snapshot.indexed_snapshot`, which a search record's facts use too. **A deployment must ship that snapshot beside the index.** If it is
    missing or different, the load fails (`index_load_failed`, ERROR). At startup that means 503
    `API_INDEX_NOT_LOADED`; on SIGHUP the old index keeps serving. It is never a record without its
    provenance, and never a re-hash per request. Only a snapshot file that becomes unreadable after the load
    is a per-request 500 `API_INTERNAL`.
  - **Paper-page highlights (task-087).** `GET /papers/{id}` takes an optional `q` and `mode` (`native` |
    `scholar`, default `native`) and always sends two more fields, `matched` and `highlights` (additive
    under v1: a new optional parameter whose absence keeps the old answer, two new always-sent nullable
    fields). Without `q` both are null. With `q`:
    - `matched` is whether the **effective** query (the default filters included) matches the paper on the
      served index: whether `/search` counts it in `total`. So a workshop paper whose text matches `trust` is
      `matched: false` for `trust` (the default `track:main` removes it) and `true` for `trust track:workshop`.
    - `highlights` is `{title, abstract}` in the `/search` hit's shape and span units (code points over the
      raw stored text). For a matched paper they are **the spans `/search` gives that paper as a hit** for the
      same `q`, `mode` and index: `search.highlight` builds the same `Highlighter` over the same display record
      and the same wildcard expansions (`Highlighter.match`, which `/search`'s per-hit call wraps).
      `tests/contract/test_paper_highlights.py` compares them hit by hit over every Trust-Evals protocol
      string (Scholar mode) and a set of native queries on the 5k fixture, plus the astral-plane golden.
    - A query that doesn't match the paper is **not an error**: `matched: false`, both highlight lists empty.
      A query that matches only through filters (`venue:ICLR`) is `matched: true` with nothing lit.
    - `q` is **admitted exactly as `/search` admits it**, so a `q` this route runs is one `/search` runs:
      strict parameters (unknown or repeated is 422 `API_BAD_PARAM`; so is `mode=scholar` without `q`), the
      2,000-code-point cap (`PARSE_TOO_LONG` before parsing), the parse (422 with its diagnostics), an
      over-cap wildcard (its located 422), the verified-clause cap and per-clause charge (`deps.searchable`),
      and the candidate ceiling (`deps.check_candidates`, 422 `API_QUERY_TOO_COSTLY`). The query is admitted
      before the id is looked up, so an unknown paper with a verified `q` is charged and then 404. The route
      declares the 503 `API_BUSY` as every query route does, but today never sends it: the paper's own text
      is evaluated (the highlighter's verdict, which a unit test holds to ReferenceEngine's on every
      fixture record), so no collection runs and nothing is position-verified, and no verification slot or
      deadline applies. The per-verified-clause charge is still taken, deliberately: nothing is verified
      today, but the charge is `/search`'s admission for the same `q`, so this route can't be used to
      price a query below `/search`, and the charge stays right if highlighting ever runs a collection. The
      paper's display record is read once, for the existence check, and highlighted as read. The access line
      carries the parse fields (`canonical_hash`, token count, codes, `verified_clauses`), never `q`.
    - Chosen over carrying the hit's spans from the `/search` response the reader came from (the other option
      TASK-087 named): that way a direct or shared link to a paper page would show no highlights, the page
      would depend on client state the URL doesn't hold (guarantee 3 keeps `q` as the only result-set state),
      and a reload would lose them. The paper page links as `/paper/<id>?q=…&mode=…` instead (spec 05).
  - `GET /meta` answers the three versions, plus `index_versions` (every index this instance can serve,
    sorted, with the served one included; which are left out: §Implementation notes, pinned indexes), `text_fields` (`title`, `abstract`), `filter_fields` (`venue`,
    `year`, `track`, `status`), and `values` (`venue`, `track` and `status`: the vocabularies the parser checks
    filter values against, so autocomplete never offers a value it refuses), and `limits` (task-089):
    `max_query_length` (the parser's `MAX_QUERY_LENGTH`, 2,000 code points; not configurable),
    `max_query_depth` (the parser's `MAX_DEPTH`, 64 nested groups and `NOT`s, deeper is `PARSE_TOO_DEEP`;
    not configurable; additive),
    `max_verified_clauses` and `max_verification_candidates` (this instance's `op serve` values, defaults 16
    and 300,000), the limits behind `PARSE_TOO_LONG`, `API_TOO_MANY_VERIFIED_CLAUSES` and
    `API_QUERY_TOO_COSTLY`, so a client need not hard-code them. The frontend reducer takes both caps from it
    (spec 05 §URL is state).
  - Every route that reports `index_version` needs a loaded engine, `/parse` and `/meta` included (503
    `API_INDEX_NOT_LOADED` before the first load).
- As built (task-038, `api/coverage.py`, `coverage.py`): `GET /coverage` answers the three versions plus
  `snapshot` (`name`, `snapshot_hash`, `crawl_date` (the last fetch's UTC date), `crawl_dates` (a search
  record's shape, `{"*": {from, to}}`, plus a key per source that carries its own window; `coverage.crawl_dates`),
  `built_at`, `sources`), `totals` (`records`, `abstract_missing`, `unknown_track`, `unknown_status`) and
  `venue_years`: one entry per venue-year, ordered by venue name then year, with the same four counts and
  `cells`, a `{track, status, count}` per non-empty cell in vocabulary order (`vocab.py`; `unknown` last).
  - The numbers are the manifest of the snapshot the served index was built from (`counts`,
    `abstract_missing`, `unknown_track`, `record_count`: counted from the records once, at snapshot build),
    reshaped by `coverage.breakdown`, which never recounts. `unknown` is never folded: it is its own cell,
    and every venue-year carries `unknown_track` and `unknown_status`, 0 included. Missing abstracts are per
    venue-year, the manifest's granularity (the M4 abstract threshold is per venue-year too).
  - Computed **when the index is loaded** (`IndexState._load` → `api/coverage.py::compute`, right after the
    snapshot is verified and before the swap; task-038 review). It is part of the served bundle, beside the
    snapshot's records (`IndexState.served`). The load's one pass over the records
    also counts them per (venue, year, track, status) and counts missing abstracts per venue-year. These
    counts must equal the manifest's cells and `abstract_missing`, and the records must number the index's
    documents. Any of these failures makes the load fail, logged as `index_load_failed` (ERROR) with a
    `reason` constant and never a path: a manifest whose maps disagree, a track or status outside the
    vocabulary, a manifest that disagrees with the records, a missing or different snapshot, or a record
    count that differs from the index's document count. The reasons are `snapshot_missing`,
    `snapshot_unreadable`, `snapshot_hash_mismatch`, `index_manifest_invalid`, `manifest_invalid`,
    `counts_mismatch`, `abstract_missing_mismatch` and `doc_count_mismatch`. At startup the failure is 503 `API_INDEX_NOT_LOADED`; on SIGHUP the old index and
    its coverage keep serving. Coverage is never partial and never recomputed per request. One
    `coverage_computed` INFO line is written per load.
  - Not yet: which statuses a venue-year's sources *can* contain (spec 07 §C "statuses indexed") and crawl
    dates per source; neither is in the manifest (task-082).
- As built (task-036, `api/export.py`; review fixes 2026-09-27):
  - `GET /export` takes either `q` (with `mode` and an optional `index_version`) or `record_id` alone;
    `format` (`ris` | `csv` | `bibtex` | `jsonl`) is always required. With `record_id`, the export is the
    record's stored ids on the record's index_version (the cited set, never a re-run; `stored_documents`
    reads them in id order a chunk at a time, and provenance carries the record's `canonical_hash`), after
    the pin (409 `API_INDEX_VERSION_UNAVAILABLE`) and the replay (`api.records.refuse_mismatch`, 409
    `API_RECORD_MISMATCH`); passing `q`, `index_version` or `mode=scholar` as well is 422 `API_BAD_PARAM`, as
    is neither `q` nor `record_id`. `mode` defaults to `native`, and `mode=native` with `record_id` is
    accepted (a record replays its canonical string natively; a generated client may send every declared
    default). The body is the bytes `op export` writes for the same query,
    index and UTC date: both run `export.header` and `export.entries` over `TantivyEngine.documents`, and a
    contract test compares them for every format. Records are sent in chunks of whole records, each at most
    `CHUNK` (64 Ki characters) plus one record (a contract test reads the ASGI messages).
  - Everything that can refuse happens before the first byte, in the one envelope. First the parameters
    (422 `API_BAD_PARAM`: an unknown or repeated one, `record_id` with `q`, `index_version` or
    `mode=scholar`, or neither). Then, **with `q`**: the length cap and the parse (422 with diagnostics), a position-verified
    query's extra weight (429), the pin (409 `API_INDEX_VERSION_UNAVAILABLE`), every wildcard's expansion
    (422 `WILDCARD_TOO_MANY_EXPANSIONS`, each over-cap wildcard located in `q` by `search.expanded`, as
    `/search` does), then the one collection of the match set that gives `X-Total`. **With `record_id`**:
    the record's lookup (404 `API_RECORD_NOT_FOUND`), the pin of its own index (409
    `API_INDEX_VERSION_UNAVAILABLE`), its replay (409 `API_RECORD_MISMATCH` on a `mismatch`), and the stored
    ids hashing to its `ids_hash` and numbering its `total` (409 `API_RECORD_MISMATCH`); `X-Total` is that list's length, the record's `total`. Then a sync generator
    streams from the engine the request took, so an export started before a hot swap finishes on its index
    (contract test). A failure after the first byte is logged by the last catch and marks the access line
    `aborted: true`. A stream whose record count is below or above `X-Total` fails the same way after its
    last record (`export.check_count`, the check `op export` ends with too); it never ends as if complete. A client that hangs up mid-stream is `client_disconnected:
    true` on the access line (tested through uvicorn).
  - Headers: `X-Total`, `X-Index-Version`, `X-Tokenizer-Version`, `X-Query-Version` (all exposed to CORS),
    `Content-Disposition: attachment; filename="openproceedings-<index_version>-<first 12 of
    canonical_hash>.<ext>"` (`ris`, `csv`, `bib`, `jsonl`), and `Content-Type`
    `application/x-research-info-systems`, `text/csv`, `application/x-bibtex` or `application/x-ndjson`,
    each with `; charset=utf-8`. The access line carries `canonical_hash`, `total` and the `index_version`
    exported.
  - `index_version` must look like one (`[0-9a-f][0-9a-f-]{0,63}`; `current` is not a version), else 422
    `API_BAD_PARAM`. The served version is the served engine; any other comes from `IndexState.pinned`
    (§Implementation notes, pinned indexes). Anything but `ok` is 409 `API_INDEX_VERSION_UNAVAILABLE`:
    absent, unloadable by this code, or tampered with (a copied or changed directory). **Chosen: 409, not
    500**, for a pinned index that fails verification: from the client's side that version is not
    available here; the ERROR line tells the operator why.
- Pinned indexes (task-036/037 review; `api/state.py`): `IndexState.pinned(version) -> Pinned(engine,
  reason)` is the one loader, for exports and for a record's replay and diff (`api/records.py` passes
  `lambda v: state.pinned(v).engine`). `reason` is `ok`, `absent` (not a version directory here, or a
  name that resolves to another directory, such as an alias symlink or `current`; DEBUG, since a client can
  name any version), `unloadable` (`EngineInternalError`: another tokenizer, schema or Tantivy version; or a
  `ValueError`, `OSError` or `RuntimeError` from Tantivy or the filesystem; one WARNING) or `tampered`
  (`IndexBuildError` from verification, or an engine that reports another version; one ERROR). Each refusal
  is one `pinned_index_unavailable` line with `index_version`, `reason`, the error type and `cause_reason`
  (the load failure's constants above: `not_found`, `alias`, `files_mismatch`, `tokenizer_version_mismatch`,
  `index_version_mismatch`, an errno name), then remembered for `ApiConfig.pinned_refusal_seconds` (default
  300) or until the next reload (SIGHUP), so a broken or stale index is not re-verified per request.
  `absent`, the one refusal a client causes at will, is remembered in a map of its own (at most 256), so
  naming many absent versions never evicts a remembered `unloadable` or `tampered` one (at most 256 more).
  Engines are held in an LRU of `ApiConfig.pinned_indexes` (default 4; size it to the versions the instance
  holds); an open logs `pinned_index_opened` (INFO, with `ms`). A cache hit takes only the short map lock,
  never a lock an open holds; **at most one pinned index opens at a time** (each re-hashes a whole index;
  security review), and one version asked for at once is opened once. An engine dropped from the LRU stays alive while a stream still
  holds it, so memory is bounded by the LRU plus the exports in flight (each costs `export_weight` of the
  rate limit). `GET /meta`'s `index_versions` leaves out a version this code can't serve (its manifest's
  tokenizer, schema or Tantivy version, read without re-hashing) and one currently refused. If listing
  `<data_dir>/indexes/` fails, `/meta` lists the served version alone and logs `index_list_failed` (WARNING,
  with the errno name) once, and `index_list_recovered` (INFO) once it lists again: one line per change of
  state, not per request.

## Testing

- Contract tests for each endpoint using an in-process `TestClient` over the 5k-record fixture index.
- Export round-trips: parse the RIS/CSV/BibTeX output back and get the same IDs and fields.
- Search-record replay tests for the reproduced, drifted and mismatch paths. The mismatch path uses a
  fixture record inserted with a wrong `ids_hash` or `excluded` (the store stays append-only), and asserts a `200` with
  `status: "mismatch"` plus one `API_REPLAY_MISMATCH` ERROR log line.
- An export with `record_id` of a `mismatch` record returns 409 `API_RECORD_MISMATCH` and streams nothing; of a record whose index is gone, 409 `API_INDEX_VERSION_UNAVAILABLE`; of a record whose query version drifted, exactly its stored ids.
- An OpenAPI snapshot test, so any contract change shows up in the PR diff.
