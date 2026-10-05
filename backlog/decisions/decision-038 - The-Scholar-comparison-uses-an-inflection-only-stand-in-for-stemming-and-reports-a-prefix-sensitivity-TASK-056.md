---
id: decision-038
title: >-
  The Scholar comparison uses an inflection-only stand-in for stemming and
  reports a prefix sensitivity (TASK-056)
date: '2026-10-05 07:20'
status: accepted
---
## Context

The Scholar comparison (spec 07 §B, TASK-056) separates Scholar-only papers that match a string through a
word form (`stemming`) from those that match nowhere in title or abstract (`full_text`). Google Scholar
stems query words, but its stemmer is not documented, so no rule can be called Scholar's. The report needs
some rule to draw the line. Two options were considered:

1. **An inflection-only stand-in**, written in the repo (`eval/scholar_compare.inflection_stem`): plural or
   third-person `s`/`es`/`ies`, `ed`, `ing`, with a doubled consonant undoubled and a final `e` dropped. No
   derivation (`trustworthy` is not a form of `trust`). It over-pairs in places (`suite` with `suit`).
2. **A published stemmer** (Porter or Snowball), which also strips derivational endings. It would add a
   dependency (a lockfile change), and it is no more Scholar's stemmer than option 1 is.

The first review of TASK-056 showed that a wider stemmer moves rows out of `full_text`, so the choice could
matter. The report therefore measures it: every searched word is replaced by its inflection stem read as a
prefix (`benchmarks` → `benchmark*`), and the `full_text` rows that then match are counted. On index
`5ec5231adae2` (`docs/results/2026-10-05-scholar-comparison.md`) that moves 0 of 1,753 `full_text` rows for
`main-7-most-updated`, 0 of 1,753 for `main-7-dollar` and 2 of 1,709 for `main-2-pop`. (That run was superseded the same day
by the one on index `fd13d8d27535`, where the figures are 0 of 1,752, 0 of 1,752 and 2 of 1,708.) The prefix reading is not
a stemmer either: it covers stripped and added endings on the inflection stem, not a stemmer that rewrites
the stem. The project owner delegated the choice to the session lead on 2026-10-05.

## Decision

The Scholar comparison keeps the inflection-only stand-in and adopts no published stemmer. Every report
prints the prefix-sensitivity figure for each string beside its `full_text` count.

## Consequences

- The stand-in is not Google Scholar's stemmer. `stemming` and `full_text` counts are relative to it, and
  every report says so in its Method text and beside each finding (`eval/scholar_report.py`).
- No stemmer dependency is added: on the review's strings the measured sensitivity is zero or two rows, so a
  wider stemmer would not change the result.
- `full_text` is not a lower bound, and is never called one. The sensitivity figure is the stated check.
- Revisit this decision when a string's prefix sensitivity is not near zero, or if Google documents its
  stemming: the rule would then be replaced and the reports regenerated.
- Cited in spec 07 §B (`docs/specs/07-evaluation.md`) and the `scholar-comparison-protocol` skill. Changing
  `inflection_stem` changes the classes of past reports, so it needs a new decision and regenerated reports.
