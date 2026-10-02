# OpenReview's `_bibtex` url can name the wrong forum, so corroborate it before linking on it

**Key lesson:** Before trusting a field that names another record (here a v1 note's `_bibtex` url), tally what it names across the whole listing. All 35 ICLR 2017 `Invite to Workshop` notes named one unrelated forum. Accept such a link only when an independent signal agrees (the same dedup title key). Add a cross-record link as a provenance-only claim, so `op snapshot diff` shows exactly the linked records as `provenance_only` and nothing else moves.

- **Date:** 2026-10-02 · **Task:** task-159, task-157 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_v1.py` (`link_twins`, `is_twin_outcome`, `submission_listing`), `backend/src/openproceedings/ingest/ris.py` (`_invitation`, `_twin_outcome`), DECISION-TASK159, `docs/results/2026-10-02-iclr-2017-twins.md`

## What we set out to do
Link ICLR 2017's workshop-listing copies to their conference twins (the owner chose to link them, not merge
them), and let the RIS importer tell a copy from a real rejection by scholarmend 0.1.5's `invitation` claim.

## What we learned
- TASK-152 had found that the 18 `Submitted to ICLR 2017` copies' `_bibtex` names their title twin. The tempting
  generalisation, "a `_bibtex` naming a conference forum is a twin link", is wrong. All 35 `Invite to Workshop`
  notes' `_bibtex` name `B1akgy9xx`, a conference note with another title. A bare `_bibtex` rule would have
  linked 35 papers to one wrong record. (Evidence: a tally over the cached workshop listing.)
- The dedup title key is the reliable signal. Only ICLR 2017 has non-main submission notes whose key matches a
  main-track note: every other v1 adapter's workshop, Tiny Papers, BlogPosts and D&B listings have 0. So a
  generic rule in the crawler touches one venue-year. Measure every adapter before deciding whether a rule needs
  a venue-year guard.
- The title rule found 53 copies, not the 52 the task assumed: a workshop note with no `content.venue` also has
  one conference match. Two conference notes each have two copies, so the `twin` value is a tuple. That gives 51
  conference twins and 104 linked records.
- A claim field holding a list needs `_CLAIM_KINDS` (tuple). Without it, a `Claim` with a tuple value is refused.
- Provenance is not in `content_hash` and is never indexed. A link carried as a claim therefore leaves track,
  status, hashes, merges and conflicts unchanged, and `op snapshot diff` reports the 104 as `provenance_only`.
  New `ClaimField` values still bump `RECORD_SCHEMA_VERSION`, change the OpenAPI enum (`make openapi`), and
  change the combined snapshot test's `FILES_HASH` (the manifest's version) but not its `SNAPSHOT_HASH`.
- The RIS importer can reuse the crawler's rule as a function (`is_twin_outcome`). With one rule, the two paths
  can't drift, and a test feeds the same recorded note to both.

## Dead ends — don't repeat these
- Writing a test that clones a recorded note under a new id to make a second main-track submission with the same
  title. Rule 5 collapses identical notes, so the clone vanishes. Change a compared field (the abstract) to keep
  it.
- Adding fixture rows in the middle of `generate.py`'s v1 rows. Other tests address rows by index
  (`ris_record_of(…, 12, …)`), so append them.

## Decisions (and what would change them)
- Link, don't merge (the owner, 2026-10-02): the two notes are different submissions with their own outcomes.
  Revisit if exports or the UI need to count a paper once across tracks (the deferred "see also").

## Follow-ups
- Deferred by the owner: a visible "see also" between twins in the results and exports (reported to the lead).

## Propagated to
- Skill / agent / CLAUDE.md updated? — record-schema (claim fields, schema 4), dedup-rules (§Never merge),
  openreview-api (rule 6), openreview-venueids (the 2017 row), snapshots (`twins_linked`, the render check),
  ris-importer agent; spec 01
- Test or hook added? — `test_openreview_v1.py` (link rules, the bogus `_bibtex`, ambiguity, tuples, dedup, the
  render check, the crawler-vs-RIS agreement), `test_ris.py` (the invitation rows)
