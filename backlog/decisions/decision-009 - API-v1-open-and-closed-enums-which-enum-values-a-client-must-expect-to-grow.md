---
id: decision-009
title: 'API v1 open and closed enums: which enum values a client must expect to grow'
date: '2026-09-27 11:20'
status: accepted
---
## Context

`/api/v1` freezes at its first release (M3a review-gate). The api-contract skill already allowed "a new
enum value in a field the clients treat as open", but nothing said which fields those are, so every enum in
the OpenAPI document was implicitly closed: adding a venue (M4 adds none yet, but a fourth conference is
plausible), a track, a diagnostic or error code, or an index input to `ChangedInput.input` would have been a
breaking change needing `/api/v2`. The generated TypeScript (`frontend/src/api/schema.ts`) turns each enum
into a union, so a client that `switch`es exhaustively breaks silently on a value it has never seen.

Options considered:
1. Every enum closed; any new value is `/api/v2`. Safe for clients, but the registry of error and
   diagnostic codes grows with every parser change (spec 02), which would force a new API version for a new
   warning.
2. Every enum open. Clients must then handle an unknown `mode`, `sort` or replay `status`, values whose
   meaning the whole contract depends on (a fourth replay status would change what "citable" means).
3. Classify each enum once, in one table, and state the class in the schema. Chosen.

## Decision

We classify every enum of the `/api/v1` OpenAPI document as open or closed in
`backend/src/openproceedings/api/openapi.py` (`OPEN_ENUMS`, `CLOSED_ENUMS`). **Open** (a new value may
appear within v1; clients must handle one they don't know): error codes (`ErrorCode`), diagnostic codes
(`DiagnosticCode`, and the plain-string `code` of a stored record's diagnostics), `venue`, `track`, `status`,
`presentation`, a provenance claim's `source` and `field`, the text and filter field names (`/meta`,
`defaults`, the AST's `field`), and `ChangedInput.input`. **Closed** (a new value is a breaking change):
`mode`, `sort`, the export `format`, the replay `status`, `ChangedInput.kind`, a wildcard's `op`, and
`include`. The document marks each open enum's schema with "Open set: … handle a value you don't know."

## Consequences

- Spec 04 §Conventions lists both classes; the api-contract skill's versioning rules point at the table.
- `backend/tests/contract/test_contract_v1.py` fails when the document holds an enum in neither table, so a
  new enum is classified in the PR that adds it; moving an enum from open to closed is breaking.
- The frontend must render an unknown venue, track, status or code (show it raw), never assume the union is
  exhaustive. That is a frontend obligation (spec 05), not enforced by the types.
- An open enum is still emitted as an `enum` list in the schema (the values known today), so a client that
  validates responses against the schema must be configured leniently for open enums (accept a string not in
  the list), or it will reject a value added within v1. The "Open set" note is what tells it which ones.
- Nothing about `index_version`, `canonical_hash` or stored search records changes: this is a statement about
  the wire contract only. Revisit if a closed enum needs a value (that is `/api/v2`, or a new decision).

