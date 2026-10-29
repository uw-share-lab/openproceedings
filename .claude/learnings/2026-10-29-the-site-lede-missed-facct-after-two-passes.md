# The site's lede and meta description left out FAccT after two passes that named it elsewhere

**Key lesson:** When a venue joins the one-line description, `git grep` the old list's exact wording across the whole repo (`git grep -n "AIES and IASEAI"`), frontend included, rather than fixing the copy you happen to be reading.

- **Date:** 2026-10-29 · **Task:** n/a · **Area:** frontend
- **Artifacts:** `frontend/src/app/layout.tsx` (`metadata.description`), `frontend/src/app/page.tsx` (home lede), PR #208

## What we set out to do
Name FAccT in the two frontend copies of the project description, which v0.7.0 serves without it.

## What we learned
- **The description has seven copies.** `CITATION.cff`, `README.md`, `CLAUDE.md`, `backend/pyproject.toml`,
  `backend/src/openproceedings/__init__.py`, and the frontend's `layout.tsx` and `page.tsx`. Milestone B and PR #208
  updated the backend and the docs, and the two frontend copies kept "AIES and IASEAI" (evidence: the 404 page of the
  local v0.7.0 deploy, whose `<meta name="description">` comes from `layout.tsx`).
- **Nothing pins them.** No vitest, golden or copy-deck row holds the lede's text, so a stale venue list passes every
  check; only a grep finds it.

## Dead ends — don't repeat these
- None.

## Decisions (and what would change them)
- No test pins the venue list: the list is copy, and a test would only repeat it. A third miss would justify one
  that compares the frontend copy with `backend/pyproject.toml`'s description.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — no: the key lesson above is the whole rule, and this index is where a venue
  addition looks.
- Test or hook added? — no (see Decisions).
