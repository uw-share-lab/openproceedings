# A forum link is identity evidence, so it has to block title merges as well as make its own

**Key lesson:** Once a PMLR listing's `urls.forum` claim can merge it with an OpenReview note, the same linked forum id must also count in every other never-merge check. Otherwise the title step can still fold that listing into a *different* note with the same title, while the link says it is another paper.

- **Date:** 2026-09-27 · **Task:** TASK-105 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/dedup.py` (`_link`, `_forum_ids`, `_mergeable`,
  `_refusals`), `backend/src/openproceedings/ingest/urls.py` (`forum_id`),
  `backend/tests/unit/ingest/test_dedup_forum_link.py`, `backend/tests/unit/ingest/test_dedup_props.py`
  (`links`, `LINK_AGAINST_TITLE`)

## What we set out to do
Join PMLR (ICML 2023+) and OpenReview records on the forum link that PMLR's index carries, before the title
match, and whatever the titles say. A link across venue-years must become a conflict row, not a merge.

## What we learned
- **Only v235 is recorded with the link.** v28 has none, and v220 is a NeurIPS competition volume. The claim
  that v202 carries the link comes from the research notes, not from a fixture.
- **The scrubbed titles differ by source.** The PMLR index has `Synthetic title 1` and the OpenReview note
  has `Synthetic title text 1.`, so no title key matches. That makes the fixtures a clean control: without
  the link nothing merges.
- **Cloned notes share one title.** Linking three of them gives three records with the same title key and an
  `ambiguous_not_merged` row. Give each clone its own title, or assert only on the rows you mean.
- **The link doesn't need the source-disjoint rule.** That rule settles which of two same-source title
  candidates is the paper. With a link, the id already says which paper it is. Two forum ids, two
  proceedings ids or the track rule still refuse the link.
- **`forum_link` rows point from a listing id to the forum id.** `with_crawl_conflicts` already follows any
  row whose `merged_id` differs from its `survivor_id`. The property test's `final_ids` had to follow
  chains of those rows too.

## Dead ends: don't repeat these
- Treating the linked forum id as only a merge key. The first draft let `pmlr(link→Y)` still title-merge
  with note X. `_mergeable` now counts own and linked forum ids.

## Decisions (and what would change them)
- A refused link is reported as a pair on the output records (`field = forum_id`, or `forum_id_chain`),
  like the title refusals, so a second run reports the same rows. This would change only if links could
  chain, which they can't while a cluster naming two forum ids never links.

## Follow-ups
- [ ] (proposed, no task yet) `pmlr._forum` should call `urls.forum_id`. It wasn't changed because
  TASK-103 is refactoring `sources/*`.
- [ ] (proposed, no task yet) Record a v202 and a v267 index fixture to confirm which volumes carry the link.

## Propagated to
- Skill / agent / CLAUDE.md updated? `.claude/skills/dedup-rules/SKILL.md` (merge order, never-merge,
  audit formats, properties); `.claude/skills/record-schema/SKILL.md`; `.claude/skills/pmlr-proceedings/SKILL.md`;
  `.claude/agents/dedup-auditor.md` (Musts); spec 01 §Pipeline 4 and §Testing.
- Test or hook added? `test_dedup_forum_link.py` (fixture table), forum-link unit tests in
  `test_dedup.py`, and the `links` strategy with its pinned examples in `test_dedup_props.py`.

## Addendum — 2026-10-03: arbitrary Unicode also reaches property-test seeds

The corrected nightly run37112111841 failed its ingest property before checking production behavior:
`random.Random(title)` uses strict UTF-8 to encode a string seed, but the Unicode strategy deliberately
includes lone surrogates. The shrunk input U+0301, U+0301, U+D800 enters the two-mark shuffle and raises
UnicodeEncodeError. Keep the arbitrary Unicode domain; filtering surrogates would hide a fixture defect.
Use deterministic `title.encode("utf-8", "surrogatepass")` seed bytes instead and retain that exact input
as an explicit example. Ordinary Unicode seeds keep the same encoded bytes; surrogate code points are
represented without replacement or loss. The canonical forms, mark-shuffle condition and title-key
assertion remain unchanged; production code is untouched.

The explicit example reproduced RED (1 failed,0.30s) at the original Random seed; all138 dedup tests
then passed (0.53s). A test-local raw-title-key replacement failed the unchanged canonical-equivalence
assertion on the existing Caf\é example, confirming the property still checks canonical equality. An
attempt to remove only title_key's NFC step did not fail: the current underlying normalizer also handles
that normalization, so that diagnostic is not claimed as a distinguishing negative control. Raw evidence:
/tmp/task171-unicode-seed-red.log, /tmp/task171-unicode-seed-green.log,
/tmp/task171-unicode-canonical-negative.log and /tmp/task171-unicode-no-nfc-control-pass.log.
Propagated to backend/tests/unit/ingest/test_dedup.py. Full final gates and corrected remote proof remain pending.
