---
name: api-contract
description: The openproceedings HTTP contract — the spec 04 endpoint table, the SearchResponse shape, disjunctive facets, the excluded block, what counts as a breaking change under /api/v1, and the OpenAPI snapshot plus frontend/src/api/schema.ts codegen with its CI freshness check. Use when adding or changing an endpoint, a pydantic response model, a query parameter or an export format, and when reviewing an OpenAPI diff.
---

# API contract (spec 04)

## Endpoints (`/api/v1`)
| Method | Path | In → out |
|---|---|---|
| POST | `/parse` | `{q, mode}` → 02's `ParseResult` (AST, canonical, warnings, translations). Debounced, called as the user types. A query with errors is a 200 whose `errors` say why (only `PARSE_TOO_LONG` and a malformed body are 422s). |
| GET | `/search` | `q, mode, sort, offset, limit(≤200)` → `SearchResponse` |
| GET | `/papers/{id}` | full record with provenance |
| GET | `/export` | `q, mode, format=ris\|csv\|bibtex\|jsonl`, optional `record_id` **or** `index_version` → a stream of the **entire** matched set, ordered by `id`, served from the pinned index; a `mismatch` record's `record_id` → 409 `API_RECORD_MISMATCH` |
| POST | `/records` | freeze a search as an immutable search record → `{record_id, url}` (`.claude/skills/search-records/SKILL.md`) |
| GET | `/records/{id}` | stored record + replay check (HTTP 200, status `reproduced` / `drifted` / `mismatch`) |
| GET | `/records/{id}/diff` | for a `drifted` record: added and removed ids (with titles), and which `index_version` inputs changed |
| GET | `/coverage` | counts per venue × year × track × status, abstract-missing counts, snapshot date |
| GET | `/meta` | current and available `index_version`s, field and track vocabularies |
| GET | `/healthz` | liveness, index loaded |
| GET | `/near-misses` | M5 only, a separate resource (`.claude/skills/specter2-embeddings/SKILL.md`) |

## `SearchResponse`
`query {input, canonical, canonical_hash, identification_query, warnings[], translations[],
expansions{pattern: [terms]}}`,
`index_version`, `tokenizer_version`, `query_version`, `total`, `excluded`, `facets`, `hits[]`. Each hit
has `id, title, abstract, authors, venue, year, track, presentation, score, highlights{field:
[[start,end]]}, urls`.

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
  its count is `total + excluded.total`.
- **`expansions`** always lists every wildcard's terms (guarantee 6). It is never omitted when non-empty.
- **Highlights** are spans computed from the AST, never from a snippet generator. Built: `engine/highlight.py::highlights(ast,
  record, engine.expansions(ast))`, which returns both fields, each a sorted list (spec 03 §Highlights). Call it only on the
  engine's hits: a record the query doesn't match raises `EngineInternalError` (a 500). Spans that touch
  (an operator token and its neighbour, `5×3`) stay separate; only overlaps merge.

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
say exactly which set was exported. Exports are ordered by `id` and are never paginated or truncated. An
export started during an index hot-swap finishes on the index it began on. The field mapping of each
format is pinned in `.claude/skills/ris-format/SKILL.md` and `.claude/skills/bibtex-format/SKILL.md`. CSV
is one row per paper: the 01 schema columns plus `index_version` and `canonical_hash` provenance columns,
UTF-8 **with BOM**.

## Versioning rules
Allowed within `v1` (additive): a new endpoint, a new **optional** response field, a new enum value in
a field the clients treat as open, a new optional parameter with the old behaviour as its default.

**Breaking**, which needs `/api/v2` or a decision record (`.claude/skills/decision-records/SKILL.md`):
removing or renaming a field, changing a field's type or nullability, making an optional field required,
tightening validation (for example a lower `limit` cap), changing a default (`sort`, `mode`, default
filters), changing what a field *means* (`total` counting something else), changing error codes, and
changing an export's field mapping or byte format. External scripts and Covidence imports depend on
those formats.

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
   function name** (`search`, `parse_query`, `paper`, `meta`, `healthz`), so it must be unique across
   routers; every route documents the error envelope (`ErrorEnvelope`) as its **`default` response**,
   which replaces FastAPI's `HTTPValidationError` 422 (never sent here); and the HEAD of a GET+HEAD route
   is dropped from the document (FastAPI would repeat the GET's operationId).
5. Reviewing: read the snapshot diff first. It is the contract as shipped; classify each change with the
   versioning rules above. A model change with no snapshot diff means the change is not in the contract.
