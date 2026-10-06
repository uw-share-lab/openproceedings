# 07 — Evaluation

Status: **draft for review** · depends on: all parts · owns: the evidence that the guarantees hold

## Purpose

Turn each guarantee in 00 into something that can be checked. Some checks are CI gates (they fail the
build). Others are reports (they're regenerated and committed as dated results, never quoted from memory).

## A. Exactness (CI gates)

| Suite | What | Gate |
|---|---|---|
| Golden tokens | 02's table plus 100 or more normalization cases | 100% pass |
| Golden queries | Query → expected ID set on a hand-built 200-record fixture, with the cases written to be tricky (benchmark/benchmarking, trust/trustworthy, hyphens, LaTeX, phrases that span fields, NEAR ordering) | 100% pass |
| Differential | Hypothesis random ASTs: `TantivyEngine == ReferenceEngine` on the synthetic 5k fixture snapshot plus 20 cap-edge records (5,020, both hash-pinned; decision-004) | 0 counterexamples in 200 examples per PR CI run, 50k nightly |
| Tokenizer parity | Stored text, positions (phrase read-back) and every term's document frequency in the index == `normalize.py`, over the whole corpus (term frequency only as far as the phrases imply) | 0 diffs |
| Semantic invariant (deferred with 06, decision-017; not a v1 gate) | Search results identical with 06 on and off | 0 diffs, once 06 is built |
| Determinism | Same canonical query + `index_version` → identical order and scores | 0 diffs |

As built (task-028): the differential is `backend/tests/differential/`, on a synthetic 5k corpus generated
in memory and hash-pinned (decision-004), with a Zipfian vocabulary: rare terms, hapaxes, and stems that
pass the 200-term cap. Trees are drawn from the corpus's own dictionary. For any tree an engine may get,
all-negative ones included, it compares:
- match sets;
- wildcard expansions, or the refusal;
- disjunctive facets;
- `total` for every sort, and the `year_asc` order;
- for trees that parse, the exclusion counts.

Shrunk counterexamples are kept in `differential-regressions.json` and replayed on every run. The `nightly`
workflow's `differential` job runs 50,000 examples in total: 8 independent runs of 6,250 in parallel, each with
its own seed, not de-duplicated across runs (TASK-057). Wildcard stems include ones at the 200-expansion cap's edge: 20 records added to the corpus the
engines search give `qca*` 199 terms, `qcb*` 200 and `qcc*` 201 (refused), since the 5k corpus's own stems
jump from 117 terms to 278.

## B. Scholar comparison (report, `op eval scholar`)

Replay the review's strings, starting with **Most Updated**, against the index (limited to the same venues
and years). Compare with the Scholar result set, which is the Trust-Evals `clean.ris` plus the 2020–2024
delta. Match papers by the merge rules in 01. Classify every disagreement:

| Only in Scholar, because… | Only in openproceedings, because… |
|---|---|
| outside a limit the string itself writes (`year:`, `source:`/`venue:`, …) | Scholar missed it (known recall gap) |
| matched only in full text | Scholar dropped it because of its 1,000-result cap or truncation |
| matched only through stemming (e.g. `benchmarks`) | |
| workshop / competition / rejected (filtered here, counted in `excluded`) | |
| not in the corpus (a coverage gap: fix 01) | |
| **our bug** (investigate; must be 0) | |

The classification is automatic where possible (for example, re-run the query with the stemmed variants
added, and check the track). The rest goes to `review.csv` for a person to decide. The output is
`docs/results/<date>-scholar-comparison.md`. This report is also a result the paper itself can use:
*how much of Scholar's result set comes from full-text matches and stemming.*

