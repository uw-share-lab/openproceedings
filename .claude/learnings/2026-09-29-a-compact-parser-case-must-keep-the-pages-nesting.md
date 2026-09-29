# A compact parser test passed while the live page gave one entry forty authors

**Key lesson:** When a compact parser test reproduces a live page's odd markup, copy its nesting too, including what the container goes on to hold. Then check the fix on the cached live page, not only on the test.

- **Date:** 2026-09-29 · **Task:** task-124 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/iclr.py` (`_bare_authors`), `backend/tests/unit/ingest/test_iclr.py::test_an_entry_outside_any_paragraph_is_read_with_the_next_blocks_authors`

## What we set out to do
Recover the ICLR 2014 archive's 35th paper, which the first full coverage trial counted as missing (34 of 35).

## What we learned
- The missing entry, arXiv 1312.6055, sits in a bare `<span><b><a>` with its authors in the next `<div><i>`. The parser only read paper links inside a `<p>` (evidence: the cached 2014 page, diffed by arXiv id against the parsed targets).
- The first fix took the whole next `<div>` as the author block. It passed a compact test whose `<div>` held only the authors. On the cached live page, though, that `<div>` holds every later entry of the page, so the paper got about forty "authors". The corrected fix takes only the `<div>`'s first inline element, and the test now nests later entries inside the `<div>` as the page does.
- Before the check: 35 entries, one with a runaway author list. After: 35 entries, and "Unit Tests for Stochastic Optimization" has Tom Schaul, Ioannis Antonoglou and David Silver.

## Dead ends — don't repeat these
- Matching page links to parsed entries by URL string. The parser canonicalises `http://arxiv.org` to `https`, so everything looked unmatched. Compare arXiv ids.

## Decisions (and what would change them)
- The fallback applies only to a paper link with no `<p>` ancestor. Links inside paragraphs keep the old rule.

## Follow-ups
- [ ] task-054 — the other trial misses (ICLR 2013, NeurIPS OpenReview-accepted absent from proceedings)

## Propagated to
- Skill / agent / CLAUDE.md updated? — `docs/research/2026-09-27-openreview-and-proceedings-facts.md` (§ICLR accepted-paper archive, the 2014 markup)
- Test or hook added? — the test above, with the live nesting
