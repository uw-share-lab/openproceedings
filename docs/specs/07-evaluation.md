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
| Semantic invariant (shelved with 06, decision-017; not a v1 gate) | Search results identical with 06 on and off | 0 diffs, if 06 is ever built |
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
workflow's `differential` job runs 50,000 examples in total: 12 independent runs in parallel, eight of 4,167 and four of 4,166, so exactly 50,000 (8 of 6,250 until 2026-10-11), each with
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
  2022)`), which is no venue. A DOI (`DO`, the tag Scopus and Web of Science RIS both write, or a `doi.org` link; `DI` is
  Web of Science's plain-text export tag, which is no RIS, and is not read; read by `doi_key` in one pass, so a
  hostile value can't outlast `/compare`'s time limit: a `doi:` or `DOI `
  label is dropped, then a doi.org link's prefix with or without its scheme, `www.` or `dx.`, and its query and
  fragment (so `DOI https://doi.org/…` reads), then the `.`, `,`, `;` or unbalanced `)` a sentence leaves after
  it; a suffix with whitespace, a control character or a bidi format character (marks, embeddings, overrides,
  isolates) is no DOI; compared case-blind) names the index record whose `urls.doi` it is, **only when the record's year
  is the year the file states and its venue the venue the file states**, each where the file states one (a year;
  one of the three venues by Scholar mode's source names). A DOI that names a record in another venue or year is
  never a match: the record falls to the title rule, and its row names that record (`doi_elsewhere`, "its DOI
  names …, another venue or year: never a match"). A venue string that is no venue does not block a DOI, as it
  doesn't block a forum or proceedings id; that is what lets a Web of Science record match. A DOI two records
  carry, or a DOI and another id naming different records, is ambiguous. **Where the index has DOIs:** only
  NeurIPS proceedings pages give one (`citation_doi`, prefix `10.52202`), so on index `fd13d8d27535` (snapshot
  `2026-10-05-10b5a205a63f`) 16,690 of its 133,629 records carry a DOI (counted on 2026-10-05 by reading that
  snapshot's `records.jsonl` and counting the records whose `urls.doi` is set, by venue, year, track and
  status; a one-off read, not a committed report): every accepted NeurIPS 2022–2025 main,
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
NeurIPS 1987–2020 and ICML 2013–2022 come from proceedings only, and ICML 1988–2012 from the pinned dblp
release (decision-047), so no rejected papers exist there to exclude; NeurIPS and ICML on OpenReview hold only the rejected papers whose authors opted in, while ICLR
holds every rejected, withdrawn and desk-rejected submission (decision-012). The crawl window is each venue's
first year on: NeurIPS 1987, ICML 1988, ICLR 2013 (decision-047, superseding decision-013's 2013 floor); any
venue-year with no source is a reported gap, never a silent zero. Before 2013 only NeurIPS, ICML and (from milestone B) AAAI have cells,
so cross-venue counts over those years compare three venues, not more. ICML 1988–2012 records come from dblp,
which has no abstracts: only the years whose official ICML pages give abstracts have them (TASK-206), and every
other record of those years is title-only, counted in the cell's missing abstracts. ICLR 2014–2016 are
not gaps: their public archive listings supply accepted main-track records (TASK-096).
**AAAI 2010+, AIES 2024+ and IASEAI (decision-049, milestone A).** The index holds AAAI 2010–2026, AIES 2024–2025 and IASEAI
2026 from ojs.aaai.org, every record `accepted` (published in the proceedings: the source lists no rejected paper),
each venue-year a coverage cell with its real tracks (`main`, `student_abstract`, `consortium`, `demo`, `iaai`,
`eaai`, `other`). AAAI's `main` is the section mapping of `ingest/ojs_sections.toml` (technical, special and Journal
tracks, and the 2010–2014 topic sections), not a track AAAI itself names. **Twelve cells are gated**
(`official_counts.py`). Six were read 2026-10-09: AAAI 2013 (203), 2015 (539), 2018 (938) and 2019 (1,147) main, and AIES 2024
(150) and 2025 (238) main, each the program chairs' own statement of accepted papers (a preface, an issue's
front-matter description, the AI Magazine conference report, the AIES program), not a count of the listing the
crawl reads. AAAI 2013's count includes its AI and Robotics special track, which is why the 2011 and 2013
"Robotics Program" sections are `main`; AAAI 2013's gate row therefore pins that mapping ruling (the one gated row that
depends on a section decision), so a failing 2013 cell is a reason to check the mapping before the crawl. Four more,
read 2026-10-10, are counts of AAAI's own published accepted-paper list (no AAAI document states an accepted count
for these years): AAAI 2012 (292), 2017 (637), 2020 (1,614) and 2021 (1,696) main. A list count backs a row only
when the list is independent of the OJS proceedings and its definition is our `main` cell. A list counts as independent of the proceedings when it either states that it is pre-camera-ready, or visibly differs from the proceedings in content (a different count or membership); either shows it was not derived from them. Each row's
description says "counted", names the list and names its ground (gate C round 2): 2020's lists say they were made
before camera-ready; 2012, 2017 and 2021 differ from the proceedings in count. AAAI 2010 (262), 2014 (398) and 2016
match the proceedings exactly and are not shown to predate them, so each is an ungated cell with a note. The other cells are recorded, not gated, and each carries a cited **ungated-cell note** (`gate_note` on
`/coverage`, a section of the report; `official_counts.UNGATED_NOTES`, TASK-222): AAAI 2011's list leaves out the
Robotics Program our `main` holds (240 against 248); AAAI 2010's, 2014's and 2016's lists match the proceedings
and don't say they predate them, so they may be derived from them and a gate on them would check nothing; AAAI 2022–2026 have only chairs' emails
quoted elsewhere and third-party paper trackers' figures, which are never a row and seem to count the main technical track alone;
IASEAI 2026's front matter states 92 accepted research papers, but 35 of them are non-archival and unpublished on
OJS, so 57 indexed against 92 would fail the ±1% gate for a reason the index cannot repair. The research note
classifies every venue-year (`docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` §Official counts). Each OJS volume's listed
count is also checked against the verified count in `ingest/ojs_sections.toml`, and a difference stops the crawl
(`count_mismatch`, spec 01), so no snapshot holds a mismatched OJS listing: the report's listings section can name an OJS
volume only for its skipped entries (AAAI 2026's `unavailable 1`), always with `count_ok` yes. One article the OAI list names, AAAI 39173, is served in no form; it is counted
in AAAI 2026's listed 4,921 but is never a record (spec 01, `[[unavailable]]`).
**AAAI 1980–2008, AIES 2018–2023 and FAccT (decision-049, milestone B).** These venue-years are now coverage cells
(AAAI 1980–2008's 23 held years, with no cell for 1981, 1985, 1989, 1995, 2001, 2003 or 2009 and the coverage page's
"none in" list saying so; AIES 2018–2023; FAccT 2018–2026), and the report's database scope names where each comes from:
the pinned dblp release for AAAI (4,709 records, none with an abstract), Crossref's records of the ACM proceedings
for FAccT 2019–2026 and AIES 2018–2023, and, for FAccT, how many abstracts the official pages gave (2022 169 of 181,
2025 206 of 206, 2026 298 of 314). Crossref carries no section data, so each AIES 2018–2023 paper's track comes from its page
position (`student_abstract` cells), and the scope line counts each venue's entries that are not papers (keynotes,
invited talks, panels, tutorials: counted, not indexed; decision-050). **None of these cells is gated, and no row was added to `official_counts.py`.** Each count is the
proceedings' own contents (Crossref's DOIs, PMLR's index, dblp's keys) checked against the table in `ingest/`, which is
the crawl stopping on a mismatch (spec 01 §Sources), not an independent statement of accepted papers, so these cells
are `accepted` by construction (statuses indexed: `accepted`) and cannot show a missing paper: a `Δ —` is no
agreement; no official
accepted-paper statement was read for these years (aaai.org states none for 1980–2008; facctconference.org lists
accepted papers without a stated count, and its 2025 and 2026 lists hold non-archival papers the proceedings don't,
217 and 325 rows against 206 and 314 DOIs), so even a stated figure would likely be a definition mismatch with our
`main`. The research note's §Official counts says the same. Cross-venue counts still compare venues over different year
spans (AAAI from 1980, NeurIPS from 1987, ICML from 1988, ICLR from 2013, AIES and FAccT from 2018, IASEAI 2026).
**Where abstracts come from (decision-049, milestone C).** AAAI, AIES and FAccT records that no official source gives an
abstract are filled from OpenAlex where it has one (spec 01 §Sources, OpenAlex row), and the coverage report and
`/coverage` count them apart: every cell, venue-year and the totals carry **Official abstract** and **OpenAlex
abstract** columns beside **No abstract** (and the withheld count, when there is one), so that official + OpenAlex +
missing + withheld = records. The database-scope line says, for AAAI, that 1980–2008 comes with no abstract from dblp
and that OpenAlex's is filled in where no official AAAI source gives one, and, when a snapshot holds any, it adds how
many abstracts (and for which venues) are OpenAlex's, labelled `abstract_kind:openalex`; a snapshot OpenAlex filled
nothing in reads as it did. The coverage numbers come from the manifest's `abstract_openalex` and
`abstract_openalex_by_track`, which the load checks against the records. How faithful those abstracts are is §G.
As built, the milestone's report (`docs/results/2026-10-11-coverage.md`, index `b4f335e07e70` on snapshot
`2026-10-11-93c2937e2f29`, 173,253 records) passes `op eval coverage --check`: 81 of 82 gated cells within ±1%, the
82nd being ICLR 2013's owner-accepted exception, and 1,117 abstracts labelled `abstract_kind:openalex` (AAAI 21,
AIES 557, FAccT 539); another 4,536 AAAI 1980–2008 abstracts are official, from `aaai_library` (decision-051). The
gate has two fewer cells than the earlier as-built report (`docs/results/2026-10-10-coverage.md`, index
`9977ed00669f`, 83 of 84, 2,158 OpenAlex abstracts), which stays as history.
The source of statuses indexed is spec 01's source table as `ingest/statuses.py` holds it (spec 01
§Pipeline 5); the snapshot manifest records them per venue-year, and the missing abstracts and sources per
cell (manifest format 2, TASK-082).
**Ungated cells with a note (TASK-222).** `op eval coverage` ends with a section "Ungated cells with a note": one line per
cell `GET /coverage` serves with a `gate_note`, `- <V> <Y> <track>: <note> (source: <citation>)`, or "None: no ungated
cell in this snapshot has a note." when there is none. The notes are `official_counts.UNGATED_NOTES`, whose cited
copy is `docs/results/coverage-sources.md` §Ungated cells with a note (a test keeps the two equal); a note may not sit
on a gated cell. `/coverage` shows the same text under the track's row (copy CV-9).
The methods text cites the coverage report (with its snapshot hash) as the database-scope caveat. Under its header
the report states each venue's indexed years, and, when the snapshot holds the dblp release, that ICML 1988–2012
rests on that pinned bibliography and official ICML pages rather than a crawl on the window's dates. It also says
how many of those official pages' abstracts (ICML 1997 and 1998's) are submission-time abstracts, which can differ
from the published papers' (TASK-207). After the gate verdict it says how many gated cells compare the crawl with
its own listing's stated count (decision-047).
`GET /coverage` serves every column per cell (`venue_years[].tracks`: sources, indexed accepted,
`official_accepted` with its citation, `delta`, `delta_pct`, `gated`, `within_gate`, an ungated cell's `gate_note`
and `gate_note_citation`, missing abstracts) and
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