As built (TASK-056): `op eval scholar --ris <file>… --years LO..HI --index <v>` writes the report and, beside it,
`<date>-scholar-comparison-review.csv` (the protocol's `review.csv`, dated like its report). Two modules:
`eval/scholar_compare.py` is the comparison itself, pure functions that a reviewer's own RIS file goes through
too (TASK-177: one implementation); `eval/scholar_report.py` picks the review rows and renders.

- **The Scholar set** is any RIS file, read with scholarmend's parser. The first report reads the review's
  export as scholarmend mended it (`mended.ris`: the same 1,834 records as `clean.ris`, which holds the delta,
  with the years Scholar left out or guessed corrected), and says so under its hash.
- **Matching** follows 01's merge rules in order: the OpenReview forum id a URL names (`/forum?id=` or
  `/pdf?id=`), then the proceedings paper a URL names, then a DOI (below), then the dedup title key within the
  same venue and year. A
  proceedings id is matched **within its venue and year**, as dedup merges on it: a NeurIPS hash is md5 of the
  paper's number and repeats every year. An id or key that names two records is ambiguous, never a pick, and
  so are a forum id and a proceedings id that name different records; a title alone never matches; the venue is
  one of Scholar mode's source names exactly. A venue string that is anything else is no venue, and
  such a record is out of scope unless a URL of it names an indexed paper. One exception: when the string is
  empty or cut by Scholar (`…`) and an in-scope index record of the same year has its title, the record is in
  scope and `unsettled`, for a person, with that record named. A record that names another venue in full stays
  out, whatever its title.
