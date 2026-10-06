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
2. Else a DOI (TASK-186: Scopus and Web of Science exports, `DO`; a doi.org link too; case-blind) that an index
   record's `urls.doi` holds, **only in the venue and year the file states** (where it states them; a WoS venue
   string with its volume is no venue and doesn't block). A DOI in another venue or year is never a match and is
   named in the row. Only accepted NeurIPS 2022–2025 proceedings records carry a DOI (16,690 on `fd13d8d27535`, spec 07 §B says how counted); ICLR and
   ICML have none. A comparison rule only: dedup doesn't merge on DOIs.
3. Else normalized title (`token-contract` normalization, `dedup.title_key`) **with the same venue and year**.
Never match on title alone across venue or year; a Scholar record with no year is matched only by forum
ID, or goes to `review.csv`. The venue is one of Scholar mode's source names exactly; a string Scholar cut
(`… Information Processing …`) is no venue. Code: `eval/scholar_compare.py` (`MatchIndex.match`), the one
implementation, which a reviewer's own RIS file goes through too (TASK-177).

## A reviewer's own file (TASK-177)
The same core answers `POST /compare` (spec 04 §Comparing with a RIS file) and the web app's "Compare with your
records": one query, one RIS file, `Scope()` (every indexed venue and year: a limit is written in the query),
no report and no `review.csv`. The API's `reason` is the class below and `detail` its evidence; `matched_by`
is `Match.rule` or `Match.problem`; `independent` is `Row.independent`. `kept` + `added` is exactly `/search`'s
result. Evidence is echoed to the uploader there, so what it quotes of a file is bounded: a `coverage_gap`
row names its links' hosts as valid host names only (`link_host`: DNS labels, at most 253 characters, no
credentials or control characters), at most three a record (`MAX_HOSTS`), and a malformed link names nothing.
A change to the classes, the rules or their order changes both the report and the endpoint
(`backend/tests/contract/test_compare.py` compares the route's rows with `compare_query`'s).

## Classification
| Only in Scholar, because… | Automated test |
|---|---|
| `query_limit` — the string's own limit excludes it | A top-level filter clause the string writes (`year:`, `source:`/`venue:`, their `NOT`, or a non-default `track:`/`status:`) fails the record (`query_limits`). Whatever its text: never `full_text` or `stemming`. Evidence names the clause, the failing value, and whether the rest of the string matches. A record the index doesn't hold (`not_found`) is judged on the file's venue and year and goes to a person. A clause under an OR or NOT group is part of the search. |
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

**Order matters:** test `our_bug` (oracle vs engine) first, then `query_limit`, `filtered`, `compat_reading`, `coverage_gap`, `stemming`,
and only then `full_text`. Assigning `full_text` without the oracle check hides bugs. The filters are judged
before the text: a record that fails them and matches under any reading is `filtered`; one that fails them and
matches under none is `full_text` (Scholar found it in the full text, and the filters would also have removed it).

## What a match rests on (provenance)
An index built with an imported RIS set holds that set's records as `ris`-only records. Comparing the same set
with that index matches those records to themselves: such a match shows nothing about coverage, the text the
classes are judged on is the import's own, and in a venue-year with no crawled record nothing can be only in
openproceedings. On index `05a0541717f6`, 530 of the 1,807 matched papers were RIS-only (ICLR 2026 415, ICML
2026 111, ICLR 2025 3, ICLR 2024 1), and no 2026 record was crawled. After the 2026 crawl (index `5ec5231adae2`,
TASK-178) 7 remained, each an unmerged second copy of a crawled paper; TASK-179 merged them, and on index
`fd13d8d27535` no match is RIS-only. So every row carries whether its record has
an independent source (`Row.independent`; `record_source` in `review.csv`) and its abstract's source, and the
report gives each count for crawled and RIS-only records apart, with a per-venue-year table. A RIS-only match
whose title another index record shares is `unsettled` (one paper under two ids, or a wrong mended venue or year).
Never quote a matched or `full_text` figure without the split.

