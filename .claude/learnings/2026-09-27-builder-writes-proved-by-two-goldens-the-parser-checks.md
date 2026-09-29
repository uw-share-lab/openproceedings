# A client that writes queries can be proved against the server parser with two goldens, one owned by each side

**Key lesson:** When frontend code writes query text the server must read a certain way, let the backend generate the inputs (each query's `ast` and its own reference reading) and let the frontend generate what it writes from them (unedited and after seeded random edits), then have the backend parse every written string; and check "one term" by lexing the term both alone and between its real neighbours, because an unterminated `"a`, a trailing `a\` and a LaTeX `$` are single lexemes alone but swallow what follows.

- **Date:** 2026-09-27 · **Task:** task-043 · **Area:** frontend
- **Artifacts:** `frontend/src/builder/` (`read.ts`, `terms.ts`, `write.ts`, `edits.ts`, `concept-builder.tsx`,
  `builder-read-golden.json`, `builder-write-golden.json`, `write.test.ts`),
  `backend/tests/contract/test_frontend_builder_golden.py`

## What we set out to do
Build the concept-group builder (Text/Builder tabs) so that it never writes a query the server reads
differently from its groups, with round-trip tests against the real parser and no network.

## What we learned
- **Split the golden by ownership.** The backend owns `builder-read-golden.json` (362 queries: Trust-Evals in
  both modes, every fit-table row, 240 seeded random queries; each with the server `ast` and a Python
  reference reading of the fit rule). The frontend owns `builder-write-golden.json` (673 strings: the 295
  fitting queries rewritten without an edit, plus 378 after seeded random edits through the same pure edit functions the
  UI calls). Each side's test fails when its own file is stale, and the backend test parses every written
  string: unedited → same `canonical`; edited → every chip read alone is one leaf and the query is exactly
  the chips' groups, with no warning the chips don't raise alone. Two implementations of the fit rule (TS
  product code, Python test code) agreeing on all 349 parsed readings is what makes the rule credible.
- **"One lexeme" must be checked in context.** `"` alone, `"a`, `a\` and `$x` each lex as one lexeme, but in
  `(x OR "a)` or `(a\ OR b)` they swallow the rest; `$x OR y$` pairs into one math region across two terms.
  `isOneTerm` lexes the text alone, inside `( )`, and between words; the writer then lexes the whole query
  and leaves out (and flags) any term whose lexemes moved.
- **A limit alone may be refused.** `NOT track:workshop` on its own is `PARSE_ALL_NEGATIVE`, so the backend
  check reads limits next to a word. An edit that empties every group and keeps an Exclude row is the
  server's all-negative error, as in Text — shown, never blocked.
- **The canonical form keeps text-conjunct order,** so an Exclude row read from `NOT (a OR b) trust` has to
  be written back in its place (the model keeps `excludeAt`); moving it last would change `canonical`.
- **`react-hooks/set-state-in-effect`** flagged opening the first empty term for editing from the
  focus-on-open effect; rendering a term with no text as an open box (derived, not state) removed the need.

## Dead ends — don't repeat these
- Answering a UI test's `/parse` with an `ast` taken from a different string: spans run past the end and
  `codePointSpanToUtf16` throws. Put every query a UI test writes into the backend's HAND list so the stub
  answers with the server's real `ast` (an unknown query gets a 500, which makes the gap obvious).
- `getAllByText("AND")` in a workspace test also finds the hidden editor's highlighted operators; scope
  queries to the builder's tabpanel.

## Decisions (and what would change them)
- The builder reuses `lex.ts` (the editor's generated mirror of `lexer.py`) to decide bare vs quoted. It never
  decides meaning: the server's answer is checked against the model on every write. Revisit only if the
  lexer mirror stops being generated/goldened.
- No fast-check: the seeded mulberry32 edits in `write.test.ts` are deterministic and their outputs are
  parsed by the backend, which a JS-only property test couldn't do.

## Follow-ups
- [ ] TASK-111: show wildcard expansions under builder groups and dim the groups that fit under the
  read-only notice.
- [ ] Copy deck BD-10 review has no separate task; include the builder strings in TASK-047's first usability
  round rather than creating another pre-study copy pass.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/agents/query-builder-engineer.md` (fit rule as built, the
  two-golden proof), `.claude/skills/codemirror-lezer/SKILL.md` (`lex.ts` now also serves the builder),
  `CLAUDE.md` (layout), `docs/specs/05-frontend.md` §Components 3, the builder design doc §As built.
- Test or hook added? — `backend/tests/contract/test_frontend_builder_golden.py` (stale read golden, a
  misread write), `frontend/src/builder/write.test.ts` (stale write golden), `read.test.ts`.
