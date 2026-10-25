# A greedy repeated group can make a linear regex memory-bound: use possessive quantifiers

**Key lesson:** When a `(?:sep\d+)*` group has to be followed by a character the group can never give back, make it possessive (`(?:\.\d++)*+`, Python 3.11+). Python's `re` keeps backtracking state for every repetition it might give back. On a long hostile value that state is tens of MB, and the time then likely depends on the runner's cache more than on the input. Test the bound in bytes (`tracemalloc`), not in time.

- **Date:** 2026-10-20 · **Task:** TASK-272 · **Area:** eval, ingest, tooling
- **Artifacts:** `backend/src/openproceedings/eval/scholar_compare.py` (`_DOI`), `backend/src/openproceedings/ingest/record.py` (`_doi`), `backend/src/openproceedings/ingest/sources/html.py`, `backend/tests/timing.py` (`peak_bytes`)

## What we set out to do
Get PR #175 (a docs-only head) through CI. `test_doi_key_is_linear_on_a_hostile_value[registrant]` failed twice
in a row there (10.3x and 11.3x CPU for 4x the input; the limit is 8x), but passed locally at ~4.2x.

## What we learned
- **Not a flake.** Re-running gave the same ratio. The pattern `10\.\d+(?:\.\d+)*/…` on `10.1.1.…1./x!` (1 MB)
  matches every `.1`, meets `./`, then backs off one repetition at a time looking for `/`. That is linear in
  steps, but `re` keeps a saved state for each repetition: 63 MB peak. So the run is memory-bound, and a CI
  runner's smaller cache made it look superlinear.
- **Possessive is exact here.** Anything the group gives back starts with `.` or a digit, never the `/` that
  must follow, so no backtrack can change the result. `\d++(?:\.\d++)*+` gave the same answer on 200k random
  strings, with ~0 MB peak, and the regex alone ran about 4-6x faster on the 1 MB value (local, process time).
- **Measure memory, not time.** The new test bounds `tracemalloc`'s peak (under 4x the value's size). It is
  deterministic on any runner, and it fails on the old pattern (62.8 MB).
- **The shape recurs.** The same `x(?:sep y+)*` then a required character was in `ingest/record.py`'s `_doi` and
  `ingest/sources/html.py`'s two name patterns (62.8 MB each on a 1 MB crawled value). All three are now
  possessive, each with a `peak_bytes` test (`tests/timing.py`).
- **Re-running a CI job doesn't help** once the failure repeats with the same ratio. Read the measured pairs
  instead.

## Dead ends — don't repeat these
- Treating a timing test failing at the same ratio twice as noise and re-running it again.

## Decisions (and what would change them)
- None beyond the fix: possessive is exact for this pattern; a pattern where giving back can matter stays greedy.

## Follow-ups
- [ ] task-273 — doi_key's unquote of a percent-encoded doi.org link costs ~20x its length in memory
- [ ] task-274, task-275, task-276 — older regexes that are quadratic in time, not memory (BibTeX `_braced`, `logs.scrub`, openreview_v1 `_TRAILING_AND`): a lookbehind that starts a match only at a run's start, found by the same review's sweep

## Propagated to
- Skill: `.claude/skills/testing-standards/SKILL.md` §7 (possessive repeats on untrusted input, and a `tracemalloc` bound).
- Test: `tests/timing.py` `peak_bytes`, used by `backend/tests/unit/test_scholar_compare.py`, `backend/tests/unit/ingest/test_record.py` and `backend/tests/unit/ingest/test_html.py`.

## Addendum — 2026-10-24 (TASK-273: doi_key's unquote)
- **Bound a decoder's input by the output cap times the decoding's largest expansion, and refuse past it before
  decoding.** urllib's `unquote` holds about 20 bytes a character, ~329 MB on a link at `MAX_COMPARE_LINE` (16 MB)
  against a file's ~250 MB budget. A DOI longer than `caps.MAX_DOI` (1,000) names no record (decision-053), and a
  character unquotes from at most 12 (four UTF-8 bytes of three characters each), so a link path over
  `_MAX_ENCODED_DOI = 12 * caps.MAX_DOI` is refused unread, and only the part before the trailing run is unquoted
  (the run is read percent-encoded on the reversed path, in one possessive pass). Peak 329 MB → 34 MB (the path's
  two copies) (evidence: `scholar_compare.py` `doi_key`; spec 07; commit e8539317).
- **Count the copies on every form of the value, not only the bare one.** Round 1's 34 MB held for a bare link
  only: `strip()` and the label's slice each copied the line again, 50 MB labelled and 67 MB padded (review round
  1). Reading by position (`pattern.match(text, pos, endpos)`, `str.count(sub, start, end)`, one reversed slice
  `text[end - 1 : start - 1 : -1]`) leaves one copy, 16.8 MB on every form
  (docs/results/2026-10-24-doi-key-memory.md).
- **A rewrite of a matcher keeps its answers only if a frozen copy says so.** The old `doi_key` is kept in the test
  file and a property checks the new one equals it on every value that keys within the cap
  (`test_doi_key_is_the_frozen_function_up_to_the_doi_cap`), with the memory bound tested in bytes as above
  (`test_doi_key_reads_the_largest_compare_line_in_bounded_memory`, under 1.1× the line, bare, labelled and padded).
- Propagated to: spec 07 §B. Scholar comparison (the bound and why); no skill change, since `testing-standards` §7
  already asks for a `tracemalloc` bound on untrusted input.
