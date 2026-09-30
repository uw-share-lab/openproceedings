# A message's quoting helper only shortened text, so a backtick or newline in the query broke the quote

**Key lesson:** A helper that quotes user text inside a delimiter must escape that delimiter and every invisible or line-breaking character, not just shorten it; then grep for quotes that bypass it (raw slices such as `q[i : i + 20]` or `raw[0]` did) and pin it with a property over queries seeded with those characters.

- **Date:** 2026-09-30 · **Task:** task-141 · **Area:** query
- **Artifacts:** `backend/src/openproceedings/diagnostics.py` (`clip`), `backend/tests/unit/test_diagnostics.py`, `backend/tests/unit/test_parser.py::QUOTED`, `backend/tests/unit/test_properties.py::test_every_message_quotes_query_text_on_one_visible_line`

## What we set out to do
Make every diagnostic that quotes query text safe to log and copy: one line, no control characters, and a
backtick in the query unable to end the message's backtick quoting.

## What we learned
- The backtick is not cosmetic: the UI's `Coded` and `Ticked` split a message on every backtick and pair them
  up, so one backtick typed in the query (the lexer reads it as a lookalike quote) shifted every later code
  span in the message (evidence: `a b OR \`c\`` gave ``` ``c`` starts with a single quote… ```).
- `clip()` was called at about 60 sites, but five quotes bypassed it with raw slices of the input: the
  unterminated-phrase message (`q[i : i + 20]`), the stray wildcard (`raw[s]`), the lookalike minus
  (`raw[0]`), the ambiguous quote (`self.q[k]`), and the reference engine's wildcard cap. A grep for
  backtick-quoted interpolations without `{clip(` found them; the new property then pins it.
- Python's `re` `\s` matches exactly the `str.isspace()` characters (checked over all code points), the same
  set the lexer splits words on, so collapsing with `\s+` agrees with the lexer (NBSP, U+2028, `\x1c`–`\x1f`
  included).
- Escaping made fix hints wrong: a hint is text to type back, and `-foo\x60bar` copied from a hint searches
  `NOT "foo 60bar"`, not the word typed (query-semantics review). A hint now quotes the query only when
  `diagnostics.verbatim()` says no escape was needed, and otherwise says what to do in words.
- Escaping lengthens text, so shortening must count escapes whole: cutting after escaping could leave `\x0…`.

## Dead ends — don't repeat these
- Escaping a backtick as `` \` `` keeps the backtick, and the UI still pairs it; the escape must remove the
  character (`\x60`).
- Escaping the backslash too would make escapes unambiguous but turns every LaTeX quote into `\\alpha`; the
  span, not the message, is the exact locator.

## Decisions (and what would change them)
- Escape `Cc`, `Cf` and `Cs` plus the backtick as Python escapes; leave backslashes raw → messages stay
  readable for LaTeX queries → revisit if a client ever needs to parse `message` (it must not; `reading` and
  spans carry data).
- Message text is prose, not API contract (codes, spans and `reading` are), so the rewording is not breaking.

## Follow-ups
- [ ] none as tasks from this branch (a parallel branch may claim ids); non-query user text in messages (the
  422 validation `loc`, frontend reducer refusals quoting facet values) is listed in the PR as a deferral.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/error-diagnostics/SKILL.md` §Message style (quote only
  through `clip`; what it escapes; message text is not contract); `docs/specs/02-query-language.md`.
- Test or hook added? — the property and goldens above; no hook (the property catches a bypass that a
  generated query reaches).
