---
id: TASK-128
title: >-
  HTML parser drops a character reference's semicolon, so a following hex letter
  garbles titles
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 23:17'
updated_date: '2026-09-29 23:17'
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
- [ ] #1 Both HTML parsers re-emit a numeric character reference with its terminating ';' (decimal and hex), so text after it is never absorbed into the code point
- [ ] #2 Unit tests pin hex and decimal references followed by hex-digit letters and digits, in text and in attributes, for both parsers; the double-escape (unescape) behaviour is unchanged
- [ ] #3 On the real 2026-09-29 cache, the replayed proceedings titles no longer contain garbled code points; the count of changed titles per source is listed and each sampled change is correct
<!-- AC:END -->
