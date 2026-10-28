# A `differs` text was almost always the same paper, not a wrong attach

**Key lesson:** Before reading a text-mismatch class as a matching error, check the pair's identity by another field (authors here): 122 of the 123 OpenAlex texts that `differs` from AAAI's archived abstract were the same paper, and its OpenAlex text was a median 2.4× as long.

- **Date:** 2026-10-28 · **Task:** task-250 · **Area:** eval
- **Artifacts:** `backend/src/openproceedings/eval/openalex_audit.py` (`library_check`, `_differs_authors`, `shape`), [2026-10-28 report](../../docs/results/2026-10-28-openalex-audit.md), spec 07 §G

## What we set out to do
Split the 123 AAAI 1980–2008 `differs` texts of the `aaai_library` comparison into wrong-paper attaches and genuinely different texts, and add AIES 2026 to the DOI route.

## What we learned
- The title route's attaches are nearly always the right paper: of the 123, 122 share an author surname with the record; the 1 that doesn't (`Pedersen98a`, pedersen/pederson; single-author on both sides) is a near spelling, likely the same first author (by a character ratio, not checked by a person), as the title-route check's one flag (`nournai`/`nourani`) was. Evidence: the report's "The `differs` texts" section.
- The mismatch is in the text, not the match: 86 of the 122 OpenAlex texts are at least 1.5× AAAI's length and 63 open with the same 5 search tokens; 47 do both (a text that runs on past the abstract), and the rest have no one shape. Report the joint count, not two marginals, before naming a shape. The 10.9% `differs` rate is a text-fidelity figure, not a wrong-attach rate.
- The author check reuses the title route's `_judge` and `authors_url` unchanged, so it costs one request per 50 works (3 for the 123) and replays from the cache byte for byte.
- Running the audit `--offline` first (0 requests, the 2026-10-16 figures unchanged on the new snapshot) showed what a live run would add before any request was sent.
- Requests for the whole re-run: 9 (6 DOI batches for AIES 2026's 265 records, 3 author batches); everything else came from the cache.

## Dead ends — don't repeat these
- Naming the rule's bucket "wrong-paper attaches" outright: the one case was a near spelling, and the report contradicted itself until the bucket said "look like" (review round 1).

## Decisions (and what would change them)
- The title-route ruling (exact title key and year, controller 2026-10-11) stands: no wrong-paper attach is evident among the 1,131 compared. A future `wrong` without a near-spelling surname would reopen it.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: spec 07 §G and the report carry the finding; the lesson is a method habit, recorded here.
- Test or hook added? — `backend/tests/unit/eval/test_openalex_audit.py` (the author verdicts, the rendered split, `shape`).