## F. Usefulness of near-misses (report, M5: shelved)

This is 06's recall@25 protocol, using the review's Covidence included set as ground truth. Shelved with
06 (decision-017): v1 is Boolean search only, so neither this report nor §A's semantic invariant is a v1
release gate. Both become required only if a decision superseding decision-017 resumes the semantic layer.

## G. OpenAlex abstract fidelity (report, `op eval openalex`)

OpenAlex fills an abstract only where every official source gave none (spec 01 §Sources), so on the records it fills
there is no official text to check it against. The audit measures it where both exist, and writes
`docs/results/<date>-openalex-audit.md` (the current report is [2026-10-16-openalex-audit.md](../results/2026-10-16-openalex-audit.md), on the final snapshot
`2026-10-11-93c2937e2f29`; it adds the `aaai_library` comparison to the milestone's
[2026-10-11 report](../results/2026-10-11-openalex-audit.md) on the same snapshot, where the title route attaches 19 and 18 agree; the earlier
[2026-10-10 report](../results/2026-10-10-openalex-audit.md), on snapshot `2026-10-10-22a339940466` before `aaai_library`
took over most AAAI 1980–2008 abstracts, checked 1,061 title attaches; the DOI-route rates below are the same in both).
It feeds nothing: it writes no extract, touches no snapshot and gates nothing, and the rates are not thresholds.