- **DOI** (TASK-186; a comparison rule only: dedup does not merge on a DOI). Scopus and Web of Science exports
  carry a DOI (`DO`) and no link these rules read: a Scopus `UR` is its own record page, and Web of Science
  writes the venue with its volume and edition (`ADVANCES IN NEURAL INFORMATION PROCESSING SYSTEMS 35 (NEURIPS
  2022)`), which is no venue. A DOI (`DO`, WoS's `DI`, or a `doi.org` link; `doi:` and doi.org prefixes dropped,
  compared case-blind, `doi_key`) names the index record whose `urls.doi` it is, **only when the record's year
  is the year the file states and its venue the venue the file states**, each where the file states one (a year;
  one of the three venues by Scholar mode's source names). A DOI that names a record in another venue or year is
  never a match: the record falls to the title rule, and its row names that record (`doi_elsewhere`, "its DOI
  names …, another venue or year: never a match"). A venue string that is no venue does not block a DOI, as it
  doesn't block a forum or proceedings id; that is what lets a Web of Science record match. A DOI two records
  carry, or a DOI and another id naming different records, is ambiguous. **Where the index has DOIs:** only
  NeurIPS proceedings pages give one (`citation_doi`, prefix `10.52202`), so on index `fd13d8d27535` (snapshot
  `2026-10-05-10b5a205a63f`) 16,690 of its 133,629 records carry a DOI: every accepted NeurIPS 2022–2025 main,
  datasets-and-benchmarks and position paper, and nothing else. No ICLR or ICML record, no NeurIPS record before
  2022, and no NeurIPS workshop or rejected record has one, so a Scopus or Web of Science record of those is
  matched by title (Scopus) or not at all (Web of Science, no venue) and lands in `not_compared` or
  `coverage_gap`, as before.
- **Provenance.** An index that an RIS set was imported into holds that set's records, and comparing the set
  with it matches them to themselves. So every match records whether its index record has an independent
  source (a crawl) or only the import (`ris`), and its abstract's source; the report states both counts, a
  table per venue and year beside the crawled records the index holds there, and each class count for the two
  kinds apart. Where the index has no crawled record (2026, on the first report's index `05a0541717f6`) nothing
  can be only in openproceedings, and the report says so. The 2026 crawl (TASK-178, index `5ec5231adae2`,
  and the dedup fix of TASK-179, index `fd13d8d27535`, `docs/results/2026-10-05-scholar-comparison.md`) left no
  RIS-only match, where there had been 530. A RIS-only match whose title another index record shares is
  `unsettled` (one paper under two ids, or a wrong venue or year in the import).
- **Scope** is `--years` and `--venues`, applied to both sides: the result is the engine's match set for the
  string as written, limited to records of those venues and years; a matched Scholar record is scoped by its
  index record's venue and year, an unmatched one by its own.
- **Classes**, in the protocol's order, each decided by `ReferenceEngine` over the compared records (every matched
  Scholar paper and every in-scope match): `our_bug` (the oracle and the served index disagree on a compared
  record, on either side or in both), `query_limit` (below), `filtered`, `compat_reading` (below), `coverage_gap`, `stemming`,
  `full_text`; and `scholar_cap`, `compat_reading`, `scholar_missed` for records only in the result. The filters
  are judged before the text: a record that fails the default filters and matches without them under any
  reading (as run, Scholar's, or with inflected forms) is `filtered`, with the reading in its evidence; one that
  matches under none is `full_text` whether or not it passes the filters, and the report counts the
  `full_text` rows that fail them. A record the
  corpus holds without an abstract can't be `full_text`: it is `unsettled`, for a person. Every `coverage_gap` and
  `scholar_missed` row goes to a person too, with a tenth of the settled rows as a spot check.
- **`query_limit`** (TASK-185): a top-level filter clause the string itself writes excludes the record: a
  `year:` or `source:`/`venue:` clause, its `NOT`, or a `track:`/`status:` clause that is not the default
  (`query_limits`). The string as written leaves the record out whatever its text, so it is no `full_text` or
  `stemming` miss, and the test comes before the filters and the text. The evidence names each failing clause
  as written canonically and the value that fails it (`` `year:2020..2026` (year 2019) ``), says whether the rest
  of the string matches the record as run, and adds `also fails the filters (…)` when a default filter would
  remove it too. A record the index doesn't hold is judged on the file's own venue and year (a `not_found`
  record only; an `unsettled` one stays `unsettled`) and goes to a person, since the file's year may be wrong.
  A clause under an OR or a NOT group is part of the search, not a limit. In `op eval scholar` the limit is the
  string's own, beside `--years`/`--venues`; in `POST /compare`, where both sides cover every indexed venue and
  year, it is the only limit there is.
- **`compat_reading`** (decision-002 and `$`): the string is rewritten as Google Scholar reads it and run again.
  `$` is no wildcard there, and an unquoted multi-word `|` item is separate words with `|` binding tighter than
  juxtaposition, so `(large language model | LLM)` is `large AND language AND (model OR llm)`. A record that
  Scholar's reading matches and ours doesn't, or the reverse, is `compat_reading`, not a miss; the report prints
  Scholar's reading and says so for each such string (`main-2-pop`).
- **`stemming`** adds each searched word's other English inflections found in the compared records (`s`/`es`/
  `ies`, `ed`, `ing`; no derivation). Google Scholar's stemmer is undocumented, so the rule is a stated
  stand-in, not Scholar's rule, and the `stemming` and `full_text` counts are relative to it. Decision-038 keeps
  it and adopts no published stemmer (below). `full_text`
  is not a lower bound: a wider stemmer moves rows out of it. The report therefore gives a sensitivity figure
  per string: how many `full_text` rows would match if every searched word were replaced by its inflection stem
  read as a prefix (`benchmarks` → `benchmark*`). It measures that and no more: it is not a stemmer, and one that
  strips derivational endings could move more rows. On index `fd13d8d27535` it moves 0 of 1,752 `full_text` rows
  for `main-7-most-updated` and 2 of 1,708 for `main-2-pop`, which is why decision-038 adds no stemmer
  dependency; a string whose figure is not near zero reopens the decision.
- **`scholar_cap`** needs the size of each Scholar search: the set's Publish or Perish query dates group its
  records by search, and a group at 1,000 or more marks its venues and years as capped.
- **Any reviewer's own file** (TASK-177): the same comparison is served as `POST /compare` (04 §Comparing with
  a RIS file) and drawn by the web app's "Compare with your records" panel (05 §Components 9): one query
  against one file, every indexed venue and year on both sides (a limit is written in the query), with the
  matching and the classes of this section and no report. `compare_query` takes a `tick` the route raises its
  time limit from; `result_in_scope` and `only_in_result` are the result and the added ids as both callers
  compute them. The route is tested against the core's own rows (`backend/tests/contract/test_compare.py`).
  Since that route echoes a row's evidence to whoever uploaded the file (decision-035), the evidence of a
  record the index doesn't hold names its links' hosts only as valid host names, at most three a record
  (`link_host`, `MAX_HOSTS`), in the report too; a link no URL parser takes names no paper and no host.
- **Calls are read back.** Whoever makes a call fills `human_class` (a protocol class, `in_both` or
  `out_of_scope`), `reviewer_role` (a role, never a name) and `note` in the review file. The same command, run
  again, checks that the file's rows are the run's own (a cell the run wrote that a spreadsheet changed is named
  by line and column), leaves the file untouched and rewrites the report with a "Human calls" section: calls per
  query, spot-check agreement with the automated class ("none called" when no spot-check row has one), any row
  called `our_bug`, the counts after the calls, and the line **Every disagreement classified: yes/no** (no
  `our_bug` by the automation or by a call, and a call on every row left for one). `--check` fails on a call of
  `our_bug` as well as on the automation's. The review file is UTF-8 with a BOM and CRLF line ends, as `/compare`'s
  CSV: what a spreadsheet opens and saves as "CSV UTF-8"; a file saved in another encoding is refused with that
  fix, and is never overwritten. Calls are keyed by a row's place, so a file whose rows a spreadsheet sorted is
  refused as "its rows were reordered" (never misread); its last column, `row_number` (1, 2, …, written and
  checked like every cell the run writes), sorts it back.
- **What a call does to the counts** (the "After the calls" tables, and a bullet under each Finding). A class
  moves its row to that class. `out_of_scope` (Scholar-side rows only) takes the record out of the Scholar set,
  so out of the denominator. `in_both` (Scholar-side rows with no index record of their own) moves the record to
  "in both" and pairs it with the one same-title record its evidence names (`Row.near`, the record named after
  "same title:"), which must be one of that query's rows only in the result: it leaves them, the two being one
  paper. An `in_both` call is refused when the row's evidence names no such record or several, when the record
  it pairs with is not among the query's rows only in the result (so a row with an index record of its own is
  refused: that record is in the index, not in the result), when another `in_both` call already pairs that record, or when the
  record's own row has a call; so no paper is counted in both twice. The pairing never reads `note`. Rows without a call keep the automation's class. The tables above the
  Human calls section, and the Finding's first figures, stay the automation's alone.
