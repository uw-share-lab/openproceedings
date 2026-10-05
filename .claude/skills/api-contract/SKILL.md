---
name: api-contract
description: The openproceedings HTTP contract — the spec 04 endpoint table, the SearchResponse shape, disjunctive facets, the excluded block, what counts as a breaking change under /api/v1, and the OpenAPI snapshot plus frontend/src/api/schema.ts codegen with its CI freshness check. Use when adding or changing an endpoint, a pydantic response model, a query parameter or an export format, and when reviewing an OpenAPI diff.
---

# API contract (spec 04)

## Endpoints (`/api/v1`)
| Method | Path | In → out |
|---|---|---|
| POST | `/parse` | `{q, mode}` → 02's `ParseResult` (AST, canonical, warnings, translations) plus `filters`, each filter field's top-level clause for facet clicks (02 §Filter clauses, decision-011; `query/clauses.py`). Debounced, called as the user types. Any well-formed body is a 200 whose `errors` say why the query doesn't parse (`PARSE_TOO_LONG` included); only a malformed body is a 422 `API_BAD_PARAM`. |
| GET | `/search` | `q, mode, sort, offset, limit(≤200)` → `SearchResponse` |
| GET | `/papers/{id}` | full record with provenance and its derived `venue_name` (the export venue string, TASK-112); optional `q` (+ `mode`) → `matched` and `highlights`, equal to `/search`'s for that paper (null without `q`; `matched: false` + empty lists when the query doesn't match it; `q` admitted exactly as `/search` admits it; task-087) |
| GET | `/export` | `format=ris\|csv\|bibtex\|jsonl` plus either `q` (with `mode` and optional `index_version`) or `record_id` (with at most `mode=native`, the declared default some clients always send; `scholar` is 422 "with record_id, mode may only be native") → a stream of the **entire** matched set, ordered by `id`, served from the pinned index; `record_id` → exactly the record's stored ids from its index (409 `API_INDEX_VERSION_UNAVAILABLE` if gone, 409 `API_RECORD_MISMATCH` on a `mismatch`) |
| POST | `/records` | freeze a search as an immutable search record → 201 `{record_id, page}` plus the three versions, + `Location: /api/v1/records/<id>` (`.claude/skills/search-records/SKILL.md`); optional `index_version` pin: 409 `API_INDEX_VERSION_UNAVAILABLE` unless it is the served index (TASK-091) |
| GET | `/records/{id}` | stored record + replay check (HTTP 200, status `reproduced` / `drifted` / `mismatch`; a replay over this instance's verification limits is withheld: 200, `refused`, never a 422); `replay=false`: the stored record, `replay: null`, no run, one token without `include=ids` (full weight with ids; TASK-091, decision-014) |
| GET | `/records/{id}/diff` | for a record of any status: added and removed ids (with titles, paged), and which `index_version` inputs changed |
| GET | `/coverage` | counts per venue × year × track × status, abstract-missing counts, snapshot date; `snapshot.crawl_dates_kind` and `identification_citable`, a record's derivation (TASK-091) |
| GET | `/meta` | current and servable `index_version`s, field names, venue, track and status vocabularies, and `limits` (`max_query_length`, the parser's; `max_verified_clauses` and `max_verification_candidates`, the served config's; task-089) |
| GET | `/healthz` | liveness, index loaded |
| GET | `/near-misses` | M5 only (deferred to phase 2, decision-017; not in v1), a separate resource (`.claude/skills/specter2-embeddings/SKILL.md`) |

## `SearchResponse`
`query {input, canonical, canonical_hash, identification_query, warnings[], translations[],
expansions{pattern: [terms]}}`,
`index_version`, `tokenizer_version`, `query_version`, `total`, `excluded`, `identified_total`,
`unclassified_total`, `facets`, `groups {counts[{span, total}], groups_total, limit, not_counted}` (TASK-176:
each concept group's count alone, the query with every other group removed; spec 04 §SearchResponse), `hits[]`. Each hit
has `id, title, abstract, authors, venue, year, track, status, presentation, score, highlights{field:
[[start,end]]}, urls, abstract_source{source, origin, url}|null` (the claim the abstract came from, the site that
published it, for `ris` read from the claim's evidence, and the paper's page there; TASK-134, decision-018;
computed per record at snapshot load, `RecordFile.attributions`).

**Every response** (not only `/search`) carries `index_version`, `tokenizer_version` and `query_version`
(spec 04 §Conventions; `.claude/skills/index-versioning/SKILL.md`).

- **`total`** is the size of the lexical matched set. It never depends on `sort`, `offset`, `limit`
  or the semantic layer (guarantee 5).
- **`excluded`** is 03's exclusion accounting for what the **default filters** removed, with a pinned
  shape: `{"total": N, "track": {…, "unknown": n}, "status": {…, "unknown": n}}`, for example
  `{"total": 304, "track": {"workshop": 212, "competition": 4, "unknown": 0}, "status": {"rejected": 88,
  "unknown": 0}}`. The buckets sum to `total`, and both `unknown` keys are always present (even when 0) so
  unclassified records are itemised. It is always present, even when empty, because it is PRISMA's
  "records removed before screening".
- **`identification_query`** is the canonical string minus the default conjuncts (02 §Default filters);
  its count is `total + excluded.total`, sent as **`identified_total`**; **`unclassified_total`** is the two
  `unknown` buckets (TASK-090). Both are `engine/exclusions.py`'s helpers, which `op search` prints too: a
  client never adds counts. A search record and its replay carry both.
- **`expansions`** always lists every wildcard's terms (guarantee 6). It is never omitted when non-empty.
- **Highlights** are spans computed from the AST, never from a snippet generator. Built: `engine/highlight.py::highlights(ast,
  record, engine.expansions(ast))`, which returns both fields, each a sorted list (spec 03 §Highlights). Call it only on the
  engine's hits: a record the query doesn't match raises `EngineInternalError` (a 500). For one record that
  need not be a hit (`GET /papers/{id}?q=`), `search.highlight` calls `Highlighter.match`, which returns
  None instead. Spans that touch
  (an operator token and its neighbour, `5×3`) stay separate; only overlaps merge. For a page, build one
  `Highlighter(ast, expansions)` and call it on each hit (`search.run` does; task-073): the query's work is
  done once, not per hit.

## v1 shape rules (spec 04 §Conventions; frozen at the first release, M3a gate)
Checked by `backend/tests/contract/test_contract_v1.py`; keep to them in every new model and route.
- **Every field a response sends is required** in the schema (`json_schema_serialization_defaults_required`
  on every response model, the shared ones in `ingest/record.py`, `diagnostics.py`, `query/ast.py` and
  `records.py` included). The one optional key is `ErrorBody.diagnostics`: absent or a non-empty array,
  never null (`SkipJsonSchema[None]`). A shape a hit shares with its paper is the same schema.
- **Counts are `*_total`** (`added_total`, `removed_total`); a bare plural is a list.
- **One timestamp form**: UTC RFC 3339 with `Z`, typed `format: date-time`, via `timestamps.Timestamp` (or a
  UTC `datetime`); a date is `format: date`. Never pass a manifest's `…+00:00` text through.
- **One crawl-window shape**: `crawl_dates: {"*": CrawlWindow, <source>: CrawlWindow}` everywhere.
- **Parameters are exact**: every route refuses an unknown or repeated query parameter (the app-wide
  `deps.strict_query`), a trailing slash is a 404 (`redirect_slashes=False`), and a path id carries its
  `pattern` (a malformed id is 422 `API_BAD_PARAM`, an unknown one 404). Describe every parameter.
- **Enums are open or closed** (decision-009): `OPEN_ENUMS` / `CLOSED_ENUMS` in `api/openapi.py`; the test
  fails on an enum in neither. Open ones get "Open set: … handle a value you don't know." in the schema.
- **`ErrorBody.code` is `ErrorCode`**: the registry's codes with an HTTP status, derived, never hand-listed.
- **Status-specific headers are declared** (`response_header`): an export's 200 (`X-Total`, the three
  versions, `Content-Disposition`, `X-Abstract-Source`: closed enum `attributed`/`unavailable`, decision-021), every 405 (`Allow`) and 429 (`Retry-After`), the 503 `API_BUSY` of every
  route that runs a query (`Retry-After`, `openapi.BUSY`: `/search`, `/export`, `/papers/{id}`, the record routes), a 201
  (`Location`); CORS exposes each (`app.EXPOSED_HEADERS`).
- `info.version` is the API version (`v1`), not the package's.

## Span units (spec 04 §Conventions)
Every span is a half-open `[start, end)` range of **Unicode code points** over the **raw source string**:
the stored title or abstract for `highlights`, the query input `q` for diagnostic `span`s. Never over
normalized text: NFKC can change lengths, so `normalize()` returns an offset map that highlight computation
uses. The frontend converts to UTF-16 exactly once, in one helper
(`.claude/skills/nextjs-conventions/SKILL.md`). A golden contract test covers a title containing an
astral-plane character.

## Facets are disjunctive
For each facet field F, count over the set matched by the query with every filter applied **except F's
own**. The track facet therefore still shows the workshop count while workshops are filtered out. A facet
click rewrites `q` in the UI (guarantee 3), so no facet state is held server-side and none is passed
as a parameter. Remove F's filter only where it is a top-level conjunct; a filter nested under `OR`
stays applied (decision-001, matching the default-filter rule).

## Errors
Statuses and codes are exactly spec 04 §Error handling (the only table; the registry is in
`.claude/skills/error-diagnostics/SKILL.md`). Changing a released status/code pair is a breaking change.

## Exports are contract too
The response headers `X-Total` (equal to the `/search` `total` for the same `q`) and `X-Index-Version`
say exactly which set was exported; `X-Tokenizer-Version` and `X-Query-Version` carry the other two
versions a JSON response has in its body. Exports are ordered by `id` and are never paginated or truncated. An
export started during an index hot-swap finishes on the index it began on. The field mapping of each
format is pinned in `.claude/skills/ris-format/SKILL.md` and `.claude/skills/bibtex-format/SKILL.md`. CSV
is one row per paper: the 01 schema columns plus the provenance columns (`index_version`, `canonical_hash`,
`exported_at`, `record_id`, `searched_at`) and the abstract-source columns (`abstract_source`,
`abstract_origin`, `abstract_url`, `abstract_withheld`; TASK-138), UTF-8 **with BOM**. Every format names each
abstract's source from the exported index's snapshot (`RecordFile.attributions`; a pinned index's through
`IndexState.pinned_records`). When a pinned index's snapshot can't be verified the export is still a 200 with
every abstract withheld, `X-Abstract-Source: unavailable` and a marker in each record (decision-021). A record a
takedown withholds (TASK-136, decision-022) is exported without its abstract on every index version, marked the
same way; CSV appends `abstract_withheld_reason` (`takedown`, `source_unavailable` or empty) after
`abstract_withheld`, and JSONL has the same key; the response counts those records in `X-Abstracts-Withheld`
(an integer header, declared, exposed to CORS, on the access line as `abstracts_withheld`). `/search` hits and `/papers/{id}` carry `abstract_withheld`
(a boolean, additive) and `/coverage` an `abstract_withheld` count beside `abstract_missing`. `/search` hits and
`/papers/{id}` also carry `twins` (TASK-162, additive; decision-029): the sorted ids of the record's twins (its
`twin` claims, `RecordFile.twins`), usually `[]`; every export names them (RIS `N1  - See also: …`, BibTeX
`openproceedings_twins`, a last CSV column `twins`, a JSONL `twins` list only on a record with one), and a
record without one exports byte for byte as before except CSV's one more empty cell.

