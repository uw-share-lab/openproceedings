# A frontend twin of a Python text helper is wrong if it uses JavaScript's character classes

**Key lesson:** When porting a Python text helper to TypeScript, spell out Python's character set (`str.isspace()` is not JS `\s`), count code points rather than UTF-16 units, and pin the port with a table of the Python function's own outputs.

- **Date:** 2026-10-01 · **Task:** task-144 · **Area:** frontend
- **Artifacts:** `frontend/src/lib/clip.ts`, `frontend/src/lib/clip.test.ts`, `frontend/src/lib/search-state.ts`, `backend/src/openproceedings/diagnostics.py::clip`

## What we set out to do
Quote client values in the URL-to-state reducer's refusals and URL notices the way `diagnostics.clip` quotes them, so `Coded` keeps its backticks paired.

## What we learned
- JS `\s` and Python's `str.isspace()` differ. JS adds U+FEFF, which Python treats as an invisible `Cf` character to escape. JS leaves out U+001C–U+001F and U+0085, which Python collapses to a space. Evidence: `python3 -c "import re,sys; print([hex(i) for i in range(sys.maxunicode+1) if re.match(r'\s', chr(i))])"`. `clip.ts` therefore lists the 29 code points explicitly.
- A JS string's `.length` counts UTF-16 units, so an emoji is 2 where Python counts 1. The width check has to count code points with `[...piece].length`. The `"😀".repeat(41)` row in `clip.test.ts` pins this.
- `/[\p{Cc}\p{Cf}\p{Cs}]/u` matches a lone surrogate in Node, because `for…of` yields it as one code point. That makes the `Cs` rule portable.
- A value the reducer did not write also includes values that are typed but come from untyped data: `clause.field` from `/parse`, or an `action.page` cast from elsewhere. The tests reach them with `as unknown as`.

## Dead ends — don't repeat these
- Writing `\u2028`-style escapes into a source file through the agent's file tools, or through a heredoc, put the literal invisible characters in the file. Regex literals then failed to parse ("Unterminated regular expression"), and test tables held raw bidi characters. Check with `od -c` or `grep -nP "[^\x00-\x7f]"`. In tests, write such characters as `String.fromCodePoint(0x202e)`. In source, write the escape text with a script, e.g. `chr(92) + "u2028"`.

## Decisions (and what would change them)
- `clip.test.ts` holds a hand-copied table of the backend's outputs instead of a golden that a backend test generates → this keeps the change frontend-only → generate the golden from the backend (as `help_golden.py` does) if `diagnostics.clip` changes again.
- `BAD_PAGE` keeps its wording without backticks. The page is clipped, not quoted → the copy is unchanged.

## Follow-ups
- [ ] Listed as a deferral in the PR: other `Coded` messages quote server-written values (`exclusion-banner.tsx`, `search/exclusions.ts`, `lib/replay-status.ts`). These are not client text, so this task left them alone.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/error-diagnostics/SKILL.md` §Message style ("The frontend quotes alike"); `docs/specs/05-frontend.md` §URL is state.
- Test or hook added? — `frontend/src/lib/clip.test.ts` (the backend's outputs) and the TASK-144 block in `search-state.test.ts`. There is no hook: the tests catch a value that bypasses the helper.
