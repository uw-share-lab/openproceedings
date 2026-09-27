---
id: decision-013
title: >-
  Crawl every venue from 2013, ICLR's first year, where the source has it
  (TASK-049)
date: '2026-09-27 20:15'
status: accepted
---
## Context

Spec 00 open question 3 (M4): how far back does the crawl go? The Trust-Evals review searches
2020–2026, and the proposal was to crawl from 2018 (thought to be ICLR's first year on OpenReview) and
let `year:` in the query narrow it. Options: (a) 2020, the review's own window; (b) 2018; (c) 2013, the
year ICLR was first held, so all three venues start from the same year; (d) every year each source has
(NeurIPS proceedings go back to 1987).

A narrower crawl makes a search silently incomplete for anyone whose review starts earlier, and a
year limit belongs in the query (guarantee 3), not in the corpus. Going back to 1987 would add a
quarter-century of NeurIPS alone, with no ICLR and a different ICML source, which makes cross-venue
counts incomparable. 2013 is the first year all three venues exist.

Live checks (2026-09-27, `docs/research/2026-09-27-openreview-and-proceedings-facts.md`) showed that
ICLR is on OpenReview from 2013, not 2018: API v1 holds ICLR 2013, 2014 and 2016–2023 and v2 holds
2024+; but 2015 has no OpenReview group, 2014's notes carry no decisions, and 2016 has only its workshop
track. NeurIPS proceedings cover every year; OpenReview covers NeurIPS main from 2021. PMLR has every
ICML from 2013 (v28) to 2025 (v267).

## Decision

The owner decided (2026-09-27): we crawl every venue from 2013 wherever a spec 01 source holds the
venue-year (ICLR from OpenReview; NeurIPS from its proceedings and OpenReview; ICML from PMLR and
OpenReview) and leave the year range to the query's `year:` filter.

## Consequences

- Spec 01 §Sources gives each source's year range from 2013; the crawl window is 2013 to the current year.
- ICLR 2015, the ICLR 2016 conference track and ICLR 2014's acceptance have no spec 01 source: they are
  coverage gaps, shown on the coverage page, until a source (iclr.cc's accepted-paper lists, or
  `proceedings.iclr.cc` if it covers the years) is added by a spec change (TASK-092). ICLR 2014 papers
  are indexed with `status:unknown`, which the default filter excludes and counts.
- Older ICLR years (2013, 2014, 2016, 2017) use v1 schemas the M4 v1 adapters must handle; the v1
  adapter task (TASK-051) now covers ICLR 2013–2023, and ICML 2013–2019 comes from PMLR through the
  volume table (TASK-053).
- No default year filter is added: the canonical string and `canonical_hash` are unchanged. The
  snapshot grows by the 2013–2017 years (PMLR v28–v70 alone hold 1,619 ICML papers; NeurIPS 2013 has
  360), well inside the 80k-record scale spec 03 benchmarks against.
- Years before 2013 stay out; revisit only with a spec change and a reason from a review that needs them.

