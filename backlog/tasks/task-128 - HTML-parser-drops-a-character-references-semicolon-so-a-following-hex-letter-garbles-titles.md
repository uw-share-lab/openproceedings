---
id: TASK-128
title: >-
  HTML parser drops a character reference's semicolon, so a following hex letter
  garbles titles
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:17'
updated_date: '2026-09-29 23:43'
labels:
  - ingest
  - bug
dependencies: []
ordinal: 112000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
html.py's handle_charref (both parsers) re-emits a numeric character reference as '&#<name>' without its ';'. unescape then reads following hex-digit letters as part of the code: 'A &#x27;Catch' decodes to 'A ⟊tch', 'Fr&#233;chet'-style titles can garble too. Found by TASK-072's real-data check (2026-09-29): 2 of the 6 NeurIPS papers it marked unlisted were proceedings titles garbled this way (r8UWp9JeJi 'Attention Sinks: A \'Catch…', Sg3aCpWUQP 'Errors-in-variables Fr\'echet…'), so they failed to merge with their OpenReview notes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both HTML parsers re-emit a numeric character reference with its terminating ';' (decimal and hex), so text after it is never absorbed into the code point
- [x] #2 Unit tests pin hex and decimal references followed by hex-digit letters and digits, in text and in attributes, for both parsers; the double-escape (unescape) behaviour is unchanged
- [x] #3 On the real 2026-09-29 cache, the replayed proceedings titles no longer contain garbled code points; the count of changed titles per source is listed and each sampled change is correct
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fix: `html.py` `_reference()` re-emits every reference HTMLParser reports whole, with its `;` (`&#x27;`, `&rsquo;`), in both `_TreeParser` and `_TextParser`. Probed on CPython 3.12.9: `&#x27;` -> `handle_charref("x27")`, `&#39;` -> `"39"`, `&rsquo;` -> `handle_entityref("rsquo")`, the `;` consumed in each; a reference with no `;` is never reported because `_BARE_AMP` escapes it first (so `;` is always what the page had). Named refs were broken too: HTML5-only names lost their decode (`&rsquo;s` -> `&rsquos`, `&mdash;a` -> `&mdasha`) and `&notin;x` decoded as `¬inx` via the legacy `&not` prefix; legacy names (`&amp;Catch`, `&eacute;chet`) happened to work and still do. An unknown `&foo;` now stays `&foo;` as written. Attribute values (tree attributes, `attrs`, `metas`) are decoded by HTMLParser itself and never had the bug; pinned by a test. `metas`' full second `html.unescape` differs from a complete-entity-only second pass on 0 cached values.

Tests: `test_html.py::test_both_parsers_re_emit_each_reference_whole` (25 rows through `text_of` and `parse`+`node_text`: hex/decimal followed by hex letters, digits, end of text, back to back; legacy and HTML5-only named refs followed by letters; double escapes; `R&D`, `&R&D`, semicolon-less refs), 9 rows fail on the old handlers; plus the attribute test. No recorded fixture or golden changed (fixtures hold only `&nbsp;`/`&times;`/`&copy;`/`&amp;`, all legacy names). Full backend suite 5281 passed, 2 skipped; `make lint`, `make tooling` green.

Real data (2026-09-29 cache, read-only; old vs new handlers, scratch `task128/diff_refs.py`): iclr_archive 146 records, 0 changed; pmlr 14,281, 0 changed; neurips_proceedings 26,019, 11 changed: 3 titles (`Replica-Exchange Nos\ɾ-Hoover` -> `Nos\'e-Hoover` (2020), `Errors-in-variables Fr\⟬het` -> `Fr\'echet` (2023), `Attention Sinks: A ⟊tch, Tag, Release'` -> `A 'Catch, Tag, Release'` (2025)); each of the three also gained its abstract and page authors, since its garbled listing title had failed the `citation_title` match; and 8 abstracts with `&mdash`/`&ndash` fixed (e.g. `Fisher information&mdasha` -> `Fisher information—a`, `Weisfeilern&ndashLeman` -> `Weisfeilern–Leman`). Every `&` left in new titles/abstracts (4 titles, 23 abstracts) is a real bare ampersand (`See&Trek`, `GNN&GBDT`, `SF&GPI`).

Snapshot check (scratch, same HEAD, old handlers vs new): records 95,940 -> 95,938 (the 2023 and 2025 proceedings-only duplicates now merge into Sg3aCpWUQP and r8UWp9JeJi); NeurIPS 2023 main 3,219 -> 3,218 and 2025 main 5,287 -> 5,286 (both now exactly official); missing abstracts 574 -> 571; `op eval coverage` gate unchanged at 43/44 (the one failing cell is ICLR 2013 main, unrelated).
<!-- SECTION:NOTES:END -->
