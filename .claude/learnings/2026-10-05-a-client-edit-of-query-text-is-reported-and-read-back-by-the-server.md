# An edit a client makes to query text has to be reported by the server and read back by parsing the edited string

**Key lesson:** When the UI writes into the query for the reader (a `$`, parentheses, a filter clause), have the server say exactly where and what to insert, parse the edited string itself and compare the tree with the one it meant, and offer nothing when they differ; then hold the rules to that read-back in a property over every subset a reader can pick, because two things only the lexer knows broke a "just append `$`" edit here: a second `$` in an unspaced run closes LaTeX math, and a lowercase `and` with a `$` is no longer an operator word.

- **Date:** 2026-10-05 · **Task:** TASK-175, TASK-181 · **Area:** query, api, frontend
- **Artifacts:** `backend/src/openproceedings/query/exact.py` (`dollar_places`), `backend/src/openproceedings/query/wordforms.py`, `backend/tests/unit/test_wordforms.py`, `backend/tests/unit/test_compat.py` (`STEMMING_EXAMPLES`), `backend/tests/contract/test_frontend_word_forms_golden.py`, `frontend/src/lib/word-forms.ts`, `frontend/src/components/search/diagnostics-row.tsx`, spec 02 §Word forms

## What we set out to do
Let a reader who pasted a Google Scholar string apply the no-stemming notice's own suggestion in one click:
write `$` after the terms the notice names, as an edit of the query text (guarantees 1, 3 and 6), never as a
way of matching.

## What we learned
- **Appending `$` to each named term is not a safe edit.** In `(model|LLM)`, a `$` on both words gives
  `(model$|LLM$)`, and the lexer reads `$|LLM$` as LaTeX math (Pandoc's rule, found per unspaced run), so
  neither is a wildcard. The server now asks for `$` and a space on every offered word but the last of a run
  (`(model$ |LLM$)`), and leaves a word alone when its run already holds a `$` or a backslash. Evidence: the
  `two words in one unspaced run` and `a wildcard earlier in the unspaced run` rows of `test_wordforms.py`.
- **A rule that reads a word's text changes when the text does.** `compat.py` keeps a lowercase operator word
  out of a `|` item's phrase by its text, and the lexer's `WARN_LOWERCASE_OPERATOR` goes by it too. So
  `trust | LLM and` with `$` on all three read back as `trust$ | "LLM$ and$"`, another query; the read-back
  refused it and nothing was offered, with no error to say why. The first version shipped this: its property
  asserted that the read-back refuses only a query over the length cap, and its strategy could draw the input,
  so it was a failure waiting for a seed (found in review, fixed in the next commit; the three strings are now
  `@example`s). `exact.reads_as_operator` leaves such a word alone.
- **The read-back is what made that a missing offer, not a wrong query.** `word_forms` makes every edit at
  once, parses the result in the query's mode and requires the tree to be the original with exactly those
  leaves made `$` wildcards. The rules are meant to allow only what it accepts; the property
  (`test_offered_edits_are_sound_on_generated_queries`) fails when it refuses anything they allow short of the
  cap. The same shape as `clauses.filter_clauses` (decision-011), and for the same reason it is a `/parse`
  field and not part of `parse` or of a `Diagnostic`: `parse` would recurse.
- **"All together" and "each alone" are not "any subset".** The chooser applies whichever terms are ticked.
  `check_edits` now tries every combination of the first six forms; the space rule above is what makes a
  subset sound (ticking only `model` gives `(model$ |LLM)`).
- **A leaf's span is wider than its word.** `title:trust` spans the prefix and `(model)` the parentheses, so a
  lexeme is matched to its leaf by containment, never by equal spans or equal ends (both were tried and each
  dropped real cases silently).
- **Two places asked the same question and one answered it wrongly.** The notice's own example was built from
  the first term (`AI C++ or` suggested `ai$`, a `WILDCARD_STEM_TOO_SHORT`). The rule now lives once, in
  `query/exact.py` below both `parser.py` and `wordforms.py`, and the example is the first term it allows or
  is left out (TASK-181).

## Dead ends — don't repeat these
- Having the client find the terms (from the message, or from the highlighting grammar): it can't know a
  Scholar phrase run, the stem minimum or the math rule, and it is the re-parsing `typescript-standards`
  forbids.
- Treating a green property as proof the rules are complete. It is a search for counterexamples; a rule in
  the lexer or `compat.py` that reads a word's text needs its own row and its own words in the strategy.
- Verifying each edit with its own parse at request time: one parse per term of a 2,000-character query. One
  combined read-back plus rules that make subsets sound costs one parse.

## Decisions (and what would change them)
- A phrase takes `$` on its last word only → the notice names the phrase as one term and the review's own
  strings write it so → reverse if readers ask for inner words (they can type them: it is valid syntax).
- Nothing is offered when all edits together would pass the length cap → the read-back is one parse of the
  full edit → revisit if near-cap strings turn out to be common (a follow-up task holds it).

## Follow-ups
- Filed by the main session with the batch's follow-up tasks (offer the subset that fits near the cap; a
  per-term reason for a term left alone).

## Propagated to
- Skill / agent / CLAUDE.md updated? — `scholar-syntax-compat` (one rule function, the read-back, never in the
  client), `wildcards-and-expansion` (where `$` may go), `error-diagnostics` (data that costs a parse is a
  `/parse` field, not a `Diagnostic` field), spec 02 §Word forms, `CLAUDE.md`'s `query/` line.
- Test or hook added? — `test_wordforms.py` (table, subsets, property with the three review strings as
  examples), `test_compat.py` (`STEMMING_EXAMPLES`), `word-forms-golden.json` read by both sides.
