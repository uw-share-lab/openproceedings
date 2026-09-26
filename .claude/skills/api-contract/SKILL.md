---
name: api-contract
description: The openproceedings HTTP contract — the spec 04 endpoint table, the SearchResponse shape, disjunctive facets, the excluded block, what counts as a breaking change under /api/v1, and the OpenAPI snapshot plus frontend/src/api/schema.ts codegen with its CI freshness check. Use when adding or changing an endpoint, a pydantic response model, a query parameter or an export format, and when reviewing an OpenAPI diff.
---

# API contract (spec 04)

## Endpoints (`/api/v1`)
| Method | Path | In → out |
|---|---|---|
| POST | `/parse` | `{q, mode}` → 02's `ParseResult` (AST, canonical, warnings, translations). Debounced, called as the user types. |
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
- **Highlights** are spans computed from the AST, never from a snippet generator.

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
as a parameter. Remove F's filter only where it is a top-level conjunct. How a filter nested under `OR`
is treated is still open: task-001 AC #6 owns the decision. Until it is decided, raise it with
`query-semantics-reviewer` rather than guessing.

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

## Codegen and freshness
1. The OpenAPI document is generated from the app (`app.openapi()`) and committed as a snapshot under
   `backend/tests/contract/`. The exact filename is pinned at implementation time. The contract test
   diffs the live schema against it, so every contract change shows up in the PR diff.
2. `frontend/src/api/schema.ts` is generated from that snapshot (verify the tool at implementation time;
   `openapi-typescript` is the usual choice). Never edit it by hand.
3. CI (`test` workflow) regenerates both and fails if either differs from the committed file.
4. Keep the snapshot deterministic: stable key order, no timestamps, no server URL from the environment.