## review.csv (next to the report)
Columns: `query_name, side, scholar_key, op_id, title, venue, year, auto_class, auto_evidence,
human_class, reviewer_role, note`. One row per disagreement the automation couldn't settle, plus a random
10% of automated rows as a spot check. The tool never fills `human_class`; whoever makes a call writes it with
their role in `reviewer_role`. Roles, not names. A call weighs what its role does (below).

As built: the file is `docs/results/<YYYY-MM-DD>-scholar-comparison-review.csv`, with two more columns,
`row_kind` (`unresolved` or `spot_check`) and `index_version`. Unresolved rows are every `unsettled` row (an
ambiguous or undated match; a record the corpus holds without an abstract, which can't be called `full_text`),
every `coverage_gap` (a gap and a record Scholar filed under the wrong venue look alike), every
`scholar_missed` and every `our_bug`. The spot check is the tenth of each query's settled rows whose sha256 of
(query name, side, ids) sorts first: fixed for a run, unrelated to any field. `op eval scholar` refuses to
replace a review file in which anything is filled in (or which is not UTF-8). Two further columns,
`record_source` (`crawled` or `ris_only`) and `abstract_source`, say what the row's index record rests on, and
the last, `row_number` (1, 2, …), is each row's place, to sort a reordered file back by. The
file is UTF-8 with a BOM and CRLF line ends, like `/compare`'s CSV, so a spreadsheet opens it as UTF-8; cells
are written through `export.csv_cell` (a value starting `=`, `+`, `-` or `@` gets a leading `'`).

**Filling it in, and reading it back.** Whoever makes a call fills three columns and nothing else:
`human_class`, one of `our_bug`, `query_limit`, `filtered`, `compat_reading`, `coverage_gap`, `stemming`, `full_text`,
`scholar_cap`, `scholar_missed`, `in_both` (the record is the same paper as one in the result) or
`out_of_scope` (it is no paper of the scope's venues and years: Scholar's venue or year is wrong); both verdicts
go on Scholar-side rows only. `reviewer_role`, a role, never a name, required with a class; and `note`, free
text. `unsettled` is not a call. Save as "CSV UTF-8" (another encoding is refused with that fix). Then run the
same `op eval scholar` command again (same inputs, `--index`, `--date`, `--out`): it checks that the file's rows
are exactly the rows the run writes (naming the first line and column a spreadsheet changed), keys each call by
its row's place among the run's rows (never by a cell the guard or a spreadsheet may have rewritten), leaves the
file byte for byte, and rewrites only the report. Its "Human calls" section counts the calls per query
(unresolved rows called, spot-check rows called and how many agree with the automated class, or "none called"),
automated × called class, names any row called `our_bug`, prints an "After the calls" table per query, and ends
with **Every disagreement classified: yes/no**. "Yes" needs no `our_bug` by the automation or a call and a call
on every unresolved row. `--check` exits 1 on an automated `our_bug` and on a call of `our_bug`. A malformed
call, or a filled file whose rows belong to another run, is refused and nothing is written; so is a file a
spreadsheet sorted ("its rows were reordered": sort it by `row_number` and save again). The report never quotes
a note.

**After the calls.** A class moves its row to that class. `out_of_scope` takes the record out of the Scholar set
and so out of the denominator. `in_both` moves the record to "in both" and pairs it with one index record: the
one same-title record its evidence names (`Row.near`: for a record with no venue
string, the in-scope records of its year named after "same title:"), which must be one of that query's rows only
in the result: it leaves that table, the two being one paper. An `in_both` call is refused when its row names
none or several, when the paired record is not among the query's rows only in the result (so a row with an
`op_id` of its own is refused: `in_both` is for a row with no index record), when another `in_both` call pairs the same record, or when that record's own row has a call: no paper
is counted in both twice. The pairing never parses `note`. Rows without a call keep the automation's class. Every table above
the Human calls section, and the first figures of each Finding, are the automation's alone; the Finding adds an
"After the calls" bullet with the roles beside it.

