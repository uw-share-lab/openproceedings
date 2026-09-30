# The builder finds a term's expansions through the server's ast, and its read-only view needed a per-part walk

**Key lesson:** To attach server data keyed by normalized forms (like `/search` `query.expansions`, keyed `<stem><op>`) to UI terms, match the server's `ast` leaves to each term's span and use their `stem`/`op`, never the term's typed text; and when a reader stops at the first thing that doesn't fit, make it a view of a walk that reads every part on its own, so a partial display can reuse it without touching the golden it is checked against.

- **Date:** 2026-09-30 · **Task:** task-111 · **Area:** frontend
- **Artifacts:** `frontend/src/builder/expansions.ts`, `frontend/src/builder/read.ts` (`readParts`, `readFitting`), `frontend/src/builder/concept-builder.tsx` (`carryKeys`, `GroupExpansions`, `FittingParts`), `docs/design/2026-09-27-concept-group-builder.md` §As built (TASK-111)

## What we set out to do
Show each builder group's wildcard expansions after a search, and show the groups that fit, dimmed, under the read-only notice (design B1/B2).

## What we learned
- The expansion keys are the **normalized** stem plus the operator (`search.py` `expansions_json`): `LLM$` is keyed `llm$`, and `gpt-4*` is a phrase whose wildcard is keyed `4*`. So the term's text can't be the key. The draft's `ast`, which the builder already has, gives each wildcard's `stem`, `op` and span, phrase items included. Mapping them to terms by span containment gets the key right without a client-side copy of normalization (evidence: `expansions.test.ts`, the `gpt-4*` → `4*` case).
- The parse of a builder edit is in flight for a moment, so keys derived only from the current parse made every group's lines flicker on any edit. Carrying a term's keys across an edit while its written text is unchanged fixes that. The held-`/parse` test fails when the carry is removed (checked by hand as a mutant).
- `readAst` threw at the first blocker, so it couldn't show what fit. Reading each top-level part in its own `try` gives both results from one walk: the first blocker for `readAst`, unchanged against the 362-case read golden, and the fitting shape for `readFitting`. A property test pins `readFitting == readAst.shape` on every golden query that fits.

## Dead ends — don't repeat these
- Adding the fitting shape to `readAst`'s `blocked` result would have broken `read.test.ts`, which `toEqual`s it against the golden's `{ kind, blocker }`. A separate `readFitting` keeps the golden contract as it is.

## Decisions (and what would change them)
- Expansions stay shown while the draft differs from the searched query → an expansion is a fact about the index, not the query → reverse if the builder ever serves a draft against a different `index_version` from the one searched.
- In the read-only view, groups are "Group `<n>`" with no "of `<m>`" (ux-writer): the parts that don't fit aren't counted, so a total would be false.

## Follow-ups
- none

## Propagated to
- Skill / agent / CLAUDE.md updated? — the design doc's §As built (TASK-111) and copy deck BD-11 record the mapping and the copy; CLAUDE.md's `src/builder/` line names TASK-111. No skill change: `wildcards-and-expansion` already says the stem is normalized before expansion, and the key format is in `search.py`'s docstring.
- Test or hook added? — `frontend/src/builder/expansions.test.ts`, the `readFitting` cases in `read.test.ts`, and the TASK-111 blocks in `concept-builder.test.tsx` and `search-view.test.tsx`.
