# A server message spliced after a colon reads as a broken sentence

**Key lesson:** When a frontend line wraps an API envelope's `message`, end the frontend's own clause with a full stop and let the message stand as its own sentence; and keep "excluded" for default filters only, even in builder controls.

- **Date:** 2026-10-01 · **Task:** task-100 · **Area:** frontend
- **Artifacts:** `frontend/src/components/search/search-workspace.tsx` (`Unchecked`), `frontend/src/builder/concept-builder.tsx`, `docs/design/2026-09-27-copy-deck.md` (ED-18, BD-10, the TASK-100 before/after table)

## What we set out to do
Review the strings TASK-041–044 added after the copy deck was handed off ("The query couldn't be checked: …",
BD-10, TASK-042's paging/year/paper strings, TASK-044's record and export strings), put each in the deck, and
apply the rewrites.

## What we learned
- The editor's line read "The query couldn't be checked: Too many requests from this address; try again in 3 s."
  The API's messages are whole capitalised sentences (`rate_limited` in `backend/src/openproceedings/api/middleware.py`
  builds `"{who}; try again in {seconds} s."`), so a colon before them always gives a mid-sentence capital.
  A full stop fixes every envelope message at once, without touching the registry.
- The same component's network case read "…couldn't be checked: couldn't reach the server." A clause after a
  colon needs its own subject; the record page's `CantLoad` had the same shape. Both now say "the server
  couldn't be reached. Check your connection.", which also adds the fix the pattern asks for (as ER-6 does).
- The builder had drifted from the glossary: "+ Exclude terms", "Remove excluded terms", "added to the excluded
  terms", while the same row's heading says "Leave out papers with any of:". *Excluded* is the banner's word for
  default filters; TASK-093 already rewrote `PARSE_ALL_NEGATIVE` for the same reason. The row is now
  "leave-out terms" throughout.
- Several of the reviewed strings had no test pinning them (the year line, the record page's network text, the
  builder's leave-out announcements, the save's 409 sentence in full); the review added one for each.

## Dead ends — don't repeat these
- Asserting `textContent` on a `role="alert"` that also holds the Retry button picks up "Retry" too; assert on
  the message paragraph (`within(alert).getByText(/^The record couldn't be loaded/)`).

## Decisions (and what would change them)
- "Includes `<ranges>`." replaces "Admits …" for the year line, pairing with "Leaves out" and RH-1's
  "included" / "left out". A usability finding that "Includes" reads as additive would reopen it.
- The 429 text keeps the server's static "try again in N s." in the editor (no countdown), since Check again
  is one click and the search panel's ER-3 has the countdown.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/ux-writing/SKILL.md` §Message pattern (server message after a full stop; a clause after a colon keeps its subject) and §Glossary (*excluded* never for `NOT` terms).
- Test or hook added? — Vitest pins in `search-workspace.test.tsx`, `record-view.test.tsx`, `search-view.test.tsx`, `concept-builder.test.tsx`, `save-record.test.tsx`; no hook (wording is a review call).
