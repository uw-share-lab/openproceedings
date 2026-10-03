---
id: decision-014
title: >-
  API v1: a response field may be null only in answer to a new opt-in parameter
  (GET records replay=false)
date: '2026-09-27 20:41'
status: accepted
---
## Context

The record page (spec 05; `docs/design/2026-09-27-export-records-and-paper.md`, pre-pass S4) must show a
record's recorded fields and methods text while its replay can't run: a 429, or 503 `API_BUSY` while every
verification slot is taken. `GET /records/{id}` always replayed, so the page showed nothing then. TASK-091
adds `?replay=false`, which reads the stored record and runs nothing. Its answer has no replay to give.

The api-contract skill lists "changing a field's nullability" as breaking under `/api/v1`: a client that
reads `replay` without a null check would fail. The options:
1. **`RecordResponse.replay` becomes `ReplayInfo | null`, null exactly when the request asked
   `replay=false`.** One route and one response model. A client that never sends the new parameter never
   sees a null: the wire behaviour of every request it can make is unchanged. A generated client's type
   widens, so a typed client that reads `replay` needs a null check at compile time.
2. A separate resource (`GET /records/{id}/stored`) with its own response model: nothing widens, but the
   record gets two resources for one object, and every consumer has to choose between them.
3. Send `replay` with every field null (a sentinel): not a replay, and `status` is a closed enum, so there
   is no honest value for it.

## Decision

We allow a response field to become nullable within `/api/v1` only when the null is sent exclusively in
answer to a new, optional parameter whose default keeps the old answer. `RecordResponse.replay` is the one
such field: null exactly when the request says `replay=false`, never otherwise.

## Consequences

- Spec 04 §Search records and the api-contract skill state the rule and the one field it covers.
- `backend/tests/contract/test_openapi_additive.py` compares the committed OpenAPI snapshot with the
  released one on `origin/dev` and fails on every breaking change; its `ALLOWED` set lists
  `RecordResponse.replay` (nullable) with this record, and a test holds that the same widening anywhere else
  is still found.
- `backend/tests/contract/test_ui_additions.py` holds that `replay` is non-null on every request without
  `replay=false`.
- A typed client (the frontend's `schema.ts`) now types `replay` as nullable and must check it; the record
  page does anyway, to show "Replay: waiting".
- Any later widening needs its own record; this one is not a general licence.