## Versioning rules
Allowed within `v1` (additive): a new endpoint, a new response field (always sent, so required in the
schema; an old client ignores it: response schemas carry no `additionalProperties: false`,
`openapi.open_response_objects`), a new value in an enum listed **open** (`OPEN_ENUMS`, decision-009), a new
optional parameter with the old behaviour as its default. **In an export format** (decision-021, TASK-138): a
new RIS line of a tag that already repeats, placed so every documented position still holds (the provenance
`N1` stays last); a new BibTeX field; a new CSV column appended after the last; a new JSONL key. Each only when
no existing line, field or column changes its value or its position among its peers, and the Covidence fixture
either keeps its bytes or is re-imported. Precedent: the M3a gate appended `record_id` and `searched_at`.
Not protected (decision-021 says so): CSV readers with a fixed column list (pandas `names=`, readr fixed
`col_types`), JSONL readers with a strict schema (`additionalProperties: false`), RIS readers that take the
first `N1` as the provenance line.

One recorded exception: `RecordResponse.replay` is nullable, null only for the opt-in `replay=false`
(decision-014). `backend/tests/contract/test_openapi_additive.py` diffs the snapshot against the released one
on `origin/dev` by these rules (`ALLOWED` lists that exception); run it before any contract change lands.
Locally it skips when `origin/dev` is missing. CI's `test` job compares against the commit the change builds
on (the PR's base commit, or the pushed branch's previous tip), fetched by SHA into `OPENAPI_BASELINE_REF`, with
`OPENAPI_BASELINE_REQUIRED=1`: an unreadable baseline fails there. A baseline commit with no snapshot yet (`main`
before its first promotion) skips: there is no released contract to compare against (TASK-129).

