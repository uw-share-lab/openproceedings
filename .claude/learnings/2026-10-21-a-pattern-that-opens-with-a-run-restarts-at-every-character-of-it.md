# A pattern that opens with a run is retried at every character of a run nothing ends: anchor it with a lookbehind

**Key lesson:** A `finditer`/`sub` pattern that opens with a repeat (`(\\*)[{}]`) is retried at each character of a run that its terminator never follows, and each retry reads the rest of the run, so it is quadratic. Anchor it where the run starts (`(?<!\\)(\\*)[{}]`), and prove the anchor changes nothing by comparing the old and new patterns' spans and groups over every short string of the characters they read.

- **Date:** 2026-10-21 · **Task:** TASK-274 · **Area:** api
- **Artifacts:** `backend/src/openproceedings/export.py` (`_BRACE`, `_SPECIAL`, `_AT`), `backend/tests/unit/test_export_braced.py`, `backend/tests/timing.py`

## What we set out to do
Make BibTeX export's `_braced` linear on a long backslash run (TASK-272's sweep: one 20,000-character abstract
cost seconds of CPU on every public `/export?format=bibtex` that included it), keeping its output byte-identical.

## What we learned
- **Why it was quadratic.** `re` scans left to right and tries a match at every position. At each backslash of
  a run that no brace (or `&%#`, `@`) ends, the greedy `\\*` took the rest of the run, met the wrong character
  and gave the run back one backslash at a time. That is ~n²/2 steps for a run of n. The fix is not
  possessive (TASK-272's tool for memory): possessive stops giving back within one attempt, but the attempts
  still start at every backslash. A lookbehind `(?<!\\)` makes every start inside a run fail in one step.
- **Why the anchor is exact here.** Two things hold. No match ends on a backslash, so the unanchored scan never
  resumed inside a run: it reached each run at its first backslash, where the lookbehind allows a start. And
  `\\*` can give the run back down to nothing, so an attempt that fails at the first backslash fails at every
  later one. The second is not automatic: a parity pattern `(?:\\\\)*@` matches the last two backslashes and the `@` of `\\\@` (three backslashes), and
  anchored it finds nothing (the docs review's counterexample).
  The test doesn't trust that argument. It compares the three patterns' `(span, groups)` lists, and
  `_braced`, `_debraced` and `_balances`, against the old patterns on all 299,593 strings of up to 6 characters
  over `\{}&%#@x`. A one-off run took it to length 8 for the patterns and 7 for the functions: no difference.
- **Swap the module attributes back for the "old" side.** `_pre274()` puts the old compiled patterns on
  `export` for one call, so the comparison runs today's `_braced` with only the patterns changed, rather than a
  second hand-copied function that could drift from the real one.
- **Show the growth check fails first.** On the old patterns `growth` gave ratios of 15.8 to 16.0 for 4x the run
  (the limit is 8). With the anchor they were 3.8 to 4.0. Three wrong patterns (`\\?` for `\\*`, a brace class
  without `}`, a lookbehind that also refuses `x`) each failed all three equivalence tests.
- **DOI and url are covered.** Both are written through `_braced`, as is `abstract_source`'s url, so the one
  fix covers them. They still have no length cap at ingest (decision-026 caps only titles and abstracts).

## Dead ends — don't repeat these
- Reaching for possessive quantifiers again. They bound memory within one attempt (TASK-272), not the number of
  attempts.

## Decisions (and what would change them)
- The lookbehind rather than a hand-written scanner. It is a one-token change that is exactly equivalent
  (shown exhaustively). A pattern whose matches can end inside a run, or whose run can't shrink to nothing
  (parity), needs its own proof, or a scanner.

## Follow-ups
- [ ] task-279 — decide ingest length caps for the uncapped stored string fields: DOI, URLs, authors, keywords, venue_id_raw (decision-026 caps only titles and abstracts)

## Propagated to
- Skill: `.claude/skills/testing-standards/SKILL.md` §7 (anchor a run-opening pattern with a lookbehind and
  prove it exhaustively); `.claude/skills/bibtex-format/SKILL.md` §Escaping (the patterns, the exhaustive and
  growth tests).
- Test: `backend/tests/unit/test_export_braced.py`; TASK-275 (`logs.scrub`) and TASK-276 (openreview_v1
  `_TRAILING_AND`) are quadratic patterns over a run found by the same sweep, for the same check.