**Method (`eval/openalex_audit.py`).**
- **The DOI route.** Every record of FAccT 2022, 2025 and 2026 and AIES 2024 and 2025 with an official abstract and a
  DOI (FAccT's official abstracts are the conference site's; AIES's are ojs.aaai.org's), and a seeded sample (seed 49,
  1,000 in id order) of the 25,124 such AAAI 2010+ records. Each venue-year's DOIs are looked up in OpenAlex in sorted
  batches of 50, exactly as `op ingest openalex` looks them up (`openalex.doi_lookups`, halving included), each work's
  `abstract_inverted_index` is rebuilt and cleaned by the fill's own rules (`openalex.abstract_of`), and the text is
  compared with the official one. A work returned for a DOI that was not asked is counted and never compared.
- **Classes.** `exact` (equal once whitespace is collapsed); `near_exact` (the same search tokens under the token
  contract, so every search matches both alike); `truncated` (OpenAlex's tokens a strict prefix of the official
  ones); `similar` (a token `SequenceMatcher` ratio of at least 0.9); `differs`. Beside these, a record's outcome can
  be `no_abstract` (OpenAlex has the work but no abstract), `no_openalex` (no work for the DOI; kept apart from
  `no_abstract`), `refused` (the rebuild or cleaning refused it, the reasons listed) or `duplicate` (several works with differing
  texts; several with one text are compared once). Every rate is of the records compared in its row, and the report
  quotes no abstract text: records are named by id.
