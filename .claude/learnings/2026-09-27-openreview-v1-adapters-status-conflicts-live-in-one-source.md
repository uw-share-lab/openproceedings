# A v1 note can contradict itself, so conflicts.csv needs rows that dedup never makes

**Key lesson:** In OpenReview API v1 one submission note can carry two status signals that disagree (a withdrawn invitation and an accepted `content.venue`, or two decision notes), and a record allows one claim per field and source, so the v1 crawler sets that field to `unknown` and hands an `unresolved:openreview_v1` row to `snapshot.with_crawl_conflicts`: a disagreement inside one source never reaches dedup, which only compares sources.

- **Date:** 2026-09-27 · **Task:** TASK-051 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/openreview_v1.py`,
  `backend/src/openproceedings/ingest/snapshot.py` (`with_crawl_conflicts`),
  `backend/tests/unit/ingest/test_openreview_v1.py`
  (`test_iclr_2021_venue_first_then_the_decision_note_and_the_withdrawn_conflict`,
  `test_the_snapshot_build_replays_v1_crawls_and_writes_their_conflicts`)

## What we set out to do
Build the API v1 adapters (ICLR 2013–2023, NeurIPS 2021–2022), wire them into `op ingest openreview` and the
snapshot replay, and test them only against the TASK-002 recorded fixtures.

## What we learned
- **dedup's conflicts are cross-source only.** `PaperRecord` refuses two claims for one (field, source), and
  `dedup` writes rows only when sources disagree, so `xGZG2kS5bFk` (withdrawn invitation, `ICLR 2021 Poster`)
  had no way into `conflicts.csv`. The crawl report now carries its own `Conflict` rows, and the snapshot
  build adds them after dedup, re-pointed along `merges.csv` to the surviving id.
- **A decision string often names no track.** `Reject` and `Accept (Poster)` say nothing about the track, so a
  v1 outcome's track is optional and falls back to the listing the note was submitted under; `Invite to
  Workshop Track` and ICLR 2013's `…-workshop` do name one.
- **A decision note must be tied to its paper three ways:** the exact per-year invitation with this
  submission's `Paper<number>`, `forum == submission id`, and `replyto == submission id`. The ICLR 2019 test
  shows a meta-review copied into another forum is ignored.
- **Scrubbed fixtures share titles.** Every recorded note is "Synthetic title text 1.", so a snapshot built
  from several fixtures gets `ambiguous_not_merged` rows; assert on the rows you mean, not on the total.
- **Early ICLR 2017 notes give `authors` as one string** (with `author_emails`); splitting it would be a guess.

## Dead ends — don't repeat these
- Treating ICLR 2020's accept strings as known: only `Reject` is recorded. The adapter leaves the others
  unmapped (`unknown`, counted) until a live accepted forum is recorded.
- Complex inline `python3 - <<EOF` patches in a worktree agent: the sandbox refuses them as unverifiable;
  write the script to the scratchpad and run it.

## Decisions (and what would change them)
- Within-source disagreement → field `unknown` + `unresolved:openreview_v1` row, never one side picked
  (openreview-api skill) → a decision that one v1 signal outranks another.
- Only live-verified invitations and strings are in `ADAPTERS` → a recorded fixture for each missing one
  (ICLR 2023 Blogposts, NeurIPS withdrawn/desk-rejected, ICLR 2020/2021 accept decisions).

## Follow-ups
- [ ] (proposed, no task yet: parallel-branch ids) record live fixtures for the v1 gaps listed in the TASK-051
  notes, then extend `ADAPTERS`.
- [ ] (proposed, no task yet) decide how to split early ICLR 2017 `authors` strings (`authors_unsplit`).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-api/SKILL.md` §The v1 crawler as built;
  `.claude/skills/dedup-rules/SKILL.md` (the new resolution); `.claude/skills/snapshots/SKILL.md`
  (`sources.openreview_v1`); `.claude/skills/record-schema/SKILL.md`; `.claude/agents/openreview-crawler.md`;
  `CLAUDE.md` layout; spec 01 §CLI; spec 08 layout.
- Test or hook added? — `backend/tests/unit/ingest/test_openreview_v1.py` (one replay test per adapter).
