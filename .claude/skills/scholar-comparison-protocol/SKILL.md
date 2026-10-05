---
name: scholar-comparison-protocol
description: The spec 07 §B protocol for comparing openproceedings with Google Scholar on the Trust-Evals strings — inputs (clean.ris plus the 2020–2024 delta), scoping to the same venues and years, matching by the 01 merge rules, the disagreement classification table, which classes are automated and how, the review.csv shape for human calls, and the report format. Use when running or reviewing `op eval scholar`, classifying a disagreement, or citing the comparison in the paper.
---

# Scholar comparison protocol (spec 07 §B)

## Inputs and scope
- **Queries:** the review's strings, starting with **Most Updated**, in `mode=scholar` exactly as written
  (translations recorded), then the native canonical form.
- **Scholar set:** the Trust-Evals `clean.ris` plus the 2020–2024 delta — a fixed, dated export. Record
  its file hash in the report; never re-scrape Scholar mid-analysis. As run (2026-10-04): scholarmend's
  `mended.ris` of that export, the same 1,834 records with real years (`clean.ris` has none on 99 records and
  Scholar's guess, 2026, on 1,059); `docs/results/scholar-comparison-notes.md` says so in the report.
- **Scope both sides identically:** venues NeurIPS/ICLR/ICML, the same years. Scholar records outside the
  scope are dropped *before* comparing and counted in the report.
- **Index:** one pinned `index_version`, stated in the report and in every row.

## Matching papers across the two sets (01 merge rules)
1. Identical OpenReview forum ID (from Scholar's URL when present: `/forum?id=` or `/pdf?id=`), then the
   proceedings paper a URL names. A proceedings id counts **within its venue and year** only: a NeurIPS hash
   repeats every year (matching on the bare `nips-<hash>` made 316 of 1,834 records ambiguous).
2. Else normalized title (`token-contract` normalization, `dedup.title_key`) **with the same venue and year**.
Never match on title alone across venue or year; a Scholar record with no year is matched only by forum
ID, or goes to `review.csv`. The venue is one of Scholar mode's source names exactly; a string Scholar cut
(`… Information Processing …`) is no venue. Code: `eval/scholar_compare.py` (`MatchIndex.match`), the one
implementation, which a reviewer's own RIS file goes through too (TASK-177).

## Classification
| Only in Scholar, because… | Automated test |
|---|---|
| `filtered` — workshop / competition / rejected / withdrawn | Paper is in the corpus; `track`/`status` fails the default filters; re-running with defaults removed matches it, as run, as Scholar reads the string, or with inflected forms (the evidence says which: `also compat_reading`, `also stemming`). Counted in `excluded`. |
| `compat_reading` | The difference comes from how Scholar mode read the string, not from the corpus: decision-002's phrase reading of unquoted multi-word `\|` items (Scholar ORs only neighbouring words), or `$` read as the WoS zero-or-one wildcard (Scholar has no documented `$`). Re-run with the Scholar reading written natively; it now matches. |
| `stemming` | Passes the filters; re-run the query with the inflected variants added (e.g. `benchmarks`, `trusted`; inflection only, so not `trustworthy` for `trust`); it now matches. Record the variants that decide it. |
| `coverage_gap` — not in the corpus | No match by forum ID or title+venue+year in the snapshot. Fix in 01; cross-check with the coverage report. |
| `full_text` | In the corpus with an abstract, and `ReferenceEngine` confirms neither the query, Scholar's reading of it, nor any inflected variant matches title+abstract. Residual class, so needs the oracle check. It says nothing about the filters: a `full_text` record may fail them too (its evidence says `also fails the filters`, and the report counts them). |
| `our_bug` | `ReferenceEngine` matches but the served result doesn't, or a normalization/parsing defect explains it. **Must be 0**; each one is a Must-fix with a golden case. |

| Only in openproceedings, because… | Automated test |
|---|---|
| `scholar_cap` | Scholar's result count for the string hit its 1,000-result cap, or the record was truncated. |
| `compat_reading` | Scholar mode read the string differently from Scholar (decision-002 phrases, `$` as a WoS wildcard) and that reading matches the record; re-running with Scholar's reading written natively doesn't. |
| `scholar_missed` | Otherwise. Goes to `review.csv` to confirm the exact token really is in title/abstract. |

**Order matters:** test `our_bug` (oracle vs engine) first, then `filtered`, `compat_reading`, `coverage_gap`, `stemming`,
and only then `full_text`. Assigning `full_text` without the oracle check hides bugs. The filters are judged
before the text: a record that fails them and matches under any reading is `filtered`; one that fails them and
matches under none is `full_text` (Scholar found it in the full text, and the filters would also have removed it).

## What a match rests on (provenance)
An index built with an imported RIS set holds that set's records as `ris`-only records. Comparing the same set
with that index matches those records to themselves: such a match shows nothing about coverage, the text the
classes are judged on is the import's own, and in a venue-year with no crawled record nothing can be only in
openproceedings. On index `05a0541717f6`, 530 of the 1,807 matched papers were RIS-only (ICLR 2026 415, ICML
2026 111, ICLR 2025 3, ICLR 2024 1), and no 2026 record was crawled. So every row carries whether its record has
an independent source (`Row.independent`; `record_source` in `review.csv`) and its abstract's source, and the
report gives each count for crawled and RIS-only records apart, with a per-venue-year table. A RIS-only match
whose title another index record shares is `unsettled` (one paper under two ids, or a wrong mended venue or year).
Never quote a matched or `full_text` figure without the split.

## review.csv (next to the report)
Columns: `query_name, side, scholar_key, op_id, title, venue, year, auto_class, auto_evidence,
human_class, reviewer_role, note`. One row per disagreement the automation couldn't settle, plus a random
10% of automated rows as a spot check. A person fills `human_class`; the analyst never does. Roles, not
names.

As built: the file is `docs/results/<YYYY-MM-DD>-scholar-comparison-review.csv`, with two more columns,
`row_kind` (`unresolved` or `spot_check`) and `index_version`. Unresolved rows are every `unsettled` row (an
ambiguous or undated match; a record the corpus holds without an abstract, which can't be called `full_text`),
every `coverage_gap` (a gap and a record Scholar filed under the wrong venue look alike), every
`scholar_missed` and every `our_bug`. The spot check is the tenth of each query's settled rows whose sha256 of
(query name, side, ids) sorts first: fixed for a run, unrelated to any field. `op eval scholar` refuses to
replace a review file in which a person has filled anything. Two further columns, `record_source` (`crawled` or
`ris_only`) and `abstract_source`, say what the row's index record rests on.

## Report — `docs/results/<YYYY-MM-DD>-scholar-comparison.md`
Header: date, `index_version`, `tokenizer_version`, Scholar export hash, queries run. Per query: sizes
(Scholar in scope, openproceedings `total`, both), the two classification tables with counts and
percentages, `our_bug` count (must be 0), and the unresolved `review.csv` count. Close with the paper
finding: *share of Scholar's set explained by full-text matches and by stemming*. Numbers come only from
the run; state the command, with file names only, never paths (`op eval scholar --ris mended.ris --name
main-7-most-updated --years 2020..2026 --index <v>`). `--years` and `--venues` are part of the result: another
range gives other numbers, so always state them.

## Gotchas
- Scholar titles are truncated or lower-cased; normalize before matching but keep the raw title in the CSV.
- `source:PMLR` translates to `venue:ICML` with a warning — PMLR also hosts other venues; note it.
- A paper can be both `filtered` and `stemming`; record the first class in the order above (`filtered`) and the
  other in `auto_evidence` (`also stemming (matches with …)`).
- A record with a year but a venue string that is no venue (Scholar cut it) is out of scope, unless an in-scope
  index record has its title: then it is in scope and `unsettled`, with that record named. The papers in scope
  are the denominator of every percentage of the Scholar set, and the report states it.
- A forum id and a proceedings id on one Scholar record that name different index records are ambiguous.
- The `stemming` test is inflection only (`scholar_compare.inflection_stem`: `s`/`es`/`ies`, `ed`, `ing`), a
  stated stand-in for Scholar's undocumented stemmer. A plural acronym needs no vowel in its stem (`llms` →
  `llm`): the first version required one and missed the commonest variant in the corpus. Which stemmer stands
  for Scholar's is an open decision for the project owner; don't adopt another one in passing. `full_text` is
  **not** a lower bound: a wider stemmer moves rows out of it. The report gives a sensitivity figure instead,
  how many `full_text` rows a prefix reading of every word (`word*`) would match.
- Notes about one export (`--notes`) are never a default: another set would be printed with the wrong notes.
  `--answers <name>` says which string the set is Scholar's answer to, and the report marks the others.
- The Scholar set answers one string (`main-7-most-updated`: one export per `source:` value). Running another
  string against it shows what that string keeps, drops and adds, not what Scholar returned for it.