- **A call weighs what its role does.** The report prints each distinct `reviewer_role` with its row count beside
  the Human calls figures, on the closing line and on the command's verdict line, and never quotes a note. The
  tool does not judge a role: when any call was made by someone other than an independent reviewer (the
  analyst, or an AI assistant acting for the project), it is recorded like any other, but the "yes" is
  provisional and this section's bar is not closed. A paper cites the automation's figures; the counts after the
  calls are not to be cited until every role is an independent reviewer's (the Finding's after-calls bullet says
  so in these words), and then with the roles beside them. The 2026-10-05 "yes" rests on 48 calls an AI
  assistant made at the owner's direction: TASK-193 (an independent reviewer repeats them) need not block
  merging, but blocks citing the calls and closing this bar.
- A report never replaces a review file in which a call is filled in, and names its inputs by file name and sha256,
  never by path. Notes about one set of inputs come from the file `--notes` names (for the review's export,
  `docs/results/scholar-comparison-notes.md`), printed verbatim under its hash; there is no default, since
  another set would get the wrong notes. `--answers <name>` names the string the set is Scholar's answer to:
  the report then marks every other string's numbers as a comparison against that set only.

## C. Coverage (report plus a soft gate at M4)

For each venue × year × track: indexed accepted count compared with the official accepted count (the table
of sources lives in `docs/results/coverage-sources.md`, each with a citation; `official_counts.py` is its
machine-readable copy, which `GET /coverage` serves, and a test holds the two equal).