- **The title route.** AAAI 1980–2008 has no DOI, so the fill matches by exact title key and year in the listing
  (spec 01). The fill is replayed over the cached listings and **every** title-route attach (1,061 in the 2026-10-10 run, before `aaai_library`; 19 on the final snapshot) is checked
  against OpenAlex's authors for the work (one request per 50 works): the years must match (they do by
  construction) and the author lists must share a surname (surnames compared without marks or case, dblp's
  homonym numbers and Jr./II suffixes dropped, `Last, First` handled); `agree`, `wrong` (OpenAlex lists authors and
  none is ours) or `unverifiable` (an empty list on either side). The report lists each `wrong` one and the rules
  that would exclude it, with what each rule costs, and counts how many have a near-spelling first-author surname.
- **AAAI's archived pages (`library_check`, TASK-235).** An AAAI 1980–2008 record whose abstract is `aaai_library`'s
  (official) never takes OpenAlex's, but the title route often finds a work for it. The fill is replayed over the
  cached listings twice, as the records stand and with those abstracts set aside, and each text the second run would
  attach is compared with AAAI's by the classes above. A work with no abstract is counted `no_abstract`; the other
  refusals the second run adds (`title_unmatched`, `title_ambiguous`, rebuild refusals) are counted by reason. This is
  the one measure of OpenAlex's text for those years.
- **Reproducibility.** The fetcher is the one OpenAlex fetcher and cache (api.openalex.org only, one request a second,
  keyless, no contact address). The reproduction command in the report starts `op eval openalex --offline …` and
  carries `--date` and the controller's `--ruling`, so a re-run from the cache makes no request and renders the same
  bytes. Flags: `--snapshot` (default: the current index's), `--aaai-sample`, `--title-sample`, `--seed`, `--offline`,
  `--out`, `--date`, `--ruling`. The command holds the `<cache>/openalex` lock.

**The rates (2026-10-10, 2,122 records compared).** Exact or near-exact for 83.1% (exact 72.8%, near-exact 10.3%); 1.7%
truncated, 9.6% similar, 3.8% differs (81), 1.6% no abstract at OpenAlex; no refusal, no missing work. By venue:
AAAI 2010+ 99.3% exact or near-exact (991 exact, 2 near-exact of 1,000), AIES 2024 and 2025 100%, and FAccT far lower:
2022 23.1% (14.8% exact), 2025 59.2%, 2026 53.6%. **FAccT's difference looks like a different version, not noise**:
its `similar` and `differs` cases are mostly the same length and open with the same words, so OpenAlex often carries
ACM's published version of an abstract, not the conference site's text (a few are entirely different texts). An
abstract the fill takes from OpenAlex is labelled `abstract_kind: openalex`, never `official`, which already tells
a reader it is OpenAlex's, possibly ACM's version; the label is how a review excludes them.

**The title route's result, 2026-10-10 run (before `aaai_library`).** 1,052 of 1,061 attaches agree (99.2%); 9 look wrong (0.8%), none is unverifiable.
Seven of the nine are spelling or OCR variants of the same surname (for example kender/render, pentland/pentlaud), so
a surname rule would mostly drop correct attaches (requiring a shared surname excludes exactly the 9; requiring the
first author to match also excludes 8 that agree on another author). **Ruling (controller, 2026-10-10): keep the exact
title-key and year rule**; the residual wrong-attach risk is about 2 of 1,061 (an estimate: the audit's Caveats).

**The final result** ([2026-10-11 report](../results/2026-10-11-openalex-audit.md), after `aaai_library` took most AAAI 1980–2008 abstracts): the title route attaches 19 and 18 agree; the 1 other is an OCR variant (`nournai`/`nourani`). The ruling stands.

**OpenAlex against AAAI's archived pages** ([2026-10-16 report](../results/2026-10-16-openalex-audit.md), same snapshot;
the DOI route and title route figures are unchanged). Of the 4,536 AAAI 1980–2008 records with an `aaai_library`
abstract, the title route finds one work with a text for 1,131. OpenAlex's text is exact for 361 (31.9%), near-exact
for 223 (19.7%), truncated for 16 (1.4%), similar for 408 (36.1%) and differs for 123 (10.9%): 51.6% would match every
search exactly as AAAI's text does, against 99.3% for AAAI 2010+ on the DOI route. Another 109 have a work with no
abstract; 3,216 have no listed work with their title key, 20 are ambiguous and 60 refused by the rebuild. `differs` runs
highest in 1994–2002 (15.9–50.0% a year). It is a measure, not a threshold: the records OpenAlex does fill are the ones the
archived pages don't cover, and they carry `abstract_kind: openalex`.

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