**Breaking**, which needs `/api/v2` or a decision record (`.claude/skills/decision-records/SKILL.md`):
removing or renaming a field, changing a field's type or nullability, making an optional field required,
tightening validation (for example a lower `limit` cap), changing a default (`sort`, `mode`, default
filters), changing what a field *means* (`total` counting something else), changing error codes, a new
value in a **closed** enum (`mode`, `sort`, `format`, the replay `status`, …) or moving an enum from open to
closed, and
changing an export's existing field mapping or byte format (a value, a field's content such as BibTeX `note`, a
column's position, a line's documented place), or removing anything from it (decision-021). External scripts and Covidence imports depend on those formats.

## Codegen and freshness (as built, TASK-040)
**One command: `make openapi`.** Run it after any change to a route, a parameter or a response model, and
commit both files it writes. Never edit either by hand; never resolve a merge conflict in them by hand
(merge, then rerun `make openapi`).
1. `op openapi [--out FILE]` (`backend/src/openproceedings/api/openapi.py`) renders the app's document
   from `create_app` without running its lifespan (no index, no data dir): sorted keys, two-space indent,
   raw UTF-8, trailing newline, no server URL, no timestamp. `make openapi` writes it to
   **`backend/tests/contract/openapi.json`**, the committed snapshot.
