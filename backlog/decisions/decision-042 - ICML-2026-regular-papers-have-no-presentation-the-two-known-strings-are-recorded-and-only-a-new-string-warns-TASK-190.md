---
id: decision-042
title: >-
  ICML 2026 regular papers have no presentation; the two known strings are
  recorded and only a new string warns (TASK-190)
date: '2026-10-05 23:54'
status: accepted
---
## Context

ICML 2026's accepted OpenReview notes carry the venue strings `ICML 2026 regular` (5,805) and `ICML 2026
Position Paper Track regular` (175). Nothing ICML has published says a regular paper was a poster, so TASK-178
left them unmapped, and every ICML 2026 crawl warns `presentation_unmapped` 5,980 times. That standing warning
would hide a genuinely new string. The owner's interim choice (2026-10-05) was to leave them blank (TASK-190).

Options: map them to `poster`, which needs evidence from ICML; or keep the presentation blank and record the two
strings as known, so the warning names only strings nobody has seen.

## Decision

The project owner chose (2026-10-05) the second. The two strings are recorded as known with no presentation;
`presentation_unmapped` warns only for a string that is neither mapped nor known.

## Consequences

- ICML 2026 regular papers have no presentation in records, filters and exports.
- An ICML 2026 crawl reports no `presentation_unmapped` warning for these 5,980 papers, and still warns on any
  new venue string.
- If ICML says what "regular" means, the mapping can be added and this decision revisited.

