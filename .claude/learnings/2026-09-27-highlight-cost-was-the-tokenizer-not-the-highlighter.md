# The highlight page cost was the tokenizer's per-character loop, not the highlighter's structure

**Key lesson:** Profile before restructuring: three quarters of a page's highlight time was `tokenize` running `_fold` on every ASCII character, and exact shortcuts inside `normalize.py` (a plain-ASCII text path, an ASCII-character branch), pinned to a frozen copy of the old loop, bought ~7× with no `TOKENIZER_VERSION` bump.

- **Date:** 2026-09-27 · **Task:** task-073 · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/query/normalize.py`, `backend/src/openproceedings/engine/highlight.py`, `backend/tests/unit/engine/test_highlight_speed.py`, `backend/tests/unit/tokenize_before.py`, `backend/tests/unit/engine/highlight_before.py`, `docs/results/2026-09-27-highlights.md`

## What we set out to do
Fit a 50-hit page's highlights inside spec 03's 100 ms page budget without changing any span.

## What we learned
- cProfile on the real local index (every Trust-Evals page): `tokenize` 2.15 s of 2.82 s, of which `_fold` 1.05 s over 413k calls (one per character); `occurrences` (a rescan of the field per leaf) 0.64 s. The highlighter's structure was the smaller part.
- 77% of real titles and abstracts are ASCII with no `\` or `$`, so their tokens are exactly the lower-cased `[A-Za-z0-9]+` runs (the LaTeX mask is all KEEP without those two characters). The synthetic 80k generator is about 50%, so the loop's own ASCII branch matters there.
- A frozen copy of the code as it was is a better differential oracle for an optimisation than the whole-string definition: it compares everything a token carries (`reach` too), which the definition doesn't.
- A mutant that only swaps which of two equivalent lookups runs (`len(first) <= len(where)`) survives every test: it is a performance choice, equivalent by construction.

## Dead ends — don't repeat these
- A per-(index_version, id) token cache (the task's first idea) only helps a page seen before; the first page of a new query pays in full. Make the work cheaper before caching it.
- The Write tool turned `\u0301` escapes in a test file into literal combining characters; check non-ASCII test literals with `grep -nP "[^\x00-\x7F]"` and write them as escapes.

## Decisions (and what would change them)
- Fast paths inside `tokenize`, not a second tokenizer elsewhere → the token contract keeps one implementation → a fast path the frozen-copy differential can't pin.
- No cache and nothing precomputed at build (no SCHEMA_VERSION bump) → a page is within budget cold → abstracts much longer than 250 words becoming common.

## Follow-ups
- none: the numbers are in `docs/results/2026-09-27-highlights.md`; a quiet-machine regeneration of the 80k report adds its page column.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/token-contract/SKILL.md` (the two shortcuts and their oracle), `.claude/skills/api-contract/SKILL.md` (one `Highlighter` per page), spec 03 §Highlights
- Test or hook added? — `backend/tests/unit/engine/test_highlight_speed.py`, and the bench row `test_a_50_hit_page_with_highlights`

## Addendum — 2026-10-01 (TASK-088: the loop's fast paths)

**Key lesson:** On real abstracts the loop's cost was the ASCII between the few odd characters, not the odd characters themselves; profile the real corpus before building the fast path a task names, and memoise a function on part of its input only after proving the rest can't change its output.

- **Artifacts:** `backend/src/openproceedings/query/normalize.py`, `backend/tests/unit/tokenize_before_088.py`,
  `backend/tests/bench/alternate.py`, `docs/results/2026-10-01-tokenizer-fast-path.md`.
- **What the profile showed:** of the real corpus's texts that leave the whole-text ASCII path (18%), two thirds
  do so for a `$` or `\`, and `_fold` didn't reach cProfile's top 12; the time was `close()` and the
  per-character steps over ASCII (evidence: `docs/results/2026-10-01-tokenizer-fast-path.md` §What changed:
  the loop's own steps 0.75 s of 1.97 s, `close()` 0.58 s). Taking each ASCII stretch word by word
  (one regex search for its end, then `finditer`) gave most of the win: the loop is 1.8× faster on those real
  texts, 1.7× on the synthetic ones. A "non-ASCII Latin" table alone would have missed the LaTeX texts.
- **A cache keyed on the character, sound by enumeration:** `_fold(c, base)` reads `base` only through
  `_folds_marks`, which tells apart five classes, so comparing `_fold` after one base of each proves
  independence (`_BASES`). Checked by hand once against a base per Unicode-name prefix (5,759) for every
  code point (no exception), and by a Hypothesis property in the suite.
- **Hand mutants find what a property's examples don't:** the stretch's base reset survived the property
  until an `@example` put a Thai base, a `.` stretch, `\-` markup and a combining mark in a row. The
  survivors are equivalent (an ASCII letter and no base are one class; `None` and Thai alone already catch a
  base-dependent fold, so the Cyrillic and Arabic bases are redundant): say so rather than chase them.
- **A bounded memo must stop costing once it is full:** the first `_fold_char` still ran five probe folds for
  a character it could no longer keep, 2.6–3.3× slower than no table for the rest of the process (review
  gate). Check the bound before the work that only the table needs.
- **A search for "the next X" from every stretch is quadratic** when the stretches are cut short by something
  else (markup): `_NON_ASCII.search(text, i)` scanned to the end each time and failed task-070's linear-time
  test on `$1` × 4,000. Keep the last position found and search again only past it.

### Dead ends — don't repeat these
- `pytest -k "not light"` to skip the slow highlight tests deselected the whole `test_highlight_speed.py`
  (`-k` matches module names too), so every mutant "survived". Check the selected count, or name the tests.
- Absolute p95 under load: `main-2-pop` on the real corpus read 151–167 ms wall p95 at load 12–27 and 70–73 ms
  at load 4–8. Only the alternated old-vs-new differences are comparable across runs.

### Propagated to
- `.claude/skills/token-contract/SKILL.md` (the three shortcuts and their frozen oracle), spec 03 §Highlights
  and §Performance budgets.
- Tests: `tests/unit/tokenize_before_088.py` (frozen loop, tokens and `Tail`), the `LATIN` strategy and the
  `_fold_char` property in `tests/unit/engine/test_highlight_speed.py`.
