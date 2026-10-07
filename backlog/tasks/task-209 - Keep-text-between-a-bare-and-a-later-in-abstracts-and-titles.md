---
id: TASK-209
title: Keep text between a bare < and a later > in abstracts and titles
status: In Progress
assignee: []
created_date: '2026-10-07 17:07'
updated_date: '2026-10-07 17:49'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found during TASK-208 and approved by the owner on 2026-10-07: on every Python release, ingest/sources/html.py hands any < followed by a letter to the standard-library parser as a tag, so abstract text between a bare < and a later > is dropped (if a<b and c>d then reads if ad then; p<\infty$. For $1\leq p<2$ swallows a sentence). Maths-heavy abstracts are common in this corpus, so this loses searchable words. The fix belongs in the shared HTML path so every crawler (NeurIPS, PMLR, ICLR, the ICML sites) reads it the same way, on the pinned 3.12.15 and as 3.12.9 would, without undoing TASK-208's kept readings (a tail without > stays text; only script and style are raw text) or TASK-207's contact-stripping parsers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A < that does not start a real tag stays text in html.py's text_of, parse/node_text and metas, the same on 3.12.9 and 3.12.15; real tags (known element names with real attributes) still parse
- [x] #2 Tests use real cached pages as fixtures for the dropped-text cases, and keep TASK-208's p<q tail and raw-text readings and TASK-207's contact-stripping tests green; bounded time on adversarial < input
- [x] #3 A full crawl-cache replay old vs new counts the records whose abstract or title changes, per venue, with examples; every change is classified and anything other than restored <...> text is explained
- [x] #4 A new snapshot and index are built (data/indexes/current not repointed, nothing deleted); the diff vs 2026-10-07-6adb465a519f changes only abstract/title text; the coverage gate passes; the Trust-Evals query is compared on both indexes and any id difference is explained
- [x] #5 Spec 01, the html.py docstring and a docs/results write-up describe the rule and the measured impact
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Escape every < that would open a tag but doesn't start a real one (html.escape_bare_lt) before each parse (parse, text_of, metas): a real start tag has an HTML/SVG/MathML element name (or custom/namespaced), parses up to > with no < outside quotes (atomic, linear), and has an attribute value or only HTML attribute names; real end tags have such a name. Measure by replaying the whole cache old vs new on 3.12.9 and 3.12.15, classify every change, then build a snapshot and index from a frozen tree (origin/dev + html.py) and diff, coverage, Trust-Evals.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Replay (55,359 cached files, 168,181 records): 41 records change, abstract only (34 NeurIPS, 7 ICML); 35 restore <...> text, 6 PMLR (2021-2024) also drop page chrome (Cite this Paper/BibTeX) the unclosed bogus element had pulled into the abstract. New code byte-identical on 3.12.9 and 3.12.15. Snapshot 2026-10-07-1ed899dc6f56 / index 3637c41e0951 (current left at 4646c7547fe7): diff vs 6adb465a519f changed 26 (abstract only), provenance-only 15, nothing else; coverage --check PASS (71/72, ICLR 2013 accepted exception; run by the maintainer: the worktree guard refuses command lines with the word eval); Trust-Evals 101 ids identical. Evidence: docs/results/2026-10-07-bare-lt.md.
<!-- SECTION:NOTES:END -->
