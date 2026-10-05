# A proceedings hash names a paper only within its year, and a stemmer that wants a vowel misses `LLMs`

**Key lesson:** When matching outside records to the index by a proceedings id, key it by venue and year as dedup does (a NeurIPS `nips-<hash>` is md5 of the paper's number and repeats every year), and before trusting a hand-written stemming rule, print the variant table it produces for the real query: the commonest variant missing from it is the bug.

- **Date:** 2026-10-04 · **Task:** TASK-056 · **Area:** eval
- **Artifacts:** [comparison core](../../backend/src/openproceedings/eval/scholar_compare.py), [report](../../backend/src/openproceedings/eval/scholar_report.py), [first report](../../docs/results/2026-10-04-scholar-comparison.md), [protocol skill](../skills/scholar-comparison-protocol/SKILL.md), [spec 07 §B](../../docs/specs/07-evaluation.md)

## What we set out to do
Build `op eval scholar` (spec 07 §B): match a Scholar RIS set to one pinned index by the merge rules, classify every record only one side holds, and commit the first report.

## What we learned
- **A bare proceedings id is not an identity.** `dedup.proceedings_ids` returns `nips-<hash>` without a year, which is right inside dedup because every merge key there already carries venue and year. Looked up across the whole snapshot, the same hash named a 2022, a 2023 and a 2025 paper: the first real run reported 316 of 1,834 Scholar records as ambiguous. Keyed by (venue, year, id), with the year read from the URL itself (`urls.proceedings_parts`; the PMLR volume table for ICML), all 316 matched and the counts met the earlier script's (51 kept, 16 added on the `$` string). Unit fixtures with one year could not have shown it; `test_match_order_…` now holds one hash in two years.
- **The variant table is the stemmer's test.** The inflection rule first required a vowel in every stem, to keep `string` from becoming `str`. That also kept `llms` from becoming `llm`, and the report's own table of added forms listed `benchmark`, `model`, `trust` and no `llm`. Reading the table caught it; the counts alone looked plausible. The vowel rule now applies to `ed` and `ing` only.
- **A report with prose needs somewhere to keep it.** Reports are regenerated from their command, so a sentence about one set of inputs (why `mended.ris` and not `clean.ris`, what the raw exports' sizes were) can't be typed into the output. It lives in `docs/results/scholar-comparison-notes.md`, printed verbatim under its sha256, as the coverage report reads `coverage-causes.toml`.
- **A regenerated review file can erase a person's work.** `review.csv` is written by the command and then filled in by a person. `scholar_report.write` refuses when any `human_class`, `reviewer_role` or `note` cell is filled.
- **Paths are personal data.** The first draft printed the command with the RIS file's absolute path, which holds a user name. The report names inputs by file name and sha256 only, and a test asserts the temporary directory never appears in it.
- **An oracle built over the compared records is enough, and fast.** `ReferenceEngine` is built over the 1,807 matched Scholar papers plus the engine's in-scope matches, not the 95,877-record snapshot: those are exactly the records a row is written about, and each reading takes seconds. Memoise each tree's match set: the first version re-ran a reading per row and one query took 95 s.

## Dead ends — don't repeat these
- Calling `scholarmend.parse` output "the venue" by substring. Scholar cuts venue names (`… Information Processing …`); `compat.SOURCE_ALIASES` is matched exactly, and a cut string is no venue. Such a record is out of scope unless a URL of it names an indexed paper, and the report lists the seven whose title an index record shares.
- Writing a literal byte-order mark escape in a test through a tool that decodes escapes: the file ended up holding real U+FEFF characters. Write the file with `encoding="utf-8-sig"` instead and let the codec add it.
- Classing every unmatched record `coverage_gap` and calling it settled. The three in the first report link to link.springer.com, neurips.cc slides and ieeexplore.ieee.org, filed by Scholar under ICML or NeurIPS: likely Scholar's venue, not a gap in the corpus. Every `coverage_gap` now goes to a person, with the hosts of its links as evidence.

## Decisions (and what would change them)
- The `stemming` test is inflection only. (This entry first called `full_text` a lower bound; the review showed that is wrong, see the addendum.) A documented description of Scholar's stemmer, or the owner choosing Porter, would change it; the rule's choice is listed for the owner in the task's notes.
- The review file is `<date>-scholar-comparison-review.csv`, not a bare `review.csv`: a second run on another day must not land on the first one's human calls.

## Follow-ups
- Listed in TASK-056's notes for the main session to file (ids are assigned there): the owner's call on the stemming rule and on quoted words; ICML 2026 records without abstracts; a full per-row classification file if the paper needs every row.

## Propagated to
- [scholar-comparison-protocol skill](../skills/scholar-comparison-protocol/SKILL.md) (matching within venue and year, the review file as built, the stemmer gotcha), [spec 07 §B](../../docs/specs/07-evaluation.md) as built, [spec 08 §CLI](../../docs/specs/08-ops-and-tooling.md).
- Test or hook added? — yes: `backend/tests/unit/test_scholar_compare.py` (one hash in two years; `vlms`/`gnns` stems) and `test_scholar_report.py` (no path in the report; a filled review file is never replaced).

## Addendum — 2026-10-04: the review found the set matching its own import
- **Ask what the index record rests on before counting a match.** The snapshot was built with this same Scholar set imported as its `ris` source. 530 of the 1,807 matched papers matched a record nothing but that import holds (ICLR 2026 415, ICML 2026 111), and no 2026 record was crawled, so "1,807 of 1,810 match" was partly the set matching itself, `full_text` for those rows was judged on the import's own text, and nothing could be only in openproceedings for 2026. The first report said none of this. Matching now records each record's independence and abstract source (`MatchIndex.independent`, `Row.independent`), and the report splits every count. How to recognise it early: tabulate the matched records' provenance sources per venue-year before writing a headline; a cell whose matches are all one bootstrap source is not evidence.
- **"Errs towards X, so Y is a lower bound" needs the direction checked.** A wider stemmer moves rows out of `full_text`, so the inflection-only stand-in makes `full_text` larger, not a floor. The report now gives a sensitivity figure (every word read as a prefix) and calls the stemmer an open owner decision.
- **Pick one overlap order and write it in one place.** The skill said a record both filtered and stemmed is `filtered`; the code said `stemming; also filtered`. Code, skill, spec and tests now judge the filters first.
- **A default notes file is a trap.** Notes about one export were read by default from `docs/results/`, so a run on any other set would have printed them. `--notes` has no default now.
- **A quadratic count hides in a dict comprehension.** `{s: sum(r.search == s for r in records) for s in searches}` took 10.9 s on 20,000 one-record searches; a `Counter` and a cost-ratio test replaced it.
