# A highlighter can mirror the server lexer exactly if its tables and its test cases are generated from it

**Key lesson:** Make the editor's Lezer grammar a flat token sequence fed by an external tokenizer that mirrors `lexer.py` in code points, import its character classes from a JSON the backend generates, and check it against a backend-generated golden (every lexer/parser golden input, Trust-Evals, and 400 seeded random strings); and in Vitest with fake timers, advance time in several short `act()`s with real event-loop turns between them, or TanStack Query and a stubbed fetch never deliver.

- **Date:** 2026-09-27 · **Task:** task-041 · **Area:** frontend
- **Artifacts:** `frontend/src/editor/lang/` (`lex.ts`, `tokens.ts`, `query.grammar`, `lexer-tables.json`, `lexer-golden.json`, `grammar.test.ts`), `backend/tests/contract/test_frontend_lexer_golden.py`, `frontend/src/test/api-stub.tsx` (`pass`)

## What we set out to do
Build the `/search` query editor: CodeMirror 6 with a Lezer grammar for highlighting only, server `/parse`
diagnostics as squiggles and an accessible list, and the draft/dirty behaviour of the design.

## What we learned
- **A structural Lezer grammar would disagree silently; a token-only one can't.** The grammar is
  `@top Query { lexeme* }` over external tokens, so it has no rule that can reject input and the tree never
  holds an error node. What it colours is exactly the server's lexemes: 724 golden cases (every input in
  `test_lexer.py`/`test_parser.py`, the Trust-Evals strings, probes, and 400 random strings over the lexer's
  special characters, seed 41) pass class for class and span for span (`lex.test.ts`, `grammar.test.ts`).
  The seeded random strings are what makes that claim credible: hand-picked inputs don't reach interleavings
  of quotes, `$…$` math, backslashes and parentheses.
- **Generate the tables, don't restate them.** Quotes and their closer families, NFKC look-alikes of
  `( ) | : - * $`, field names, Python's `str.isspace` set and the non-`Nd` characters `str.isdigit` accepts
  are written by the backend test into `lexer-tables.json`, and `lex.ts` imports them; the test fails when
  either JSON is stale. `\s` in JS and `str.isspace` differ (U+001C–U+001F, U+0085, U+FEFF), and `isdigit`
  accepts superscripts and circled digits, so hand-copied classes would have drifted on day one.
- **Lexing is local, so an external tokenizer works.** Every lexer.py rule looks only at the previous
  character and forward, so the tokenizer reads the document through `InputStream.peek` as code points
  (joining surrogates) and converts the end back to UTF-16. Incremental reparses after an edit next to a
  `-` or a quote give the fresh parse's tokens (`grammar.test.ts`, "incremental reparsing").
- **`openapi-fetch` doesn't return `schema.ts`'s types.** Its `Readable<>` turns tuple spans (`[number,
  number]`) into `number[]`, so `data` isn't assignable to `Schemas["ParseResponse"]`. Type responses with
  `MethodResponse<Api, "post", "/api/v1/parse">` and validate spans once (`spanOf` in `diagnostics.ts`)
  instead of casting.
- **Fake timers + React 19 `act` + TanStack Query.** A state update made inside an async `act` renders when
  that `act` ends, so a debounce firing inside `advanceTimersByTimeAsync(300)` starts its query only
  afterwards; TanStack's notifications are `setTimeout(0)`; and a stubbed fetch reading a `Request` body
  needs real event-loop turns. `pass(ms)` advances in one `act`, then runs eight short `act`s, each a real
  `setTimeout(0)` followed by `advanceTimersByTimeAsync(0)`.
- **Measured keystroke-to-squiggle** against `op serve` on the local index (production build, Chromium):
  261–272 ms over five edits, 250 ms of it the debounce (spec 05 budget ≤300 ms).

## Dead ends — don't repeat these
- A single `act(async () => { advance; await real turns })` never rendered the debounced query: all 17
  answer-dependent tests saw nothing. Split the turns into separate `act`s.
- `setImmediate` turns alone don't flush a real `setTimeout(0)` (it has a 1 ms floor); use a real
  `setTimeout` captured before the test fakes it.
- Reading the reading out of `WARN_MIXED_AND_OR`'s message ("Load with parentheses") works but is parsing
  prose; the server shortens a reading over 120 characters with `…`, and the button is then left out.

## Decisions (and what would change them)
- Diagnostics are pushed into CodeMirror with `setDiagnostics` from a TanStack query keyed
  `["parse", q, mode]`, not with `linter()`: the row, the summary, the tree and the squiggles all need the
  same answer, and the key (not the doc) decides staleness, which also covers a Syntax change. The skill now
  says so. A `linter()` source would be simpler only if nothing but squiggles used `/parse`.

## Follow-ups
- [ ] (for the main session to reserve an id) a `reading` field on `WARN_MIXED_AND_OR` so "Load with
  parentheses" needn't parse the message.
- [ ] (for the main session) ux-writer review of the new "The query couldn't be checked: …" strings for
  `/parse` refusals (429, 503, non-JSON, unreachable), which the copy deck doesn't word.

## Propagated to
- Skill updated? — `.claude/skills/codemirror-lezer/SKILL.md` (as-built layout, token-only grammar,
  generated tables and golden, `setDiagnostics` wiring, the test helper)
- Test or hook added? — `backend/tests/contract/test_frontend_lexer_golden.py` (stale tables or golden fail
  CI); `frontend/src/editor/lang/grammar.test.ts` (stale `parser.ts` fails)
