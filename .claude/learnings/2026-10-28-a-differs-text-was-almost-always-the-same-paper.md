# A `differs` text was almost always the same paper, not a wrong attach

**Key lesson:** Before reading a text-mismatch class as a matching error, check the pair's identity by another field (authors here): 122 of the 123 OpenAlex texts that `differs` from AAAI's archived abstract were the same paper, and its OpenAlex text was a median 2.4× as long.

- **Date:** 2026-10-28 · **Task:** task-250 · **Area:** eval
- **Artifacts:** `backend/src/openproceedings/eval/openalex_audit.py` (`library_check`, `_differs_authors`, `shape`), [2026-10-28 report](../../docs/results/2026-10-28-openalex-audit.md), spec 07 §G

## What we set out to do
Split the 123 AAAI 1980–2008 `differs` texts of the `aaai_library` comparison into wrong-paper attaches and genuinely different texts, and add AIES 2026 to the DOI route.

## What we learned
- The title route's attaches are nearly always the right paper: of the 123, 122 share an author surname with the record; the 1 that doesn't (`Pedersen98a`, pedersen/pederson) is a near spelling of the same first author, as the title-route check's one flag (`nournai`/`nourani`) was. Evidence: the report's "The `differs` texts" section.
- The mismatch is in the text, not the match: 86 of the 122 OpenAlex texts are at least 1.5× AAAI's length and only 63 open with the same 5 search tokens, so OpenAlex's text for these years often runs past the abstract or is another extraction. The 10.9% `differs` rate is a text-fidelity figure, not a wrong-attach rate.
- The author check reuses the title route's `_judge` and `authors_url` unchanged, so it costs one request per 50 works (3 for the 123) and replays from the cache byte for byte.
- Requests for the whole re-run: 9 (6 DOI batches for AIES 2026's 265 records, 3 author batches); everything else came from the cache.

## Dead ends — don't repeat these
- None. The offline replay first (0 requests, same figures as 2026-10-16) showed exactly what a live run would add before any request was sent.

## Decisions (and what would change them)
- The title-route ruling (exact title key and year, controller 2026-10-11) stands: no wrong-paper attach is evident among the 1,131 compared. A future `wrong` without a near-spelling surname would reopen it.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: spec 07 §G and the report carry the finding; the lesson is a method habit, recorded here.
- Test or hook added? — `backend/tests/unit/eval/test_openalex_audit.py` (the author verdicts, the rendered split, `shape`).