2. **`frontend/src/api/schema.ts`** is generated from that snapshot by `openapi-typescript` (7.13.0,
   pinned exactly in `frontend/package.json`; `npm run gen:api --workspace frontend`, which `make openapi`
   runs). Excluded from prettier and eslint (`frontend/.prettierignore`, `eslint.config.mjs`); `tsc`
   still checks it. `src/api/client.ts` is the one typed client over it (`openapi-fetch`).
3. `backend/tests/contract/test_openapi_snapshot.py` fails when the live document differs from the
   snapshot (and says to run `make openapi`), when an operationId repeats, and when `op openapi` renders
   differently under another `PYTHONHASHSEED`. CI's `test` job runs `make openapi` unconditionally and then
   `git diff --exit-code` on both files.
4. Validity rules the app enforces (`api/app.py`, `api/openapi.py`): an **operationId is the handler's
   function name, `verb_noun`**: `search`, `parse_query`, `export`, `get_paper`, `get_coverage`, `get_meta`,
   `get_healthz`, `create_record`, `get_record`, `get_record_diff` (a test pins the list), so it must be
   unique across routers; every route documents the error envelope (`ErrorEnvelope`) as its **`default`
   response**, which replaces FastAPI's `HTTPValidationError` 422 (never sent here), plus its 405 (`Allow`)
   and 429 (`Retry-After`; not `/healthz`, never limited), and each route that runs a query its 503
   `API_BUSY` (`Retry-After`, `openapi.BUSY`); the HEAD of a GET+HEAD route is dropped from the
   document (FastAPI would repeat the GET's operationId); and open enums are marked (`mark_open_enums`).
5. Reviewing: read the snapshot diff first. It is the contract as shipped; classify each change with the
   versioning rules above. A model change with no snapshot diff means the change is not in the contract.
