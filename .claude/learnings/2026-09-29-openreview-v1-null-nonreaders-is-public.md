# OpenReview API v1 writes `nonreaders: null` on public notes

**Key lesson:** In an ACL check, treat an explicit `null` as the field's empty value only where the API documents it that way. Keep every other malformed shape failing closed, and pin the falsy look-alikes (`""`, `{}`, `False`, `0`) as refused, so that "accept null" never becomes "accept falsy".

- **Date:** 2026-09-29 · **Task:** task-119 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_client.py` (`_world_readable`), `backend/tests/unit/ingest/test_openreview_client.py::test_a_null_or_empty_top_level_nonreaders_excludes_no_one`, `test_a_null_nonreaders_does_not_make_a_private_note_public`, `backend/tests/unit/ingest/test_openreview_v1.py::test_iclr_2017_notes_with_a_null_nonreaders_are_public_and_imported`

## What we set out to do
Run the first live OpenReview crawl for the M4 coverage gate (TASK-054).

## What we learned
- `op ingest openreview --venue ICLR --years 2013-2025` finished 2013–2016 and then refused ICLR 2017 with `private_response` ("note response is not world-readable; use credentials without venue roles"). The advice about venue roles was a red herring.
- In one authenticated diagnostic read of `ICLR.cc/2017/workshop/-/submission`, all 161 notes have `readers: ["everyone"]`. 102 have `nonreaders: []` and 59 have `nonreaders: null`. The conference listing (490 notes) has none (evidence: counts from that read; only ids and ACLs were printed, no content).
- `_world_readable` required `nonreaders` to be a list, so `null` failed closed. Because the guard refuses a whole page (dropping a row would break offset pagination), one null aborted the crawl for ICLR 2017 onwards.
- The projection's cache version did not need a bump. The new rule only admits pages the old one refused, and a refused page was never cached, so every cached entry still passes.

## Dead ends — don't repeat these
- The refusal message suggests the account has venue roles. Check the ACL values before chasing credentials: `Counter(repr(n.get("nonreaders", "<absent>")))` showed the cause at once. A diagnostic that writes `n.get("nonreaders") or ()` hides it, because it prints `None` and `[]` the same way.

## Decisions (and what would change them)
- Only `None` (or no key) means that no one is excluded. `""`, `{}`, `False`, `0` and other non-lists are still refused, pinned by tests. Revisit only if the API documents another empty form.

## Follow-ups
- [ ] task-054 — re-run the ICLR OpenReview crawl on this fix (queued behind the NeurIPS and ICML OpenReview crawls on 2026-09-29).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` (the exact world-readable rule), `docs/specs/01-ingestion.md` (§Pipeline projection)
- Test or hook added? — the three tests above
