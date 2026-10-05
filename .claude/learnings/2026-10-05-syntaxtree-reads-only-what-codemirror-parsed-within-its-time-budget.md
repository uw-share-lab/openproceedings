# `syntaxTree(state)` is only what CodeMirror parsed within a wall-clock budget, so a test that reads it fails under load

**Key lesson:** In a test, read a CodeMirror tree with `ensureSyntaxTree(state, length, timeout)`, never `syntaxTree(state)`: the latter returns whatever was parsed inside a start-up time budget measured on the wall clock, which on a loaded machine is the tree of a prefix of the document; and reach an e2e "special state" (a tight limit, a feature off) by pointing the page at another configuration of the fixture server, not by writing the answer in the browser.

- **Date:** 2026-10-05 · **Task:** TASK-182 · **Area:** frontend, tooling
- **Artifacts:** `frontend/src/editor/lang/grammar.test.ts`, `frontend/src/editor/query-editor.test.tsx`, `backend/tests/e2e/fixture_server.py`, `frontend/e2e/instances.ts`, commits bc662579, 56dfff2b

## What we set out to do
Add browser, keyboard, axe and visual coverage for the batch's three UI features (Add `$`, the builder's group
counts, the RIS comparison).

## What we learned
- **The flake was a budget, not the grammar.** `grammar.test.ts` compared the Lezer tree's tokens with the
  server lexer's golden for each case. With several test suites running on the machine, one case or another
  failed on each run, a different one each time, always with a tree that stopped early. `syntaxTree(state)`
  is the tree parsed so far; a new state parses within a start-up time budget on the wall clock and leaves
  the rest for later work that a state-only test never triggers. `ensureSyntaxTree` parses to the
  position asked for. A test whose clock advances on every read (so the budget is spent at once) now pins it
  without needing a loaded machine (bc662579).
- **How to recognise it:** failures that move between cases from run to run, only under load, with output
  that is a correct prefix of the expected one. Rerunning the one test alone passes.
- **One index, three servers, no browser mocks.** The fixture server serves the same index from three
  configurations (default; `tight`: low group-count bounds, the rate limit with a visible cooldown, a small
  file cap; `plain`: comparisons off), and a spec re-addresses a page's API calls to one of them. Every
  answer a spec sees is one the API gave (56dfff2b). Tests on `tight` share one client network, so a test
  that needs a comparison waits out another's cooldown through the panel's own Retry.

## Dead ends — don't repeat these
- Raising a test timeout or retrying the test: the tree was never going to be complete.
- `page.route` with a hand-written JSON body for a refusal: it is the partial stub
  [that broke the next reader](2026-09-29-partial-api-stubs-break-the-next-reader.md), in a browser.

## Decisions (and what would change them)
- Linux visual baselines come from CI's own run, as
  [the earlier entry](2026-09-30-linux-visual-baselines-need-a-native-amd64-runner.md) says; the new element
  baselines are darwin-only until that run.

## Follow-ups
- Filed by the main session with the batch's follow-up tasks (the Linux baselines).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `testing-standards` (`ensureSyntaxTree` in tests; e2e instances),
  `codemirror-lezer` (§Testing: the same rule, where an editor test is written), spec 05 §Testing.
- Test or hook added? — `grammar.test.ts`'s clock test.