**The M4 gate:** every **main-track and D&B cell for which an official accepted count exists** is within
±1%, or an owner-accepted exception (below). Cells with no official count are reported but not gated. The same definition appears in 00 and in the
`coverage-reporting` skill. Also report, per cell: missing-abstract count, `unknown`-track count, and
**statuses indexed**, meaning which statuses the sources for that venue-year can even contain. For example,
NeurIPS 2013–2020 and ICML 2013–2022 come from proceedings only, so no rejected papers exist there to
exclude; NeurIPS and ICML on OpenReview hold only the rejected papers whose authors opted in, while ICLR
holds every rejected, withdrawn and desk-rejected submission (decision-012). The crawl window is 2013 on
(decision-013); any venue-year with no source is a reported gap, never a silent zero. ICLR 2014–2016 are
not gaps: their public archive listings supply accepted main-track records (TASK-096).
The source of statuses indexed is spec 01's source table as `ingest/statuses.py` holds it (spec 01
§Pipeline 5); the snapshot manifest records them per venue-year, and the missing abstracts and sources per
cell (manifest format 2, TASK-082).
The methods text cites the coverage report (with its snapshot hash) as the database-scope caveat.
`GET /coverage` serves every column per cell (`venue_years[].tracks`: sources, indexed accepted,
`official_accepted` with its citation, `delta`, `delta_pct`, `gated`, `within_gate`, missing abstracts) and
the statuses indexed per venue-year; `/coverage` in the UI renders the same data. A takedown (TASK-136,
decision-022) adds `abstract_withheld` beside the missing abstracts, which then leave the withheld ones out;
the served `/coverage` also counts ids the takedown list names since the snapshot was built, while the report
(`op eval coverage`) keeps the snapshot's own counts and says under its totals how many it withheld: the report
is the citable figure.
As built (TASK-054): `op eval coverage` renders `docs/results/<date>-coverage.md` from that same computation
(`api.coverage.compute` on the index, `eval/coverage_report.py`). It adds the gate verdict over every gated
official cell, with a cell the snapshot holds no record for as a gap (0 indexed, ✗); a cause note for every
failing cell, read from `docs/results/coverage-causes.toml` (`["<Venue> <year> <track>"]` with a `cause`) or
**unclassified**, with the file's sha256 in the header; every proceedings listing whose crawl skipped entries or
disagreed with its page's count; and every OpenReview crawl that is incomplete or has coverage gaps, conflicts,
unmapped venues, non-routine skipped groups or non-routine skipped notes; and every **unresolved record**
(TASK-113): each `conflicts.csv` row a source left unresolved (`unresolved:<source>`, the field `unknown` because
the source's own signals disagree, decision-020), by record id, with the record's track and status in the snapshot now (flagged when the field
is no longer `unknown`, e.g. another source decided it after a merge), the cell it would count in were the field
resolved (for `status`, the record's own track cell; for `track`, the cell of each track a side names) and
whether that cell is gated, so a reader can see which gated deltas an unresolved record explains (on the
2026-09-29 crawl: ICLR 2021 `xGZG2kS5bFk` and ICLR 2018 `S1p31z-Ab`, both ICLR main). The report reads
`conflicts.csv` only after checking its sha256 against the manifest's `files`. `--check` exits 1 when the gate fails or an accepted exception is stale.

**Owner-accepted exceptions.** A gated cell outside ±1% passes the gate only if the project owner accepted its
gap in a decision record and `coverage-causes.toml` records it under the cell (`["<Venue> <year> <track>".accepted]`:
`indexed`, `official`, `reason`, `papers` (record ids), `accepted_by` (a role: `project owner`), `accepted_on`,
`decision`; every key required, no other allowed, no control characters, and the decision record must exist in
`backlog/decisions/`). It passes only while the cell's indexed and official counts are exactly the accepted ones
**and** its papers are the gap: exactly |official − indexed| of them, each a record of the index's snapshot, and
for an under-count a record of the cell's venue-year outside the cell (another track or status), for an
over-count a record counted in the cell. The over-count check can't prove the named records are the extras,
only that they are counted: the owner's decision record is what names them as the extras. Anything else fails the cell again
(`drifted`, the failed check in its cause note); a gap (no records) is never accepted and stays `✗ gap`. The
report marks the cell `✓ accepted exception`, lists every exception in its own section and counts them in the
verdict line, and reports an exception whose cell is within ±1% or not gated as stale; `--check` exits 1 on a
stale exception too. ICLR 2013 main is one (decision-016). The report also lists, per cell, the
accepted records whose only source is an imported RIS set, with the cell's delta without them (TASK-178): such
a record is counted as indexed with no listing or note behind it, and where it is a second copy of a crawled
paper it inflates the cell. The exception is applied by the gate report
(`op eval coverage`) only: `GET /coverage` and the `/coverage` page report the raw ±1% per cell, so an accepted
cell is served with `within_gate: false`.

## D. Classification audit (report)

Sample 50 records per `track` value (stratified by venue and year). Two reviewers label each one blind.
Report accuracy and Cohen's κ. Start with venuescout's 92 human-verified workshop calls as a seed set. The
target is ≥99% accuracy on `workshop` vs non-workshop, because a workshop slipping into a main-track search
is the specific failure this project exists to prevent.

## E. Performance (CI benchmark)

The 03 budgets are measured with `pytest-benchmark` on the fixture index in CI (a relative regression over
20% fails); nightly, the 5k budgets are asserted again and a synthetic ~80k report is produced. Numbers on the
real (full) index are a local run, since the real corpus is local only (decision-004).

As built (task-031): `backend/tests/bench/test_bench.py` runs on the synthetic 5k index. It covers every
Trust-Evals string (a 50-hit search and `match_ids` with exclusions, cold cache) and the widest expansion
under the cap and one past it, and asserts each budget on the p95 of 30 rounds. In ordinary runs benchmarks
are disabled and run once as tests; the `bench` workflow enables them and compares the head with the base
(the minimum time, the statistic least moved by runner noise). It also covers every sort, a broad query (thousands of matches),
the widest wildcard inside a search, a multi-token NEAR, a nested NOT, draining an export, and a 500-record build. The check is advisory until it has proven
free of false failures on shared runners (spec 08); sub-millisecond calls repeat within a round (≥ ~1 ms each). The search benchmark is warm after one warm-up round; `match_ids` clears every cache
(verified clauses, expansions, compiled queries) every round, so it is cold.
The ~80k numbers, and the position-verified cases spec 03 exempts, are a report
(`backend/tests/bench/report_80k.py` → `docs/results/<date>-bench.md`), from the same synthetic generator at
80k with abstracts of realistic length. The `nightly` workflow's `benchmarks` job runs the 5k benchmarks with
their budgets and then this report, into the run summary and a `bench-80k` artifact kept for inspection (a
citable number is a committed `docs/results/<date>-bench.md`); a budgeted number past its budget is listed in
the report and shown as a warning annotation, never a failure (TASK-057).

The `/search` endpoint rows (`test_search_endpoint_first_page`) run over the 5k corpus as the API serves it
(`attributed` records: authors and abstract claims) and include each hit's `abstract_source`, a lookup in
what the snapshot reader computed at load (TASK-134; about 95 µs per 50-hit page on the served snapshot, spec
03 §Performance budgets), and each concept group's counts as the route asks for them, at `ApiConfig`'s
default bounds, grace and wait (TASK-176). Beside the first page of every Trust-Evals string there are a warm
later page of each (`test_search_endpoint_later_page`: facets and counts from the memo) and a query of ten
one-word groups, the most `/search` counts (`test_search_endpoint_ten_groups`: 20 collections on a first
page); `test_the_endpoint_bench_counts_groups` checks that these rows do count groups. What the counts add,
with and without them on the fixture and on the real corpus (every Trust-Evals string too), is a report
(`backend/tests/bench/group_counts_report.py` → `docs/results/<date>-bench-group-counts.md`; median and p95
of 200 rounds, cited only at a 1-minute load under 5 at the start and the end), cited by 04 §SearchResponse.

## F. Usefulness of near-misses (report, M5: deferred)

This is 06's recall@25 protocol, using the review's Covidence included set as ground truth. Deferred with
06 (decision-017): v1 is Boolean search only, so neither this report nor §A's semantic invariant is a v1
release gate. Both become required when the semantic layer is built.

## Error handling

- A gate that cannot run (a missing fixture snapshot, a crashed oracle) **fails** the build; it is never
  skipped or reported as passed.
- A report whose inputs are missing (no Scholar set, no official count for a cell) says so in the report
  and leaves that cell unscored; it never fills in an estimate.
- An **our bug** row in the Scholar comparison (§B) or a differential counterexample (§A) opens a Backlog
  task with the query and the shrunk AST before the report is committed.

## Testing

The evaluation tooling is tested like any other code:
- The report generators (`op eval scholar|coverage|audit`, and `near-miss` when 06 is built) have unit tests on fixture inputs
  with known answers. For example, a coverage fixture with one cell off by 2% must fail the gate.
- The CI gates in §A are checked for teeth by mutation. Deleting the comparison, or the oracle call, must
  make the suite fail (`qa-auditor`).
- Dated reports in `docs/results/` are regenerated from their command, never edited by hand. A report
  whose command no longer reproduces it is a Should.
