---
name: default-filters
description: The default-filter rule (guarantee 3) — `track:(main OR datasets_benchmarks OR position)` and `status:accepted` are added when a query has no track:/status: clause, always made explicit in the canonical string, edited by the UI toggles as the same clauses, and accounted for in `excluded` (PRISMA "removed before screening"). Use when touching default-filter insertion, canonical filter rendering, the filter toggles, exclusion accounting, or any report of removed records.
---

# Default filters (spec 02 §Fields and filters, spec 03 §Exclusion accounting)

## The rule
| Clause absent from the query | Parser adds |
|---|---|
| no `track:` anywhere | `track:(main OR datasets_benchmarks OR position)` |
| no `status:` anywhere | `status:accepted` |

- Added clauses are ANDed at the top level and **made explicit in `canonical`**. The saved string shows them.
  A default that is applied but missing from the canonical string is a guarantee-3 violation. The
  `exactness-guardian` treats it as a Must.
- "Absent" means no clause of that field **anywhere** in the AST. A user who writes
  `(track:workshop AND x) OR y` has opted out of the track default for the whole query, and the `y` branch
  is then unfiltered by track. The spec doesn't settle whether this needs a warning. Record the decision,
  and pin the behaviour with a golden case.
- The default value set comes from the 01 track taxonomy. `workshop` and `competition` are excluded by
  default. NeurIPS Datasets & Benchmarks is main-line content and stays in (`datasets_benchmarks`).
- Idempotence: parsing a canonical string that already contains the defaults adds nothing. The clauses are
  present, so no default fires.

## UI toggles are the same clauses
The frontend "include workshops" and "include rejected" toggles **edit the query's `track:`/`status:`
clauses** (through the AST round-trip). They are not separate state. `/search?q=` must fully describe the
result set. If a toggle and the string can disagree, that is a bug.

## Exclusion accounting (guarantee 6)
For every search, the engine also evaluates the query **with the default clauses removed** and reports how
the difference breaks down:
```json
"excluded": {"track": {"workshop": 212, "competition": 4}, "status": {"rejected": 88}}
```
- Only defaults that were **added** are accounted. A clause the user wrote is their filter, not an automated
  exclusion.
- A record can fail both defaults (a rejected workshop paper). **Decided in spec 03 §Exclusion
  accounting:** buckets are assigned in a fixed order, track first and then status, so that paper counts
  once, under `track.workshop`. The buckets always add up to `excluded.total = |unfiltered| − |filtered|`,
  the single number PRISMA needs. Reporting rules: `.claude/skills/prisma-reporting/SKILL.md`.
- The counts must come from the same engine and `index_version` as the result set. The oracle computes them
  too, and the differential suite compares both.
- Budget: `match_ids` with exclusion accounting takes < 300 ms p95 (spec 03).

## Worked example
Input `trust AND calibration` →
canonical (illustrative ordering) `((trust AND calibration) AND status:accepted AND track:(datasets_benchmarks OR main OR position))`.
Input `trust AND track:workshop` → only `status:accepted` is added. `excluded.track` is absent, because the
user chose the track.

## Gotchas
- Filters never score (`.claude/skills/field-weighted-bm25/SKILL.md`).
- An unknown `track:` value is an error listing the valid values. It never matches nothing silently.
- The ICLR `status:rejected`/`withdrawn` records exist only if M4 indexes them (00 open question 2). Until
  then, `excluded.status` may be empty. Report that honestly, never as a hard-coded zero.