**A call weighs what its role does.** The report prints each distinct `reviewer_role` with its row count in the
Human calls section and on the closing line, and the command prints them on its verdict line. The tool does not
judge a role. A call by anyone but an independent reviewer (the analyst, or an AI assistant acting for the
project) leaves "yes" provisional and spec 07 §B's bar open: a paper cites the automation's figures; the
after-calls figures are not to be cited until every role is an independent reviewer's (the Finding's bullet says
so), and then with the roles beside them. The 2026-10-05 review file's 48 calls were made by an AI assistant
at the owner's direction; TASK-193 (an independent reviewer repeats them, reading each `scholar_missed` abstract
first) blocks citing them, not merging.

## Report — `docs/results/<YYYY-MM-DD>-scholar-comparison.md`
Header: date, `index_version`, `tokenizer_version`, Scholar export hash, queries run. Per query: sizes
(Scholar in scope, openproceedings `total`, both), the two classification tables with counts and
percentages, `our_bug` count (must be 0), and the `review.csv` counts (rows left for a call, called). Under the
only-in-openproceedings table of a string with `$`, a caveat: a `compat_reading` row decided by `$` matches only
through a plural, the forms `stemming` credits Scholar with, so it is no evidence Scholar would not return the
paper; and, when the string has a `scholar_missed` row, `scholar_missed` counts exact matches only, a floor. Close with the paper
finding: *share of Scholar's set explained by full-text matches and by stemming*. Numbers come only from
the run; state the command, with file names only, never paths (`op eval scholar --ris mended.ris --name
main-7-most-updated --years 2020..2026 --index <v>`). `--years` and `--venues` are part of the result: another
range gives other numbers, so always state them.

## Gotchas
- Scholar titles are truncated or lower-cased; normalize before matching but keep the raw title in the CSV.
- `source:PMLR` translates to `venue:ICML` with a warning — PMLR also hosts other venues; note it.
- A paper can be both `filtered` and `stemming`; record the first class in the order above (`filtered`) and the
  other in `auto_evidence` (`also stemming (matches with …)`).
- A record whose venue string is no venue is out of scope. One exception: the string is empty or cut by Scholar
  (`…`) and an in-scope index record of the same year has its title: then it is in scope and `unsettled`, with
  that record named. A complete name of another venue (AISTATS) keeps the record out, whatever its title. The papers in scope
  are the denominator of every percentage of the Scholar set, and the report states it.
- A forum id and a proceedings id on one Scholar record that name different index records are ambiguous.
- The `stemming` test is inflection only (`scholar_compare.inflection_stem`: `s`/`es`/`ies`, `ed`, `ing`), a
  stated stand-in for Scholar's undocumented stemmer. A plural acronym needs no vowel in its stem (`llms` →
  `llm`): the first version required one and missed the commonest variant in the corpus. Decision-038 keeps
  this stand-in and adopts no published stemmer; don't add one in passing. The `stemming` and `full_text` counts
  are relative to the stand-in, never "what Scholar stems". Revisit the decision if a string's prefix
  sensitivity is not near zero. `full_text` is
  **not** a lower bound: a wider stemmer moves rows out of it. The report gives a sensitivity figure instead,
  how many `full_text` rows match when every word is replaced by its inflection stem read as a prefix
  (`benchmarks` → `benchmark*`): exactly that, not what another stemmer would do.
- Notes about one export (`--notes`) are never a default: another set would be printed with the wrong notes.
  `--answers <name>` says which string the set is Scholar's answer to, and the report marks the others.
- The Scholar set answers one string (`main-7-most-updated`: one export per `source:` value). Running another
  string against it shows what that string keeps, drops and adds, not what Scholar returned for it.
