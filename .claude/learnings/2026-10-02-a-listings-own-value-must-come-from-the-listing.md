# A RIS row bridged a note's `unknown` track into a listing, because the exemption read the cluster, not the claim

**Key lesson:** When a rule exempts "a listing's own" value, check which claim supplies that value, not only whether the cluster is a listing. Step 1 merges any same-id records unconditionally, so a note plus a RIS row naming a proceedings paper is a listing whose resolved track is still the note's.

- **Date:** 2026-10-02 · **Task:** task-174 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/dedup.py` (`_family`), `backend/tests/unit/ingest/test_dedup.py::test_a_note_with_no_track_never_merges_into_a_listing_it_names`, `backend/tests/unit/ingest/test_dedup_props.py` (`RIS_BRIDGE`), nightly proof run 37017691575

## What we set out to do
Triage a nightly property failure in `test_track_is_openreview_where_it_holds_the_paper_else_the_proceedings`: a merged NeurIPS 2024 record took OpenReview's `unknown` over a main-track listing.

## What we learned
- The track rule's exemption for "a listing's own `unknown`" (a mixed PMLR volume, v235/v267) was written as `c.listed and c.summary.track == "unknown"`. An OpenReview v1 note (track `unknown`) and a RIS row with the same id merge in step 1 whatever their tracks. The RIS row's `urls.pdf` names `nips-<hash>`, so the cluster is `listed`, and its track resolves to OpenReview's `unknown` (OpenReview ranks first). `_family` then called it `proceedings`, and step 2 merged it with the `nips-<hash>` listing by title (evidence: the blob reproduces with `pytest -n 0` before the fix and passes after).
- The same hole had a second shape the nightly never drew, and review found it: a note whose own `urls.pdf`/`urls.proceedings` names the paper is a listing too. The property skipped exactly that case (`not proceedings_ids(note_urls)`), so its oracle now checks every record with both an OpenReview and an official track claim. The rule is now "no OpenReview source in the cluster" (`OPENREVIEW_SOURCES & c.sources`), which covers both shapes.
- The oracle was right. decision-005 §Track says an OpenReview `unknown` never overrules a listing's track, and the dedup-rules skill says the exemption is only the listing's *own* `unknown`. The fix grants it only when no OpenReview track claim is present.
- Real data never had the shape. No record in snapshot `2026-09-29-d552baa07aed` is a listing with an OpenReview `unknown` track claim. Scratch builds from origin/dev and from the fix (both rounds) over one cloned cache all hash `8adf9327771a`.

## Dead ends — don't repeat these
- Diffing the scratch build against the real snapshot alone looked like a 104-record change. That was dev drift (TASK-159's schema v4 provenance), so build a baseline from the unmodified base branch over the same cache before attributing a diff. `git archive origin/dev backend/src` plus `PYTHONPATH` runs the base code without a second worktree, and a running test job in the worktree is left untouched.

## Decisions (and what would change them)
- A note's `unknown` stays apart from a listing even when a RIS row ties them → decision-005 §Track. It would change only if the owner decided a RIS proceedings URL is track evidence.

## Follow-ups
- none

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/dedup-rules/SKILL.md` (track-rule exemption), decision-005 §Track
- Test or hook added? — the unit test and `RIS_BRIDGE` example above
