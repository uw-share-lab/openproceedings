# A count a stored record derives belongs in a computed field that the store never writes

**Key lesson:** Put a count that a stored record can derive (`identified_total = total + excluded.total`) in a pydantic `computed_field` and exclude it from the stored body (`records.DERIVED`). Then every old body reads with it, no stored value can disagree with its own counts, and the OpenAPI schema still marks it required. Check each /api/v1 change with `test_openapi_additive.py` against `origin/dev`, not by reading the diff.

- **Date:** 2026-09-27 · **Task:** task-090, task-091, task-112 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/records.py` (`SearchRecord.identified_total`, `DERIVED`), `backend/src/openproceedings/api/middleware.py` (`stored_read`), `backend/tests/contract/test_openapi_additive.py`, `backend/tests/contract/test_ui_additions.py`, decision-014

## What we set out to do
Add the fields the M3b UI design asked for (identified and unclassified counts, a save pinned to the shown
index, a record read without a replay, coverage citability and clause spans), all additive under /api/v1.

## What we learned
- **`computed_field` is required and `readOnly` in the serialization schema**, so it meets the "every field
  sent is required" rule with no extra config (evidence: the snapshot diff shows `SearchRecord.required` grow
  by both names, with `readOnly: true`). It also lands in `model_dump_json`, so the store's body writer has to
  exclude it. Reading a body that carries one anyway is harmless, because `_Stored` ignores unknown keys, and
  `tampered` test rows rely on that.
- **A cheaper read on a route charged before routing needs the middleware to parse the query itself.** The
  rate limit charges `export_weight` by path before FastAPI sees the parameters. `stored_read` reads
  `replay` with pydantic's own bool rule (`TypeAdapter(bool)`), so `0`, `off`, `no` and `false` all count,
  and it is cheap only when every parameter is one the route takes, each given once. A repeat or unknown
  parameter pays the full weight (evidence: `test_a_request_the_route_refuses_is_charged_in_full`, whose
  `replay=false&x=1` case failed until the unknown-key check was added).
- **Widening nullability is breaking by the skill's rules, even when only an opt-in parameter sends the
  null.** A typed client's type widens. The exception is written down as decision-014 and allowed by name in
  the additive checker, and a test shows the same widening anywhere else is still caught.

## Dead ends — don't repeat these
- The first `blocking_spans` golden case used an emoji query, which parses as `PARSE_EMPTY_TERM` and gives
  no filters. Use a letter-like astral character (`𝔘`) to exercise code-point spans.
- `(year:2020 OR y) year:2021` is not `multiple_clauses`: a nested clause beside one top-level clause
  doesn't block it (spec 02). Flatten an AND group, `year:2020 (year:2021 y)`, to get two.

## Decisions (and what would change them)
- `blocking_spans` are the written top-level conjuncts that hold a filter of the field, not the filter
  leaves inside them. The conjunct is what a reviewer edits by hand. Reverse this if the UI needs to
  underline the leaf.
- The save's pin is checked before the parse and the save ceilings, so a stale page spends no save.
  Reverse this if pins ever name non-served indexes that can be saved on.

## Follow-ups
- [ ] none: the UI tasks that consume these (TASK-042, TASK-044, TASK-045) already exist.

## Propagated to
- Skill / agent / CLAUDE.md updated? `.claude/skills/api-contract/SKILL.md` (derived counts, decision-014,
  the additive checker), `.claude/skills/search-records/SKILL.md` (derived fields never stored, the pin,
  `replay=false`).
- Test or hook added? `backend/tests/contract/test_openapi_additive.py`, `backend/tests/contract/test_ui_additions.py`.

## Addendum — 2026-09-30 (TASK-112: `PaperRecord.venue_name`)
The same pattern on a **strict, `extra="forbid"` stored model** (`PaperRecord`, loaded with
`model_validate_json`) has two traps that `SearchRecord`'s lenient `_Stored` reader hid.
- **A dump no longer validates as input.** `model_dump()` now carries the computed field and `extra="forbid"`
  refuses it, so every dump that is validated again must pass `exclude={*DERIVED}` (`record.DERIVED`;
  `snapshot.record_line` and `PaperRecord.model_copy` do). mypy wants a `set`, not the frozenset itself
  (`IncEx`). Evidence: the full suite without those excludes failed only `test_round_trips_through_json` and
  `test_a_stale_hash_is_rejected_on_load`.
- **Tests that expect a refusal can start passing for the wrong reason.** `test_an_extra_field_is_rejected`,
  `test_every_required_field_is_required` and `test_stored_data_can_never_ask_for_a_new_hash` validate a dump
  and expect an error; with the computed field in the dump they were refused for `venue_name`, not for what
  they test. They now dump with `exclude={*DERIVED}`. After adding a computed field, grep the tests for
  `model_dump` feeding `model_validate` and check each refusal still refuses for its own reason.

**Dead end:** a `model_validator(mode="before")` that pops a matching `venue_name`, so dumps would round-trip.
Any before-validator on the model makes `model_validate_json` hand pydantic a Python dict, so the strict
fields lose JSON-mode coercion: 24 snapshot tests failed loading (`datetime_type`, `tuple_type`,
`int_type`). Don't add a before-validator to a strict model loaded from JSON.

**Decision:** derived, not stored, so no `RECORD_SCHEMA_VERSION` bump, no index rebuild and no
`index_version` change; every index already served sends it. Reverse if a derived value ever depends on
something outside the record (then it has to be stored, and versioned).
