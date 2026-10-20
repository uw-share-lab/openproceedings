# A greedy repeated group can make a linear regex memory-bound: use possessive quantifiers

**Key lesson:** When a `(?:sep\d+)*` group has to be followed by a character the group can never give back, make it possessive (`(?:\.\d++)*+`, Python 3.11+). Python's `re` keeps backtracking state for every repetition it might give back. On a long hostile value that state is tens of MB, and the time grows with the CPU's cache rather than with the input. Test the bound in bytes (`tracemalloc`), not in time.

- **Date:** 2026-10-20 · **Task:** TASK-272 · **Area:** eval, security, testing
- **Artifacts:** `backend/src/openproceedings/eval/scholar_compare.py` (`_DOI`), `backend/tests/unit/test_scholar_compare.py`

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
  strings, with ~0 MB peak and 5.6x faster.
- **Measure memory, not time.** The new test bounds `tracemalloc`'s peak (under 4x the value's size). It is
  deterministic on any runner, and it fails on the old pattern (62.8 MB).
- **Re-running a CI job doesn't help** once the failure repeats with the same ratio. Read the measured pairs
  instead.

## Dead ends — don't repeat these
- Treating a timing test failing at the same ratio twice as noise and re-running it again.
