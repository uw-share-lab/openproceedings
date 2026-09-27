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
