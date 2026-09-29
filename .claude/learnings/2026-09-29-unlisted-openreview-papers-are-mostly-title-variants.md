# On real data, most "unlisted" OpenReview acceptances are listed under another title

**Key lesson:** Before trusting a decision-005 `unknown` (OpenReview-accepted, not in the crawled proceedings), look for an unmerged listing in the same cell: 5 of the 6 on the 2026-09-29 crawl were the same paper renamed or with a title mangled by `html.py` dropping a charref's `;` (`&#x27;Catch` → `⟊tch`), and only 1 (NeurIPS 2024 `ftqjwZQz10`) was really absent.

- **Date:** 2026-09-29 · **Task:** task-072 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/reconcile.py`, `backend/tests/unit/ingest/test_reconcile.py`, decision-005 (§Built, §Track in an OpenReview venue-year), `docs/results/2026-09-29-reconcile-real-data.md` (the numbers below, with commands)

## What we set out to do
Build decision-005's reconcile step and check it against the real cache.

## What we learned
- The rule made 6 records `unknown`: NeurIPS 2023 main 1 and D&B 2, 2024 main 1, 2025 main 1 and D&B 1. Every one
  of those cells then equals its official count, because each pair had counted twice (the note and the listing).
- Paired with the unmerged listings in the same cells: INSPECT, DynaDojo and GuardSet-X → PolyGuard were renamed for
  the camera-ready. Two are mojibake: `_TextParser.handle_charref` appends `&#<name>` without the `;`, so
  `html.unescape` reads `&#x27Ca`/`&#x27ec` as one hex charref (`Fr\'echet` → `Fr\⟬het`, `'Catch` → `⟊tch`). Any
  title with `&#x27;` or `&#39;` followed by a hex/decimal digit is affected (TASK-128). DEX (NeurIPS 2024) isn't on the 2024
  or 2025 listings at all.
- An absence claim has to be distinguishable from a listing's claims: synthetic pools give proceedings sources
  every status, so "a proceedings `status=unknown`" alone misfired; the `not listed:` evidence prefix is the mark.

## Dead ends — don't repeat these
- `pytest -p no:logging` to quiet the output removes `caplog`: 45 setup errors that look like a regression.

## Decisions (and what would change them)
- Decision-005's track row (proceedings answer track only where OpenReview doesn't) was measured, not enforced: it
  would take ICLR 2016 main to 0 and ICLR 2014 main to 34/35. The review lead's reading of "on OpenReview" decides (TASK-130).

## Follow-ups
- [ ] TASK-128: the `html.py` charref bug (hid two correct titles; lands before TASK-072, then the real-data check
  is re-run).
- [ ] TASK-130: decide and enforce decision-005's track row in an OpenReview venue-year.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/dedup-rules/SKILL.md` §Reconcile; decision-005.
- Test or hook added? — `backend/tests/unit/ingest/test_reconcile.py` (the absence mark is exercised by the pools).
